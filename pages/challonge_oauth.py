"""Challonge OAuth pages.

Two flows share one registered OAuth app:

* **Service account** (``/challonge/connect``): a STAFF member authorizes the
  shared SGL Challonge account once. Tokens are stored centrally in
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
from application.utils.mock_challonge import is_mock_challonge
from pages._oauth_link import platform_link_redirect, read_callback_code, returned_state

logger = logging.getLogger(__name__)

_PROVIDER_LABEL = 'Challonge'

_ADMIN_RETURN = '/admin/challonge'
_PROFILE_RETURN = '/home/profile'


def create() -> None:
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
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        service_state = app.storage.user.pop('challonge_service_state', None)
        player_state = app.storage.user.pop('challonge_player_state', None)
        service_return = app.storage.user.pop('challonge_service_return', None) or _ADMIN_RETURN
        player_return = app.storage.user.pop('challonge_player_return', None) or _PROFILE_RETURN
        url = await ui.run_javascript('window.location.href')
        if user is None:
            # Not authenticated: bounce to the originating tenant's login rather
            # than the platform host (the returns carry the /t/<slug> prefix).
            ui.navigate.to(service_return if service_state is not None else player_return)
            return
        # The pending CSRF state tells us which flow this single callback completes.
        state = returned_state(url)
        if player_state is not None and (state == player_state or service_state is None):
            await _finish_player_link(
                user, read_callback_code(url, player_state, _PROVIDER_LABEL), player_return,
            )
        else:
            await _finish_service_connect(
                user, read_callback_code(url, service_state, _PROVIDER_LABEL), service_return,
            )

    @ui.page('/challonge/link')
    async def challonge_link(request: Request) -> RedirectResponse:
        detour = await platform_link_redirect(_PROFILE_RETURN)
        if detour:
            return RedirectResponse(detour)
        root_path = request.scope.get('root_path', '') or ''
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse(f'{root_path}/login')
        if is_mock_challonge():
            service = ChallongeService()
            me = await service.exchange_player_code('mock')
            await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
            return RedirectResponse(f'{root_path}{_PROFILE_RETURN}')
        state = secrets.token_urlsafe(32)
        app.storage.user['challonge_player_state'] = state
        app.storage.user['challonge_player_return'] = f'{root_path}{_PROFILE_RETURN}'
        return RedirectResponse(ChallongeService.player_authorize_url(state))


async def _finish_service_connect(user, code: str | None, return_path: str) -> None:
    if code is None:
        ui.notify('Challonge connection was cancelled or failed.', color='warning')
    else:
        try:
            service = ChallongeService()
            payload = await service.exchange_service_code(code)
            await service.save_service_connection(payload, user)
            ui.notify('Challonge account connected.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('Challonge service connection failed')
            ui.notify('Could not connect Challonge. Please try again.', color='negative')
    ui.navigate.to(return_path)


async def _finish_player_link(user, code: str | None, return_path: str) -> None:
    if code is None:
        ui.notify('Challonge linking was cancelled or failed.', color='warning')
    else:
        try:
            service = ChallongeService()
            me = await service.exchange_player_code(code)
            await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
            ui.notify('Challonge account linked.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('Challonge player linking failed')
            ui.notify('Could not link Challonge. Please try again.', color='negative')
    ui.navigate.to(return_path)
