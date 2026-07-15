"""racetime.gg OAuth pages.

A single flow: a logged-in user authorizes with racetime.gg (read scope) so we
can record their verified racetime identity (id / name). The token is used once
and discarded.

The CSRF ``state`` + JS-read-callback structure mirrors ``pages/auth.py`` and
``pages/twitch_oauth.py``. When ``MOCK_RACETIME`` is enabled the initiation page
completes the flow locally without contacting racetime.gg.
"""

import logging
import secrets
from urllib.parse import parse_qs, urlparse

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.services.auth_service import get_user_from_discord_id
from application.services.racetime_service import RacetimeService
from application.utils.mock_racetime import is_mock_racetime

logger = logging.getLogger(__name__)

_PROFILE_RETURN = '/home/profile'


def create() -> None:
    @ui.page('/racetime/link')
    async def racetime_link(request: Request) -> RedirectResponse:
        # Initiation runs with tenant context; the callback lands on the bare
        # platform host, so pin the tenant-qualified return here.
        root_path = request.scope.get('root_path', '') or ''
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            return RedirectResponse(f'{root_path}/login')
        if is_mock_racetime():
            service = RacetimeService()
            me = await service.exchange_player_code('mock')
            await service.record_player_link(
                user, me['user_id'], me.get('username'), actor=user,
            )
            return RedirectResponse(f'{root_path}{_PROFILE_RETURN}')
        state = secrets.token_urlsafe(32)
        app.storage.user['racetime_link_state'] = state
        app.storage.user['racetime_link_return'] = f'{root_path}{_PROFILE_RETURN}'
        return RedirectResponse(RacetimeService.player_authorize_url(state))

    @ui.page('/racetime/oauth/callback')
    async def racetime_callback(client: Client) -> None:
        await client.connected()
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        expected_state = app.storage.user.pop('racetime_link_state', None)
        return_path = app.storage.user.pop('racetime_link_return', None) or _PROFILE_RETURN
        url = await ui.run_javascript('window.location.href')
        if user is None:
            ui.navigate.to(return_path)
            return
        await _finish_link(user, _read_callback_code(url, expected_state), return_path)


async def _finish_link(user, code: str | None, return_path: str) -> None:
    if code is None:
        ui.notify('racetime linking was cancelled or failed.', color='warning')
    else:
        try:
            service = RacetimeService()
            me = await service.exchange_player_code(code)
            await service.record_player_link(
                user, me['user_id'], me.get('username'), actor=user,
            )
            ui.notify('racetime account linked.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        except Exception:  # noqa: BLE001 - log detail server-side, show generic message
            logger.exception('racetime linking failed')
            ui.notify('Could not link racetime. Please try again.', color='negative')
    ui.navigate.to(return_path)


def _read_callback_code(url: str, expected_state: str | None):
    """Validate the OAuth callback URL and return the authorization code or None."""
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    if 'error' in params:
        logger.warning('racetime OAuth callback returned error: %s', params.get('error'))
        return None
    returned_state = (params.get('state') or [None])[0]
    if not expected_state or returned_state != expected_state:
        logger.warning('racetime OAuth state mismatch on callback.')
        return None
    return (params.get('code') or [None])[0]
