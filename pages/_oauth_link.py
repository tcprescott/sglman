"""Shared scaffolding for OAuth identity-link pages.

racetime.gg and Twitch each expose the same single-flow link: a logged-in user
authorizes with the provider (read scope), we exchange the returned code once for
their verified identity and record it, then discard the token. The two page
modules were line-for-line identical except the service class, storage keys,
route paths, and user-facing strings; :func:`register_identity_link_pages`
parameterises that shape.

``challonge_oauth.py`` has its own two-flow (service + player) page registration
because its single callback is shared between the two flows, but it reuses the
:func:`read_callback_code` / :func:`returned_state` helpers here so the
callback-URL parsing lives in exactly one place.
"""

import logging
import secrets
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.services.auth_service import get_user_from_discord_id
from models import User

logger = logging.getLogger(__name__)

__all__ = [
    'IdentityLinkFlow',
    'register_identity_link_pages',
    'read_callback_code',
    'returned_state',
]


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


@dataclass(frozen=True)
class IdentityLinkFlow:
    """Provider-specific configuration for a single-flow identity link.

    ``provider_label`` is woven verbatim into log lines and toasts (``'racetime'``
    / ``'Twitch'``), so it doubles as the display name in messages.
    """

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


def register_identity_link_pages(flow: IdentityLinkFlow) -> None:
    """Register the ``/<provider>/link`` initiation + callback pages for ``flow``."""

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
        state = secrets.token_urlsafe(32)
        app.storage.user[flow.state_key] = state
        app.storage.user[flow.return_key] = f'{root_path}{flow.profile_return}'
        return RedirectResponse(flow.authorize_url(state))

    @ui.page(flow.callback_route)
    async def callback(client: Client) -> None:
        await client.connected()
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        expected_state = app.storage.user.pop(flow.state_key, None)
        return_path = app.storage.user.pop(flow.return_key, None) or flow.profile_return
        url = await ui.run_javascript('window.location.href')
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
