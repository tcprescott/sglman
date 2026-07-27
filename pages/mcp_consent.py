"""The OAuth consent screen for MCP clients.

A bespoke ``@ui.page`` rather than ``@protected_page``, for a structural reason:
every ``@protected_page`` is a *tenant* page and 404s when reached with no
tenant, but an MCP grant is deliberately platform-wide — it authenticates a
person, not a membership. So this route lives alongside the other tenant-less
OAuth pages and opts into authentication by registering itself in
``protected_routes`` directly, which is what makes ``AuthMiddleware`` bounce an
anonymous visitor to ``/login`` and back here afterwards.

There is no community picker. The issued token carries no tenant; each MCP tool
call names its own community and is authorized against the user's role there.
Asking here would imply a scoping the credential does not actually have.
"""

import logging
from urllib.parse import urlencode

from nicegui import app, ui
from starlette.responses import RedirectResponse

from application.errors import NotFoundError
from application.services import McpAuthService
from application.services.auth_service import get_user_from_discord_id
from middleware.auth import protected_routes

logger = logging.getLogger(__name__)

CONSENT_PATH = '/oauth/mcp/consent'

# What the caller is actually agreeing to. Deliberately concrete: "read-only"
# is only reassuring if it says what can be read.
_GRANTS = [
    ('visibility', 'See the communities you belong to and your roles in them'),
    ('event', 'Read tournaments, matches, schedules and results'),
    ('groups', 'Read crew and volunteer assignments'),
    ('history', 'Read audit history, where your role already allows it'),
]


def _deny_redirect(redirect_uri: str, state: str | None) -> RedirectResponse:
    """Send the standard OAuth denial back to the client.

    A denial has to reach the client as ``access_denied`` rather than as a dead
    end, or the client sits waiting on a callback that never arrives.
    """
    params = {'error': 'access_denied', 'error_description': 'The user denied the request.'}
    if state:
        params['state'] = state
    sep = '&' if '?' in redirect_uri else '?'
    return RedirectResponse(f'{redirect_uri}{sep}{urlencode(params)}', status_code=302)


def create() -> None:
    """Register the consent page."""

    # Opt into AuthMiddleware's redirect-to-login without becoming a tenant page.
    protected_routes.add(CONSENT_PATH)

    @ui.page(CONSENT_PATH)
    async def mcp_consent(txn: str = ''):
        service = McpAuthService()
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if user is None:
            # AuthMiddleware normally prevents this; if the session is half-built
            # the safe move is to send them to sign in rather than render a
            # consent screen with no identity behind it.
            return RedirectResponse('/login', status_code=302)

        try:
            pending = service.get_pending(txn)
        except NotFoundError as exc:
            with ui.column().classes('page-container'):
                ui.label('Authorization request expired').classes('section-title')
                ui.label(str(exc)).classes('text-muted')
            return None

        client = await service.get_client(pending.client_id)
        client_name = client.client_name if client else 'An MCP client'

        async def approve() -> None:
            try:
                code, redirect_uri, state = await service.approve(txn, user)
            except (ValueError, NotFoundError) as exc:
                ui.notify(str(exc), color='warning')
                return
            params = {'code': code}
            if state:
                params['state'] = state
            sep = '&' if '?' in redirect_uri else '?'
            ui.navigate.to(f'{redirect_uri}{sep}{urlencode(params)}')

        def deny() -> None:
            service.discard_pending(txn)
            sep = '&' if '?' in pending.redirect_uri else '?'
            params = {
                'error': 'access_denied',
                'error_description': 'The user denied the request.',
            }
            if pending.state:
                params['state'] = pending.state
            ui.navigate.to(f'{pending.redirect_uri}{sep}{urlencode(params)}')

        with ui.column().classes('page-container items-center'):
            with ui.card().classes('card-full-width').style('max-width: 520px;'):
                ui.label('Connect to Wizzrobe').classes('section-title')
                ui.label(
                    f'{client_name} wants to access Wizzrobe as '
                    f'{user.preferred_name}.'
                ).classes('text-body1')
                ui.separator()
                ui.label('It will be able to:').classes('text-weight-medium q-mt-sm')
                for icon, text in _GRANTS:
                    with ui.row().classes('row-centered no-wrap'):
                        ui.icon(icon).classes('text-primary')
                        ui.label(text).classes('text-caption')
                ui.label(
                    'It cannot change anything — this connection is read-only, and '
                    'it only ever sees what you can already see.'
                ).classes('text-muted text-caption q-mt-sm')
                ui.label(
                    'You can disconnect it at any time from your profile.'
                ).classes('text-muted text-caption')
                with ui.row().classes('button-row q-mt-md'):
                    ui.button('Deny', on_click=deny).props('flat')
                    ui.button('Approve', icon='check', on_click=approve).props('color=primary')
        return None
