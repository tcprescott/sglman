"""Shared scaffolding for OAuth identity-link pages.

racetime.gg and Twitch each expose the same single-flow link: a logged-in user
authorizes with the provider (read scope), we exchange the returned code once for
their verified identity and record it, then discard the token. The two page
modules were line-for-line identical except the service class, storage keys,
route paths, and user-facing strings; :func:`register_identity_link_pages`
parameterises that shape.

``challonge_oauth.py`` has its own two-flow (service + player) page registration
because its single callback is shared between the two flows, but it reuses the
:func:`read_callback_code` / :func:`returned_state` helpers here (and the player
link handoff below) so the callback-URL parsing lives in exactly one place.

Custom-domain handoff (``HOST_OAUTH_MODE=handoff``)
---------------------------------------------------
On a custom domain each provider callback still lands on the **platform** host
(one registered redirect URI per provider), whose session can't see the custom
domain's cookie — so the link would have no logged-in user to attach to. Today
those affordances are simply blocked on custom domains ("Main site only"). This
module mirrors the Discord-login handoff (:mod:`pages.auth`): the provider OAuth
runs on the platform host, then the **verified provider identity** (id + name —
public, exactly like the login handoff's Discord id/name) is handed back to the
custom domain through a single-use, host-bound, browser-bound signed token, where
the user's session lives and the link (with its tenant-scoped audit) is recorded.
Only public identity crosses the wire; the provider access token is exchanged and
discarded on the platform host, never handed across.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.services import oauth_handoff_service as handoff_service
from application.services.auth_service import get_user_from_discord_id
from application.services.tenant_service import TenantService
from application.tenant_context import get_current_tenant_id, is_host_mode
from application.utils.environment import (
    get_base_url,
    get_platform_host,
    host_oauth_handoff_enabled,
)
from application.utils.hostname import normalize_hostname, scheme_for_host
from application.utils.tenant_urls import safe_next
from models import User

logger = logging.getLogger(__name__)

__all__ = [
    'IdentityLinkFlow',
    'LinkHandoffProvider',
    'register_identity_link_pages',
    'register_link_handoff_provider',
    'register_link_handoff_pages',
    'maybe_start_link_handoff',
    'handle_link_handoff_callback',
    'read_callback_code',
    'returned_state',
    'platform_link_redirect',
]


async def platform_link_redirect(local_return: str) -> Optional[str]:
    """Where to send a secondary OAuth link that was initiated on a custom domain.

    The secondary providers (Challonge, Twitch, racetime, Discord connect) all
    redirect to a single registered callback on the **platform** host, which
    can't see a custom domain's host-only session cookie — so the flow would
    silently fail there. In host mode, send the user to the equivalent path-mode
    URL on the platform host, where linking works. Returns ``None`` in path mode
    / platform surface (the flow runs in place).

    This is the **Design A** fallback: when ``HOST_OAUTH_MODE=handoff`` is on,
    :func:`maybe_start_link_handoff` runs the cleaner cross-host handoff instead,
    and callers only fall through to this detour with handoff off.
    """
    if not is_host_mode():
        return None
    tid = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tid) if tid is not None else None
    base = get_base_url()
    if tenant is None:
        return base or '/'
    return f'{base}/t/{tenant.slug}{local_return}'


def returned_state(url: str) -> Optional[str]:
    """Extract the OAuth ``state`` parameter from a callback URL, if present."""
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    return (params.get('state') or [None])[0]


def read_callback_code(
    url: str, expected_state: Optional[str], provider_label: str,
) -> Optional[str]:
    """Validate the OAuth callback URL and return the authorization code or None."""
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    if 'error' in params:
        logger.warning('%s OAuth callback returned error: %s', provider_label, params.get('error'))
        return None
    state = (params.get('state') or [None])[0]
    if not expected_state or state != expected_state:
        logger.warning('%s OAuth state mismatch on callback.', provider_label)
        return None
    return (params.get('code') or [None])[0]


# ---------------------------------------------------------------------------
# Cross-host link handoff (Design B): registry + URL builders + shared routes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkHandoffProvider:
    """What the shared handoff routes need to complete a link for a provider.

    ``authorize_url`` runs on the platform host (start leg); ``exchange`` runs in
    the platform-host callback (code → ``{'user_id', 'name'}`` public identity);
    ``record`` runs on the custom domain (claim leg) where the user's session and
    tenant context live, so its audit row is stamped with the right tenant.
    """

    key: str
    label: str
    profile_return: str
    authorize_url: Callable[[str], str]
    exchange: Callable[[str], Awaitable[dict]]
    record: Callable[[User, dict], Awaitable[None]]


# provider key -> config. Populated at each provider module's ``create()`` time.
_HANDOFF_PROVIDERS: dict[str, LinkHandoffProvider] = {}

# Guards the one-time registration of the two shared handoff routes.
_pages_registered = False


def register_link_handoff_provider(provider: LinkHandoffProvider) -> None:
    """Register a provider so the shared ``/oauth/link/*`` routes can complete it."""
    _HANDOFF_PROVIDERS[provider.key] = provider


def _bind_commit(secret: str) -> str:
    """The commitment published through the platform hop for a browser secret."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _link_handoff_start_url(
    provider_key: str, target_host: str, next_path: str, bind_commit: str,
) -> str:
    """Platform-host ``/oauth/link/start`` URL that begins a handoff for a domain."""
    platform = get_platform_host()
    query = urlencode({'p': provider_key, 'host': target_host, 'next': next_path, 'b': bind_commit})
    return f'{scheme_for_host(platform)}://{platform}/oauth/link/start?{query}'


def _link_claim_url(target_host: str, token: str) -> str:
    """Custom-domain ``/oauth/link/claim`` URL the platform callback hands off to."""
    return f'{scheme_for_host(target_host)}://{target_host}/oauth/link/claim?token={quote(token, safe="")}'


def _cross_host_url(host: str, path: str) -> str:
    """An absolute URL on ``host`` for a plain (token-less) return redirect."""
    return f'{scheme_for_host(host)}://{host}{path}'


async def maybe_start_link_handoff(
    provider_key: str, next_path: str,
) -> Optional[RedirectResponse]:
    """Begin a cross-host link handoff when on a custom domain in handoff mode.

    Returns a redirect into the platform-host ``/oauth/link/start`` (so the
    provider OAuth runs there and hands the verified identity back here), or
    ``None`` when the flow should run in place (path mode, or handoff disabled).
    Call it from a provider's ``/<provider>/link`` initiation page.
    """
    if not (is_host_mode() and host_oauth_handoff_enabled()):
        return None
    tid = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tid) if tid is not None else None
    if tenant is None or not getattr(tenant, 'domain', None):
        return None
    # Bind the handoff to *this* browser: stash a secret in this domain's session
    # and publish only its hash through the platform hop, so a token minted in
    # another browser can't be replayed here (link-CSRF / forced link).
    bind = secrets.token_urlsafe(32)
    app.storage.user['oauth_link_bind'] = bind
    return RedirectResponse(
        _link_handoff_start_url(provider_key, tenant.domain, safe_next(next_path), _bind_commit(bind))
    )


async def handle_link_handoff_callback(url: str) -> bool:
    """Complete a custom-domain link on the platform host, then hand it back.

    If the current provider callback is a handoff leg (markers present in the
    platform-host session), exchange the code for the verified provider identity,
    mint a single-use host-bound token carrying that public identity, and redirect
    the browser to the target domain's ``/oauth/link/claim`` where the user's
    session lives. Returns ``True`` when it handled the callback (the caller must
    return), ``False`` for a normal in-place (path-mode / Design A) callback.
    """
    provider_key = app.storage.user.pop('oauth_link_provider', None)
    if not provider_key:
        return False
    expected_state = app.storage.user.pop('oauth_link_state', None)
    host = app.storage.user.pop('oauth_link_host', None)
    bind_commit = app.storage.user.pop('oauth_link_bind_commit', None)
    provider = _HANDOFF_PROVIDERS.get(provider_key)
    next_path = safe_next(
        app.storage.user.pop('oauth_link_next', None)
        or (provider.profile_return if provider else '/')
    )
    if provider is None or not host:
        # Nothing to hand back to; return the user somewhere sane.
        ui.navigate.to(_cross_host_url(host, next_path) if host else next_path)
        return True
    code = read_callback_code(url, expected_state, provider.label)
    if code is None:
        # Cancelled / denied / state mismatch — send the user back to their domain.
        ui.navigate.to(_cross_host_url(host, next_path))
        return True
    try:
        data = await provider.exchange(code)
    except Exception:  # noqa: BLE001 - log server-side; hand the user back either way
        logger.exception('%s link handoff exchange failed', provider.label)
        ui.navigate.to(_cross_host_url(host, next_path))
        return True
    token = handoff_service.mint_data(
        data={'key': provider_key, **data},
        target_host=host,
        next_path=next_path,
        bind_commit=bind_commit or None,
    )
    ui.navigate.to(_link_claim_url(host, token) if token else _cross_host_url(host, next_path))
    return True


def register_link_handoff_pages() -> None:
    """Register the shared platform-host ``/oauth/link/start`` + custom-domain
    ``/oauth/link/claim`` handoff routes. Idempotent; call once at startup."""
    global _pages_registered
    if _pages_registered:
        return
    _pages_registered = True

    @ui.page('/oauth/link/start')
    async def link_start(request: Request, client: Client) -> Optional[RedirectResponse]:
        """Platform-host entry point: begin a provider link for a custom domain.

        Records the provider, target host, return path, and browser-binding
        commitment in the platform-host session (the custom domain's cookie isn't
        visible here, so they arrive in the URL) and runs the provider's normal
        OAuth to its single platform callback. The target host is allow-listed
        against known active tenant domains (open-redirect / fixation guard).
        """
        if not host_oauth_handoff_enabled():
            return RedirectResponse('/login')
        params = request.query_params
        provider = _HANDOFF_PROVIDERS.get(params.get('p') or '')
        target = normalize_hostname(params.get('host'))
        next_path = safe_next(params.get('next') or '/')
        bind_commit = (params.get('b') or '')[:64]
        if provider is None:
            return RedirectResponse('/')
        tenant = await TenantService.get_by_domain(target) if target else None
        if tenant is None or not tenant.is_active:
            return RedirectResponse('/')
        state = secrets.token_urlsafe(32)
        app.storage.user['oauth_link_state'] = state
        app.storage.user['oauth_link_provider'] = provider.key
        app.storage.user['oauth_link_host'] = target
        app.storage.user['oauth_link_next'] = next_path
        app.storage.user['oauth_link_bind_commit'] = bind_commit
        return RedirectResponse(provider.authorize_url(state))

    @ui.page('/oauth/link/claim')
    async def link_claim(client: Client) -> None:
        """Custom-domain claim: validate the handoff and record the link here."""
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        parsed = urlparse(url)
        token = (parse_qs(parsed.query).get('token') or [None])[0]
        request_host = normalize_hostname(parsed.netloc)
        # Consume the browser-binding secret this domain's /<provider>/link stashed.
        bind = app.storage.user.pop('oauth_link_bind', None)
        payload = handoff_service.claim(token, request_host) if (token and request_host) else None
        if payload is None:
            ui.notify('Link session expired or already used. Please try again.', color='warning')
            ui.navigate.to('/home/profile')
            return
        # Link-CSRF guard: the token must have been minted for a link *this* browser
        # initiated — the secret behind the committed hash must be in this domain's
        # session. A token delivered to another browser (which lacks it) is rejected.
        expected = payload.get('bind_commit')
        if not (expected and isinstance(bind, str)
                and hmac.compare_digest(expected, _bind_commit(bind))):
            logger.warning('OAuth link handoff browser-binding mismatch on %r', request_host)
            ui.notify('Link is not valid for this browser. Please try again.', color='warning')
            ui.navigate.to('/home/profile')
            return
        data = payload.get('data') or {}
        provider = _HANDOFF_PROVIDERS.get(data.get('key'))
        next_path = safe_next(payload.get('next') or (provider.profile_return if provider else '/'))
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            ui.notify('Please log in and try linking again.', color='warning')
            ui.navigate.to('/login')
            return
        if provider is None:
            ui.navigate.to(next_path)
            return
        try:
            await provider.record(user, data)
            ui.notify(f'{provider.label} account linked.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('%s link handoff claim failed', provider.label)
            ui.notify(f'Could not link {provider.label}. Please try again.', color='negative')
        ui.navigate.to(next_path)


# ---------------------------------------------------------------------------
# Single-flow identity links (racetime / Twitch)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityLinkFlow:
    """Provider-specific configuration for a single-flow identity link.

    ``provider_label`` is woven verbatim into log lines and toasts (``'racetime'``
    / ``'Twitch'``), so it doubles as the display name in messages.
    ``provider_key`` is the stable lowercase slug routed through the handoff.
    """

    provider_key: str
    provider_label: str
    link_route: str
    callback_route: str
    state_key: str
    return_key: str
    profile_return: str
    service_factory: Callable[[], object]
    authorize_url: Callable[[str], str]
    is_mock: Callable[[], bool]
    display_name: Callable[[dict], Optional[str]]


async def _flow_exchange(flow: IdentityLinkFlow, code: str) -> dict:
    """Exchange the code and return the public identity to hand across the wire."""
    service = flow.service_factory()
    me = await service.exchange_player_code(code)
    return {'user_id': me['user_id'], 'name': flow.display_name(me)}


async def _flow_record(flow: IdentityLinkFlow, user: User, data: dict) -> None:
    service = flow.service_factory()
    await service.record_player_link(user, data['user_id'], data.get('name'), actor=user)


def register_identity_link_pages(flow: IdentityLinkFlow) -> None:
    """Register the ``/<provider>/link`` initiation + callback pages for ``flow``."""
    register_link_handoff_provider(LinkHandoffProvider(
        key=flow.provider_key,
        label=flow.provider_label,
        profile_return=flow.profile_return,
        authorize_url=flow.authorize_url,
        exchange=lambda code, f=flow: _flow_exchange(f, code),
        record=lambda user, data, f=flow: _flow_record(f, user, data),
    ))

    @ui.page(flow.link_route)
    async def link(request: Request) -> RedirectResponse:
        # Initiation runs with tenant context; the callback lands on the bare
        # platform host, so pin the tenant-qualified return here.
        root_path = request.scope.get('root_path', '') or ''
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse(f'{root_path}/login')
        if flow.is_mock():
            service = flow.service_factory()
            me = await service.exchange_player_code('mock')
            await service.record_player_link(
                user, me['user_id'], flow.display_name(me), actor=user,
            )
            return RedirectResponse(f'{root_path}{flow.profile_return}')
        # Custom domain + handoff: run the provider OAuth on the platform host and
        # hand the verified identity back here, where the session and tenant live.
        handoff = await maybe_start_link_handoff(flow.provider_key, f'{root_path}{flow.profile_return}')
        if handoff is not None:
            return handoff
        # Custom domain + Design A (handoff off): the callback is on the platform
        # host; bounce to the platform-host path-mode surface where the cookie is
        # visible. No-op (returns None) in path mode / platform surface.
        detour = await platform_link_redirect(flow.profile_return)
        if detour:
            return RedirectResponse(detour)
        state = secrets.token_urlsafe(32)
        app.storage.user[flow.state_key] = state
        app.storage.user[flow.return_key] = f'{root_path}{flow.profile_return}'
        return RedirectResponse(flow.authorize_url(state))

    @ui.page(flow.callback_route)
    async def callback(client: Client) -> None:
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        # Cross-host handoff leg (platform host): exchange + mint + hand back.
        if await handle_link_handoff_callback(url):
            return
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        expected_state = app.storage.user.pop(flow.state_key, None)
        return_path = app.storage.user.pop(flow.return_key, None) or flow.profile_return
        if user is None:
            ui.navigate.to(return_path)
            return
        code = read_callback_code(url, expected_state, flow.provider_label)
        await _finish_link(flow, user, code, return_path)


async def _finish_link(
    flow: IdentityLinkFlow, user: User, code: Optional[str], return_path: str,
) -> None:
    if code is None:
        ui.notify(f'{flow.provider_label} linking was cancelled or failed.', color='warning')
    else:
        try:
            service = flow.service_factory()
            me = await service.exchange_player_code(code)
            await service.record_player_link(
                user, me['user_id'], flow.display_name(me), actor=user,
            )
            ui.notify(f'{flow.provider_label} account linked.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('%s linking failed', flow.provider_label)
            ui.notify(f'Could not link {flow.provider_label}. Please try again.', color='negative')
    ui.navigate.to(return_path)
