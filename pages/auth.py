"""Authentication page routes: Discord OAuth ``/login``, ``/logout`` and
``/oauth/callback``.

This is the presentation half of authentication — it only registers the
``@ui.page`` routes. The actual middleware (``AuthMiddleware``, the
``protected_page`` decorator and the protected-route registry) lives in
``middleware/auth.py``.

When ``MOCK_DISCORD`` is enabled the three routes are replaced by a local
user-picker so developers can impersonate any user (or mint a new one) without
performing real Discord OAuth. User provisioning writes go through
``UserService`` to keep the presentation layer free of direct ORM writes.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import random
import secrets
from typing import Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from zenora import APIClient

from application.services import DiscordLinkService, TenantService, UserService, get_user_from_discord_id
from application.services import oauth_handoff_service as handoff_service
from application.services.discord_role_mapping_service import DiscordRoleMappingService
from application.tenant_context import get_current_tenant_id, is_host_mode, tenant_scope
from application.utils.environment import get_base_url, get_platform_host, host_oauth_handoff_enabled
from application.utils.hostname import normalize_hostname, scheme_for_host
from application.utils.mock_discord import is_mock_discord
from application.utils.tenant_urls import AUTH_ROUTES, sanitize_return_path, tenant_home
from models import Role, Tenant, User
from theme.tables.mobile_grid import enable_mobile_grid

logger = logging.getLogger(__name__)

_client_id = os.getenv("DISCORD_CLIENT_ID")

_LOGIN_ACTION = '''
    <q-btn color="primary" dense label="Log in as"
           @click="$parent.$emit('login_as', props.row)" />
'''

config = {
    "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
    "DISCORD_CLIENT_SECRET": os.getenv("DISCORD_CLIENT_SECRET"),
    "DISCORD_CLIENT_ID": _client_id,
    "STORAGE_SECRET": os.getenv("STORAGE_SECRET"),
}

discordClient = (
    APIClient(config["DISCORD_TOKEN"], client_secret=config["DISCORD_CLIENT_SECRET"])
    if not is_mock_discord() else None
)

def _platform_redirect_uri() -> str:
    """Discord OAuth callback on the platform host (path mode + platform surface).

    Read lazily so a per-deploy override or ``BASE_URL`` change applies without
    reimporting (the old module-level build captured stale values at import).
    """
    return os.getenv("REDIRECT_URL") or f"{get_base_url()}/oauth/callback"


def _redirect_uri_for_tenant(tenant: Optional[Tenant]) -> str:
    """The canonical Discord callback URI for a resolved tenant, or the platform.

    Built from the tenant's **stored** ``domain`` (never a reflected ``Host``
    header), so the ``/login`` authorize leg and the callback exchange leg
    produce a byte-identical string — which Discord requires — and there is
    nothing attacker-controlled to inject. ``https`` is forced for a real domain;
    only a ``*.localhost`` dev host keeps ``http``. Off a custom domain (platform
    host, or an unresolved tenant) it is the shared platform callback.
    """
    if tenant is not None and tenant.domain:
        return f'{scheme_for_host(tenant.domain)}://{tenant.domain}/oauth/callback'
    return _platform_redirect_uri()


async def _host_mode_tenant() -> Optional[Tenant]:
    """The tenant when this request is on its own custom domain, else None."""
    if not is_host_mode():
        return None
    tid = get_current_tenant_id()
    return await TenantService.get_by_id(tid) if tid is not None else None


async def _callback_tenant(url: str) -> Optional[Tenant]:
    """Resolve the tenant a callback landed on, from its browser URL host.

    ``window.location.href`` is the real address the browser is on (not a
    spoofable header), so its host names the custom domain when the callback ran
    in host mode; resolving that back to the tenant reproduces the exact
    ``redirect_uri`` the ``/login`` leg sent.
    """
    host = normalize_hostname(urlparse(url).netloc)
    if not host:
        return None
    tenant = await TenantService.get_by_domain(host)
    return tenant if (tenant is not None and tenant.is_active) else None


def _safe_next(path) -> str:
    """A safe in-app return path, or ``/``.

    Rejects anything that isn't a plain same-host absolute path so a ``next``
    carried across the handoff can never become an open redirect when fed to
    ``ui.navigate.to``: protocol-relative ``//evil.com``, a backslash form
    ``/\\evil.com`` (browsers normalize ``\\`` to ``/`` per the WHATWG URL spec),
    any control/whitespace char that could smuggle a second target, and auth
    routes (which would loop).
    """
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
        return '/'
    if '\\' in path or any(c in path for c in '\r\n\t '):
        return '/'
    if path.split('?', 1)[0] in AUTH_ROUTES:
        return '/'
    return path


def _bind_commit(secret: str) -> str:
    """The commitment published through the platform hop for a ``/login`` secret."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _handoff_start_url(target_host: str, next_path: str, bind_commit: str = '') -> str:
    """Platform-host ``/oauth/start`` URL that begins a Design B login for a domain."""
    platform = get_platform_host()
    query = urlencode({'host': target_host, 'next': next_path, 'b': bind_commit})
    return f'{scheme_for_host(platform)}://{platform}/oauth/start?{query}'


