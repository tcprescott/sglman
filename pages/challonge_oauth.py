"""Challonge OAuth pages.

Two flows share one registered OAuth app:

* **Service account** (``/challonge/connect``): a STAFF member authorizes the
  shared Wizzrobe Challonge account once. Tokens are stored centrally in
  :class:`ChallongeConnection`.
* **Player identity** (``/challonge/link``): a player authorizes with scope
  ``me`` so we can record their verified Challonge account id/username. The
  token is used once and discarded.

Both flows share the single registered redirect URI
``/challonge/oauth/callback`` — Challonge OAuth apps validate against one URI —
and the pending CSRF ``state`` identifies which flow a callback completes.

The CSRF ``state`` + JS-read-callback structure mirrors ``pages/auth.py``.
When ``MOCK_CHALLONGE`` is enabled the initiation pages complete the flow
locally without contacting Challonge.
"""

import logging
import secrets

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.services.auth_service import AuthService, get_user_from_discord_id
from application.services.challonge_service import ChallongeService
from application.services.feature_flag_service import FeatureFlagService
from application.utils.mocks.mock_challonge import is_mock_challonge
from models import FeatureFlag
from pages._oauth_link import (
    LinkHandoffProvider,
    handle_link_handoff_callback,
    maybe_start_link_handoff,
    platform_link_redirect,
    read_callback_code,
    register_link_handoff_provider,
    returned_state,
)
from theme.notice import stash_notice

logger = logging.getLogger(__name__)

_PROVIDER_LABEL = 'Challonge'
_PROVIDER_KEY = 'challonge'

_ADMIN_RETURN = '/admin/challonge'
_PROFILE_RETURN = '/home/profile'


async def _challonge_live() -> bool:
    """Whether this community has the Challonge feature.

    These are bare ``@ui.page`` routes (they serve cross-host OAuth legs, so they
    cannot use ``@protected_page``'s ``feature=`` gate), which leaves them
    reachable by URL after the profile/admin entry points are hidden. Without
    this the mock-mode branches would raise ``FeatureDisabledError`` out of a page
    handler, and the real flow would send the player to Challonge's consent
    screen only to fail on the way back.
    """
    return await FeatureFlagService().is_enabled(FeatureFlag.CHALLONGE)


async def _player_handoff_exchange(code: str) -> dict:
    """Exchange a player's code for the public Challonge identity to hand across."""
    service = ChallongeService()
    me = await service.exchange_player_code(code)
    return {'user_id': me['user_id'], 'name': me.get('username')}


async def _player_handoff_record(user, data: dict) -> None:
    await ChallongeService().record_player_link(
        user, data['user_id'], data.get('name'), actor=user,
    )


