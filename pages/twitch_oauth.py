"""Twitch OAuth pages.

A single flow: a logged-in user authorizes with Twitch so we can record their
verified Twitch identity (id / login / display name). The token is used once and
discarded.

The CSRF ``state`` + JS-read-callback structure mirrors ``pages/auth.py`` and
``pages/challonge_oauth.py``. When ``MOCK_TWITCH`` is enabled the initiation page
completes the flow locally without contacting Twitch.
"""

import logging
import secrets
from urllib.parse import parse_qs, urlparse

from nicegui import Client, app, ui
from starlette.responses import RedirectResponse

from application.services.auth_service import get_user_from_discord_id
from application.services.twitch_service import TwitchService
from application.utils.mock_twitch import is_mock_twitch

logger = logging.getLogger(__name__)

_PROFILE_RETURN = '/?tab=Profile'


def create() -> None:
    @ui.page('/twitch/link')
    async def twitch_link() -> RedirectResponse:
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse('/login')
        if is_mock_twitch():
            service = TwitchService()
            me = await service.exchange_player_code('mock')
            await service.record_player_link(
                user, me['user_id'], me.get('display_name') or me.get('username'), actor=user,
            )
            return RedirectResponse(_PROFILE_RETURN)
        state = secrets.token_urlsafe(32)
        app.storage.user['twitch_link_state'] = state
        return RedirectResponse(TwitchService.player_authorize_url(state))

    @ui.page('/twitch/oauth/callback')
    async def twitch_callback(client: Client) -> None:
        await client.connected()
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        expected_state = app.storage.user.pop('twitch_link_state', None)
        url = await ui.run_javascript('window.location.href')
        if user is None:
            ui.navigate.to('/login')
            return
        await _finish_link(user, _read_callback_code(url, expected_state))


async def _finish_link(user, code: str | None) -> None:
    if code is None:
        ui.notify('Twitch linking was cancelled or failed.', color='warning')
    else:
        try:
            service = TwitchService()
            me = await service.exchange_player_code(code)
            await service.record_player_link(
                user, me['user_id'], me.get('display_name') or me.get('username'), actor=user,
            )
            ui.notify('Twitch account linked.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('Twitch linking failed')
            ui.notify('Could not link Twitch. Please try again.', color='negative')
    ui.navigate.to(_PROFILE_RETURN)


def _read_callback_code(url: str, expected_state: str | None):
    """Validate the OAuth callback URL and return the authorization code or None."""
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    if 'error' in params:
        logger.warning('Twitch OAuth callback returned error: %s', params.get('error'))
        return None
    returned_state = (params.get('state') or [None])[0]
    if not expected_state or returned_state != expected_state:
        logger.warning('Twitch OAuth state mismatch on callback.')
        return None
    return (params.get('code') or [None])[0]