def _claim_url(target_host: str, token: str) -> str:
    """Custom-domain ``/session/claim`` URL the platform callback hands off to."""
    return f'{scheme_for_host(target_host)}://{target_host}/session/claim?token={quote(token, safe="")}'


def _oauth_url(state: str, redirect_uri: str) -> str:
    """Discord authorize URL for this login attempt, built at request time."""
    explicit = os.getenv("OAUTH_URL")
    if explicit:
        sep = '&' if '?' in explicit else '?'
        return f'{explicit}{sep}state={quote(state, safe="")}'
    params = urlencode({
        'client_id': _client_id or '',
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'identify',
        'state': state,
    })
    return f'https://discord.com/api/oauth2/authorize?{params}'


def _sanitized_return(root_path: str) -> str:
    """Post-login return target for this tenant, from the pending referrer.

    ``AuthMiddleware`` writes ``referrer_path`` (tenant-qualified) when a
    protected page bounces the user to login; :func:`sanitize_return_path`
    accepts it only when it belongs to this tenant, else falls back to home.
    """
    return sanitize_return_path(root_path, app.storage.user.get('referrer_path'))


def _register_discord_connect_callback() -> None:
    """Register the bot-authorization callback, shared by real and mock modes.

    Runs on the bare platform host (no tenant in scope), so the target tenant,
    CSRF state, and return path are carried in the session — set by the tenant
    admin page before redirecting to Discord. DB writes are wrapped in
    ``tenant_scope`` so the STAFF gate and guild stamp land on the right tenant.
    """
    @ui.page('/oauth/discord/connect/callback')
    async def discord_connect_callback(client: Client):
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        expected_state = app.storage.user.pop('discord_connect_state', None)
        tenant_id = app.storage.user.pop('discord_connect_tenant_id', None)
        return_path = app.storage.user.pop('discord_connect_return', None) or '/'
        if not return_path.startswith('/'):
            return_path = '/'

        params = parse_qs(urlparse(url).query)
        if 'error' in params:
            ui.notify('Discord authorization was cancelled or denied.', color='warning')
            ui.navigate.to(return_path)
            return
        returned_state = (params.get('state') or [None])[0]
        if not expected_state or returned_state != expected_state or not tenant_id:
            ui.notify('Connection session expired or invalid. Please try again.', color='warning')
            ui.navigate.to(return_path)
            return

        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        tenant = await TenantService.get_by_id(int(tenant_id))
        if actor is None or tenant is None:
            ui.notify('Session expired. Please try again.', color='warning')
            ui.navigate.to(return_path)
            return

        try:
            with tenant_scope(int(tenant_id)):
                if is_mock_discord():
                    # Dev flow: the guild id is passed straight to the callback
                    # (no real Discord). link_guild still runs the STAFF gate and
                    # the (mock) authority check.
                    guild_raw = (params.get('guild_id') or ['1'])[0]
                    await DiscordLinkService.link_guild(actor, tenant, int(guild_raw))
                else:
                    code = (params.get('code') or [None])[0]
                    if not code:
                        ui.notify('Discord authorization was cancelled.', color='warning')
                        ui.navigate.to(return_path)
                        return
                    await DiscordLinkService.complete_link(actor, tenant, code)
        except (ValueError, PermissionError) as e:
            ui.notify(str(e), color='warning')
            ui.navigate.to(return_path)
            return
        except Exception:
            logger.exception('Discord connect callback failed')
            ui.notify('An unexpected error occurred while connecting Discord.', color='negative')
            ui.navigate.to(return_path)
            return

        ui.notify('Discord server connected.', color='positive')
        ui.navigate.to(return_path)