def create() -> None:
    # Only the player-identity link uses the cross-host handoff (it carries the
    # public Challonge id/name, like racetime/Twitch). The STAFF service-connect
    # keeps the platform-host detour: it writes a tenant-scoped connection holding
    # real OAuth tokens, so it stays on the main site rather than crossing hosts.
    register_link_handoff_provider(LinkHandoffProvider(
        key=_PROVIDER_KEY,
        label=_PROVIDER_LABEL,
        profile_return=_PROFILE_RETURN,
        authorize_url=ChallongeService.player_authorize_url,
        exchange=_player_handoff_exchange,
        record=_player_handoff_record,
        is_mock=is_mock_challonge,
        callback_route='/challonge/oauth/callback',
    ))

    @ui.page('/challonge/connect')
    async def challonge_connect(request: Request) -> RedirectResponse:
        # Custom domain: the shared callback is on the platform host, so bounce
        # there rather than silently failing to complete the connection.
        detour = await platform_link_redirect(_ADMIN_RETURN)
        if detour:
            return RedirectResponse(detour)
        # Initiation runs with tenant context; the shared callback lands on the
        # bare platform host, so pin the tenant-qualified return here.
        root_path = request.scope.get('root_path', '') or ''
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse(f'{root_path}/login')
        if not await AuthService.is_staff(user):
            return RedirectResponse(f'{root_path}/admin')
        if not await _challonge_live():
            return RedirectResponse(f'{root_path}/admin')
        if is_mock_challonge():
            service = ChallongeService()
            payload = await service.exchange_service_code('mock')
            await service.save_service_connection(payload, user)
            return RedirectResponse(f'{root_path}{_ADMIN_RETURN}')
        state = secrets.token_urlsafe(32)
        app.storage.user['challonge_service_state'] = state
        app.storage.user['challonge_service_return'] = f'{root_path}{_ADMIN_RETURN}'
        return RedirectResponse(ChallongeService.service_authorize_url(state))

    @ui.page('/challonge/oauth/callback')
    async def challonge_callback(client: Client) -> None:
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        # Cross-host player-link handoff leg (platform host): exchange + mint +
        # hand the verified identity back to the custom domain's /oauth/link/claim.
        if await handle_link_handoff_callback(url):
            return
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        service_state = app.storage.user.pop('challonge_service_state', None)
        player_state = app.storage.user.pop('challonge_player_state', None)
        service_return = app.storage.user.pop('challonge_service_return', None) or _ADMIN_RETURN
        player_return = app.storage.user.pop('challonge_player_return', None) or _PROFILE_RETURN
        if user is None:
            # Not authenticated: bounce to the originating tenant's login rather
            # than the platform host (the returns carry the /t/<slug> prefix).
            stash_notice('Please log in and try linking again.', color='warning')
            ui.navigate.to(service_return if service_state is not None else player_return)
            return
        # One registered redirect URI serves two flows, so the pending CSRF state
        # says which one this callback completes. Four outcomes, named — the old
        # two-branch guess fell through to the service flow whenever *neither*
        # state was pending (a replay, a stale tab, a hand-typed URL), and that
        # flow returns to /admin/challonge, so a player was answered with a 403
        # about the admin area.
        state = returned_state(url)
        if player_state is not None and state == player_state:
            await _finish_player_link(
                user, read_callback_code(url, player_state, _PROVIDER_LABEL), player_return,
            )
        elif service_state is not None and state == service_state:
            await _finish_service_connect(
                user, read_callback_code(url, service_state, _PROVIDER_LABEL), service_return,
            )
        elif (player_state is None) != (service_state is None):
            # Exactly one flow pending and the state did not match it: a provider
            # redirect carrying an error and no usable state. Complete that flow
            # with no code so it reports cancelled/failed and returns to its own
            # path — what the old `or service_state is None` clause was for.
            if player_state is not None:
                await _finish_player_link(user, None, player_return)
            else:
                await _finish_service_connect(user, None, service_return)
        else:
            # Nothing pending, or both pending and neither matched: this callback
            # belongs to neither flow, so complete neither. Return to the profile,
            # never the admin area — every actor can reach their own profile, and
            # a staff member replaying a service-connect callback lands there with
            # an accurate message instead of a player hitting a 403. With no
            # markers there is no tenant to prefix, so in path mode the fallback
            # resolves on the platform host as the community picker — with the
            # message, which is the honest answer for a callback that names no
            # community.
            stash_notice(
                f"That {_PROVIDER_LABEL} link didn't complete. "
                f'Try again from your profile.', color='warning',
            )
            ui.navigate.to(player_return)

    @ui.page('/challonge/link')
    async def challonge_link(request: Request) -> RedirectResponse:
        root_path = request.scope.get('root_path', '') or ''
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse(f'{root_path}/login')
        if not await _challonge_live():
            return RedirectResponse(f'{root_path}{_PROFILE_RETURN}')
        # Custom domain + handoff: run the player OAuth on the platform host and
        # hand the verified identity back here (where the session/tenant live).
        # Tried before the mock short-circuit so the handoff is reachable under
        # MOCK_CHALLONGE; returns None in path mode and with handoff off.
        handoff = await maybe_start_link_handoff(_PROVIDER_KEY, f'{root_path}{_PROFILE_RETURN}')
        if handoff is not None:
            return handoff
        if is_mock_challonge():
            # Mock mode records the link here rather than in the callback, so this
            # page owns its outcome. A bare call answered an already-linked id
            # with a 500.
            service = ChallongeService()
            me = await service.exchange_player_code('mock')
            try:
                await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
                stash_notice(f'{_PROVIDER_LABEL} account linked.', color='positive')
            except ValueError as e:
                stash_notice(str(e), color='warning')
            except Exception:  # noqa: BLE001 - log detail server-side, show generic message
                logger.exception('Challonge mock player linking failed')
                stash_notice(f'Could not link {_PROVIDER_LABEL}. Please try again.', color='negative')
            return RedirectResponse(f'{root_path}{_PROFILE_RETURN}')
        # Custom domain + Design A (handoff off): bounce to the platform-host
        # path-mode surface. No-op in path mode / platform surface.
        detour = await platform_link_redirect(_PROFILE_RETURN)
        if detour:
            return RedirectResponse(detour)
        state = secrets.token_urlsafe(32)
        app.storage.user['challonge_player_state'] = state
        app.storage.user['challonge_player_return'] = f'{root_path}{_PROFILE_RETURN}'
        return RedirectResponse(ChallongeService.player_authorize_url(state))


async def _finish_service_connect(user, code: str | None, return_path: str) -> None:
    if code is None:
        stash_notice('Challonge connection was cancelled or failed.', color='warning')
    else:
        try:
            service = ChallongeService()
            payload = await service.exchange_service_code(code)
            await service.save_service_connection(payload, user)
            stash_notice('Challonge account connected.', color='positive')
        except ValueError as e:
            stash_notice(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('Challonge service connection failed')
            stash_notice('Could not connect Challonge. Please try again.', color='negative')
    ui.navigate.to(return_path)


async def _finish_player_link(user, code: str | None, return_path: str) -> None:
    if code is None:
        stash_notice('Challonge linking was cancelled or failed.', color='warning')
    else:
        try:
            service = ChallongeService()
            me = await service.exchange_player_code(code)
            await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
            stash_notice('Challonge account linked.', color='positive')
        except ValueError as e:
            stash_notice(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('Challonge player linking failed')
            stash_notice('Could not link Challonge. Please try again.', color='negative')
    ui.navigate.to(return_path)
