"""Challonge OAuth pages.

Two flows share one registered OAuth app:

* **Service account** (``/challonge/connect`` → ``/challonge/oauth/callback``):
  a STAFF member authorizes the shared SGL Challonge account once. Tokens are
  stored centrally in :class:`ChallongeConnection`.
* **Player identity** (``/challonge/link`` → ``/challonge/link/callback``): a
  player authorizes with scope ``me`` so we can record their verified Challonge
  account id/username. The token is used once and discarded.

The CSRF ``state`` + JS-read-callback structure mirrors ``middleware/auth.py``.
When ``MOCK_CHALLONGE`` is enabled the initiation pages complete the flow
locally without contacting Challonge.
"""

import logging
import secrets
from urllib.parse import parse_qs, urlparse

from nicegui import Client, app, ui
from starlette.responses import RedirectResponse

from application.services.auth_service import AuthService, current_user_from_storage
from application.services.challonge_service import ChallongeService
from application.utils.mock_challonge import is_mock_challonge

logger = logging.getLogger(__name__)

_ADMIN_RETURN = '/admin?tab=Challonge'
_PROFILE_RETURN = '/?tab=Profile'


def create() -> None:
    @ui.page('/challonge/connect')
    async def challonge_connect() -> RedirectResponse:
        user = await current_user_from_storage()
        if user is None:
            return RedirectResponse('/login')
        if not await AuthService.is_staff(user):
            return RedirectResponse('/admin')
        if is_mock_challonge():
            service = ChallongeService()
            payload = await service.exchange_service_code('mock')
            await service.save_service_connection(payload, user)
            return RedirectResponse(_ADMIN_RETURN)
        state = secrets.token_urlsafe(32)
        app.storage.user['challonge_service_state'] = state
        return RedirectResponse(ChallongeService.service_authorize_url(state))

    @ui.page('/challonge/oauth/callback')
    async def challonge_service_callback(client: Client) -> None:
        await client.connected()
        user = await current_user_from_storage()
        expected_state = app.storage.user.pop('challonge_service_state', None)
        code = _read_callback_code(await ui.run_javascript('window.location.href'), expected_state)
        if user is None:
            ui.navigate.to('/login')
            return
        if code is None:
            ui.notify('Challonge connection was cancelled or failed.', color='warning')
            ui.navigate.to(_ADMIN_RETURN)
            return
        try:
            service = ChallongeService()
            payload = await service.exchange_service_code(code)
            await service.save_service_connection(payload, user)
            ui.notify('Challonge account connected.', color='positive')
        except Exception as e:  # noqa: BLE001 - surface any failure to the user
            logger.exception('Challonge service connection failed')
            ui.notify(f'Could not connect Challonge: {e}', color='negative')
        ui.navigate.to(_ADMIN_RETURN)

    @ui.page('/challonge/link')
    async def challonge_link() -> RedirectResponse:
        user = await current_user_from_storage()
        if user is None:
            return RedirectResponse('/login')
        if is_mock_challonge():
            service = ChallongeService()
            me = await service.exchange_player_code('mock')
            await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
            return RedirectResponse(_PROFILE_RETURN)
        state = secrets.token_urlsafe(32)
        app.storage.user['challonge_player_state'] = state
        return RedirectResponse(ChallongeService.player_authorize_url(state))

    @ui.page('/challonge/link/callback')
    async def challonge_link_callback(client: Client) -> None:
        await client.connected()
        user = await current_user_from_storage()
        expected_state = app.storage.user.pop('challonge_player_state', None)
        code = _read_callback_code(await ui.run_javascript('window.location.href'), expected_state)
        if user is None:
            ui.navigate.to('/login')
            return
        if code is None:
            ui.notify('Challonge linking was cancelled or failed.', color='warning')
            ui.navigate.to(_PROFILE_RETURN)
            return
        try:
            service = ChallongeService()
            me = await service.exchange_player_code(code)
            await service.record_player_link(user, me['user_id'], me.get('username'), actor=user)
            ui.notify('Challonge account linked.', color='positive')
        except Exception as e:  # noqa: BLE001 - surface any failure to the user
            logger.exception('Challonge player linking failed')
            ui.notify(f'Could not link Challonge: {e}', color='negative')
        ui.navigate.to(_PROFILE_RETURN)


def _read_callback_code(url: str, expected_state: str | None):
    """Validate the OAuth callback URL and return the authorization code or None."""
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    if 'error' in params:
        logger.warning('Challonge OAuth callback returned error: %s', params.get('error'))
        return None
    returned_state = (params.get('state') or [None])[0]
    if not expected_state or returned_state != expected_state:
        logger.warning('Challonge OAuth state mismatch on callback.')
        return None
    return (params.get('code') or [None])[0]