def create() -> None:
    _register_discord_connect_callback()
    if is_mock_discord():
        _create_mock()
        return

    @ui.page('/login')
    async def login(request: Request, client: Client) -> Optional[RedirectResponse]:
        root_path = request.scope.get('root_path', '') or ''
        if app.storage.user.get('authenticated', False):
            return RedirectResponse(tenant_home(root_path))
        # Pin the post-login return to this tenant before leaving for Discord. In
        # path mode the callback lands on the bare platform host; in host mode it
        # lands on this same custom domain (so the session cookie is visible).
        return_path = _sanitized_return(root_path)
        # Design B (HOST_OAUTH_MODE=handoff): on a custom domain, run OAuth on the
        # platform host and hand the session back, so no per-domain Discord
        # redirect URI is needed. The return path travels in the URL (the platform
        # session can't see this host's cookie), not the session.
        if host_oauth_handoff_enabled() and is_host_mode():
            tenant = await _host_mode_tenant()
            if tenant is not None and tenant.domain:
                # Bind the handoff to *this* browser: keep a secret in this custom
                # domain's session and publish only its hash through the platform
                # hop, so a token minted in another browser can't be replayed here
                # (login-CSRF / forced login).
                bind = secrets.token_urlsafe(32)
                app.storage.user['handoff_bind'] = bind
                return RedirectResponse(
                    _handoff_start_url(tenant.domain, _safe_next(return_path), _bind_commit(bind))
                )
        # Pin the post-login return to this tenant before leaving for Discord. In
        # path mode the callback lands on the bare platform host; in host mode
        # (Design A) it lands on this same custom domain (cookie visible).
        app.storage.user['referrer_path'] = return_path
        # CSRF protection: bind this login attempt to a one-time state token
        # that must come back on the OAuth callback.
        state = secrets.token_urlsafe(32)
        app.storage.user['oauth_state'] = state
        # On a custom domain the whole flow completes on that host, so the
        # redirect_uri points at it — built from the tenant's stored domain.
        tenant = await _host_mode_tenant()
        return RedirectResponse(_oauth_url(state, _redirect_uri_for_tenant(tenant)))

    @ui.page('/logout')
    def logout(request: Request, client: Client) -> Optional[RedirectResponse]:
        root_path = request.scope.get('root_path', '') or ''
        app.storage.user.clear()
        return RedirectResponse(tenant_home(root_path))

    @ui.page('/oauth/callback')
    async def oauth_callback(client: Client):
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        expected_state = app.storage.user.pop('oauth_state', None)
        try:
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)

            if 'error' in params:
                logger.warning('OAuth callback returned error: %s', params.get('error'))
                ui.notify('Discord login was cancelled or denied.', color='warning')
                ui.navigate.to('/login')
                return

            returned_state = (params.get('state') or [None])[0]
            if not expected_state or returned_state != expected_state:
                logger.warning('OAuth state mismatch on callback.')
                ui.notify('Login session expired or invalid. Please try again.', color='warning')
                ui.navigate.to('/login')
                return

            code = (params.get('code') or [None])[0]
            if not code:
                logger.warning('OAuth callback missing authorization code.')
                ui.notify('Login failed. Please try again.', color='warning')
                ui.navigate.to('/login')
                return

            # Rebuild the exact redirect_uri the /login leg sent (Discord requires
            # the exchange to match the authorize call). In host mode the callback
            # ran on the custom domain, so recover the tenant from the browser URL
            # host and build from its stored domain — byte-identical by construction.
            callback_tenant = await _callback_tenant(url)
            redirect_uri = _redirect_uri_for_tenant(callback_tenant)

            # zenora.APIClient is synchronous (requests-based); running these two
            # Discord round-trips inline would block the single shared event loop
            # for every connected user. Offload them to worker threads.
            def _exchange_and_fetch():
                access_token = discordClient.oauth.get_access_token(
                    code, redirect_uri,
                ).access_token
                bearer_client = APIClient(access_token, bearer=True)
                return bearer_client.users.get_current_user()

            current_user = await asyncio.to_thread(_exchange_and_fetch)

            user, _created = await UserService().provision_from_discord_login(
                current_user.id, current_user.username,
            )

            # Deactivated accounts cannot log in (mirrors the REST API's
            # is_active rejection in api/dependencies.py).
            if not user.is_active:
                logger.warning('Inactive account %s attempted web login', current_user.id)
                app.storage.user.clear()
                ui.notify(
                    'This account is inactive. Contact staff if you believe this is a mistake.',
                    color='negative',
                )
                ui.navigate.to('/login')
                return

            # Design B: this login began via /oauth/start on the platform host for
            # a custom domain. Do NOT authenticate the platform-host session —
            # mint a single-use, host-bound token and hand the session over to the
            # target domain's /session/claim, where the cookie belongs.
            handoff_host = app.storage.user.pop('handoff_target_host', None)
            handoff_next = app.storage.user.pop('handoff_next', None)
            handoff_bind_commit = app.storage.user.pop('handoff_bind_commit', None)
            if handoff_host and host_oauth_handoff_enabled():
                token = handoff_service.mint(
                    discord_id=current_user.id,
                    username=current_user.username,
                    avatar=current_user.avatar_url,
                    target_host=handoff_host,
                    next_path=_safe_next(handoff_next or '/'),
                    bind_commit=handoff_bind_commit or None,
                )
                if token:
                    ui.navigate.to(_claim_url(handoff_host, token))
                    return
                # Mint failed (host no longer valid) — fall through to a normal
                # platform-host login rather than stranding the user.

            app.storage.user.update({
                'username': current_user.username,
                'avatar': current_user.avatar_url,
                'authenticated': True,
                'discord_id': current_user.id
            })

            # Map the user's Discord guild roles onto application roles.
            # Self-defensive: never raises, so login is never blocked.
            await DiscordRoleMappingService().sync_user_roles(user)

            # referrer_path was pinned to a tenant-qualified path at /login, so
            # this returns to the originating community even though the callback
            # itself runs on the bare platform host with no tenant in scope.
            referrer = app.storage.user.get('referrer_path', '/')
            if referrer.split('?', 1)[0] in AUTH_ROUTES:
                referrer = '/'
            ui.navigate.to(referrer)
            app.storage.user.pop('referrer_path', None)
        except Exception:
            logger.exception('Unexpected error during OAuth callback')
            ui.notify('An unexpected error occurred during login. Please try again.', color='negative')
            ui.navigate.to('/login')

    @ui.page('/oauth/start')
    async def oauth_start(request: Request, client: Client) -> Optional[RedirectResponse]:
        """Design B entry point (platform host): begin OAuth for a custom domain.

        Records the target host + return path in the platform-host session (the
        custom domain's cookie isn't visible here, so they arrive in the URL) and
        runs the normal Discord flow to the single platform callback. The target
        host is allow-listed against known active tenant domains.
        """
        if not host_oauth_handoff_enabled():
            return RedirectResponse('/login')
        params = request.query_params
        target = normalize_hostname(params.get('host'))
        next_path = _safe_next(params.get('next') or '/')
        # Browser-binding commitment (hex sha256) from the initiating /login;
        # kept opaque here and carried through to the mint.
        bind_commit = (params.get('b') or '')[:64]
        tenant = await TenantService.get_by_domain(target) if target else None
        if tenant is None or not tenant.is_active:
            # Unknown/inactive target host — refuse rather than hand a session to
            # an arbitrary host (open-redirect / session-fixation guard).
            return RedirectResponse('/')
        state = secrets.token_urlsafe(32)
        app.storage.user['oauth_state'] = state
        app.storage.user['handoff_target_host'] = target
        app.storage.user['handoff_next'] = next_path
        app.storage.user['handoff_bind_commit'] = bind_commit
        return RedirectResponse(_oauth_url(state, _platform_redirect_uri()))

    @ui.page('/session/claim')
    async def session_claim(client: Client) -> None:
        """Design B claim (custom domain): validate the handoff and set the session."""
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        parsed = urlparse(url)
        token = (parse_qs(parsed.query).get('token') or [None])[0]
        request_host = normalize_hostname(parsed.netloc)
        # Consume the browser-binding secret this domain's /login stashed.
        bind = app.storage.user.pop('handoff_bind', None)
        payload = handoff_service.claim(token, request_host) if (token and request_host) else None
        if payload is None:
            ui.notify('Login link expired or already used. Please try again.', color='warning')
            ui.navigate.to('/login')
            return
        # Login-CSRF guard: the token must have been minted for a login *this*
        # browser initiated — i.e. the secret behind the committed hash must be
        # present in this domain's session. A token delivered to a different
        # browser (which lacks the secret) is rejected here.
        expected = payload.get('bind_commit')
        if not (expected and isinstance(bind, str)
                and hmac.compare_digest(expected, _bind_commit(bind))):
            logger.warning('OAuth handoff browser-binding mismatch on %r', request_host)
            ui.notify('Login link is not valid for this browser. Please try again.', color='warning')
            ui.navigate.to('/login')
            return
        # Re-check the account is still active (it was provisioned at mint time,
        # but could have been deactivated inside the short TTL window).
        user = await get_user_from_discord_id(payload['discord_id'])
        if user is None:
            app.storage.user.clear()
            ui.notify('This account is inactive. Contact staff if this is a mistake.', color='negative')
            ui.navigate.to('/login')
            return
        app.storage.user.update({
            'username': payload.get('username'),
            'avatar': payload.get('avatar'),
            'authenticated': True,
            'discord_id': payload['discord_id'],
        })
        # Self-defensive; never blocks login.
        await DiscordRoleMappingService().sync_user_roles(user)
        ui.navigate.to(_safe_next(payload.get('next') or '/'))


