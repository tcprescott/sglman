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
from theme.chrome import render_platform_chrome

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


def _render_notice(headline: str, message: str) -> None:
    """The consent card's failure shape — an expired or unknown transaction.

    Deliberately not the themed error page: nothing is broken and there is no
    tenant to frame it in, so it stays on the same tenant-less consent surface
    and simply says the request can be started again.
    """
    render_platform_chrome('Authorize')
    with ui.column().classes('consent-page'):
        with ui.card().classes('consent-card consent-card--warn'):
            ui.icon('hourglass_disabled').classes('consent-badge consent-badge--warn')
            ui.label(headline).classes('consent-title')
            ui.label(message).classes('consent-lede')
            ui.label(
                'Nothing was shared. Start the connection again from the app '
                'that sent you here.'
            ).classes('consent-note')


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

        ui.page_title('Authorize — Wizzrobe')

        try:
            pending = service.get_pending(txn)
        except NotFoundError as exc:
            _render_notice('Authorization request expired', str(exc))
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

        def _signed_in_as() -> None:
            """Whose grant this is, in the header — the same identity the card names."""
            ui.label(user.preferred_name).classes('user-name')

        render_platform_chrome('Authorize', right=_signed_in_as)

        with ui.column().classes('consent-page'):
            with ui.card().classes('consent-card'):
                ui.icon('link').classes('consent-badge')
                ui.label('Connect to Wizzrobe').classes('consent-title')
                ui.label(
                    f'{client_name} wants to access Wizzrobe as '
                    f'{user.preferred_name}.'
                ).classes('consent-lede')
                ui.separator().classes('consent-rule')
                ui.label('It will be able to:').classes('consent-grants-title')
                with ui.column().classes('consent-grants'):
                    for icon, text in _GRANTS:
                        with ui.row().classes('consent-grant no-wrap'):
                            ui.icon(icon).props('size=sm').classes('consent-grant-icon')
                            ui.label(text)
                with ui.row().classes('consent-note consent-note--lock no-wrap'):
                    ui.icon('lock').props('size=sm')
                    ui.label(
                        'It cannot change anything — this connection is read-only, '
                        'and it only ever sees what you can already see.'
                    )
                ui.label(
                    'You can disconnect it at any time from your profile.'
                ).classes('consent-note')
                with ui.row().classes('consent-actions'):
                    ui.button('Deny', on_click=deny).props('flat')
                    ui.button('Approve', icon='check', on_click=approve).props('color=primary')
        return None