def _login_as(user: User) -> None:
    """Populate app.storage.user the same way the real OAuth callback does."""
    app.storage.user.update({
        'username': user.username,
        'avatar': None,
        'authenticated': True,
        'discord_id': user.discord_id,
    })
    referrer = app.storage.user.get('referrer_path', '/')
    if referrer.split('?', 1)[0] in AUTH_ROUTES:
        referrer = '/'
    app.storage.user.pop('referrer_path', None)
    ui.navigate.to(referrer)


def _create_mock() -> None:
    """Register the MOCK_DISCORD replacements for the three auth routes.

    Turns ``/login`` into a public user-picker that can impersonate any user or
    mint a new one. Never active in production (``is_mock_discord`` refuses it).
    """
    @ui.page('/login')
    async def mock_login(request: Request, client: Client):
        root_path = request.scope.get('root_path', '') or ''
        if app.storage.user.get('authenticated', False):
            ui.navigate.to(tenant_home(root_path))
            return
        # Pin the post-login return to this tenant (mirrors the real flow) so a
        # picked user lands on this community's home, not the platform landing.
        app.storage.user['referrer_path'] = _sanitized_return(root_path)

        ui.page_title('Mock Discord Login')

        with ui.column().classes('w-full max-w-4xl mx-auto p-4 gap-4'):
            ui.label('Mock Discord Login').classes('text-2xl font-bold')
            ui.label(
                'MOCK_DISCORD is enabled. Pick an existing user to impersonate, '
                'or create a new one. No real Discord OAuth is performed.'
            ).classes('text-sm text-gray-600')

            with ui.card().classes('w-full'):
                ui.label('Existing users').classes('text-lg font-semibold')

                filter_input = ui.input(label='Filter by username or discord_id').classes('w-full')

                users = await User.all().order_by('username').prefetch_related(
                    'roles', 'admin_tournaments', 'crew_coordinated_tournaments',
                )

                def format_roles(u: User) -> str:
                    # Dev impersonation picker: this is a global (pre-tenant) view,
                    # so roles span every community — dedupe by label so the same
                    # role held in several tenants shows once, not "Staff, Staff".
                    seen = set()
                    labels = []
                    for r in u.roles:
                        label = r.role.value.replace('_', ' ').title()
                        if label not in seen:
                            seen.add(label)
                            labels.append(label)
                    if len(u.admin_tournaments):
                        labels.append(f'TA({len(u.admin_tournaments)})')
                    if len(u.crew_coordinated_tournaments):
                        labels.append(f'CC({len(u.crew_coordinated_tournaments)})')
                    return ', '.join(labels) or '-'

                rows = [
                    {
                        'id': u.id,
                        'username': u.username,
                        'display_name': u.display_name or '',
                        'discord_id': str(u.discord_id),
                        'roles': format_roles(u),
                    }
                    for u in users
                ]
                user_by_id = {u.id: u for u in users}

                columns = [
                    {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left', 'sortable': True},
                    {'name': 'display_name', 'label': 'Display Name', 'field': 'display_name', 'align': 'left'},
                    {'name': 'discord_id', 'label': 'Discord ID', 'field': 'discord_id', 'align': 'left'},
                    {'name': 'roles', 'label': 'Roles', 'field': 'roles', 'align': 'left'},
                    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
                ]

                table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full')
                table.add_slot('body-cell-actions', f'<q-td :props="props">{_LOGIN_ACTION}</q-td>')
                enable_mobile_grid(table, columns, actions=_LOGIN_ACTION)

                def on_login_as(e):
                    user_id = e.args.get('id')
                    user = user_by_id.get(user_id)
                    if user is None:
                        ui.notify('User no longer exists', color='negative')
                        return
                    _login_as(user)

                table.on('login_as', on_login_as)

                def apply_filter(_=None):
                    needle = (filter_input.value or '').lower().strip()
                    if not needle:
                        table.rows = rows
                    else:
                        table.rows = [
                            r for r in rows
                            if needle in r['username'].lower()
                            or needle in r['display_name'].lower()
                            or needle in r['discord_id']
                        ]
                    table.update()

                filter_input.on('update:model-value', apply_filter)

            with ui.card().classes('w-full'):
                ui.label('Create new user').classes('text-lg font-semibold')

                username_input = ui.input(label='Username').classes('w-full')
                display_name_input = ui.input(label='Display name (optional)').classes('w-full')
                discord_id_input = ui.number(
                    label='Discord ID',
                    value=random.randint(10_000_000_000_000_000, 99_999_999_999_999_999),
                    format='%.0f',
                ).classes('w-full')
                role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
                role_select = ui.select(
                    options=role_options,
                    value=[],
                    label='Roles',
                    multiple=True,
                ).props('use-chips').classes('w-full')

                async def create_user():
                    username = (username_input.value or '').strip()
                    if not username:
                        ui.notify('Username is required', color='warning')
                        return
                    try:
                        discord_id = int(discord_id_input.value)
                    except (TypeError, ValueError):
                        ui.notify('Discord ID must be numeric', color='warning')
                        return
                    if await User.exists(discord_id=discord_id):
                        ui.notify('A user with that discord_id already exists', color='warning')
                        return
                    display_name = (display_name_input.value or '').strip() or None
                    user = await UserService().create_mock_login_user(
                        discord_id=discord_id,
                        username=username,
                        display_name=display_name,
                        role_values=role_select.value or [],
                    )
                    ui.notify(f'Created user {user.username} (#{user.discord_id})', color='positive')
                    _login_as(user)

                ui.button('Create and log in', color='green', on_click=create_user)

    @ui.page('/logout')
    def mock_logout(request: Request, client: Client) -> Optional[RedirectResponse]:
        root_path = request.scope.get('root_path', '') or ''
        app.storage.user.clear()
        return RedirectResponse(tenant_home(root_path))

    @ui.page('/oauth/callback')
    def mock_oauth_callback(request: Request, client: Client) -> RedirectResponse:
        root_path = request.scope.get('root_path', '') or ''
        return RedirectResponse(tenant_home(root_path))
