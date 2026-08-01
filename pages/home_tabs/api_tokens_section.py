"""API token management UI for the player profile page.

Lets a user create, view, and revoke their personal REST API tokens. All
mutations go through :class:`ApiTokenService`; the page never writes the ORM
directly. The plaintext token is shown exactly once, at creation.
"""

import json
from datetime import datetime, timezone

from nicegui import ui

from application.services import ApiTokenService
from application.utils.environment import get_base_url
from models import ApiTokenOrigin, User
from theme.dialog.confirmation_dialog import ConfirmationDialog


async def render_api_tokens_section(user: User) -> None:
    service = ApiTokenService()

    @ui.refreshable
    async def token_list() -> None:
        tokens = await service.list_tokens(user)
        if not tokens:
            ui.label('No API tokens yet.').classes('text-muted')
            return
        with ui.column().classes('input-full-width'):
            for t in tokens:
                is_oauth = t.origin == ApiTokenOrigin.OAUTH.value
                with ui.row().classes('row-centered').style('justify-content: space-between; width: 100%;'):
                    with ui.column().classes('gap-0'):
                        with ui.row().classes('row-centered'):
                            ui.label(t.name).classes('text-weight-medium')
                            if is_oauth:
                                # The row's label is already the client name (it
                                # is what the token was named at issue), so the
                                # badge marks the *kind* rather than repeating it.
                                ui.badge('AI client').props('color=primary')
                                # Only the writing grant is badged. Read-only is
                                # the default and the unremarkable case; the
                                # badge is here to make the other one visible on
                                # a page people skim.
                                if not t.read_only:
                                    ui.badge('can make changes').props('color=warning')
                            else:
                                if t.read_only:
                                    ui.badge('read-only').props('color=grey')
                                ui.label(f'{t.token_prefix}…').classes('text-muted text-caption')
                        used = f'Last used {t.last_used_at:%Y-%m-%d}' if t.last_used_at else 'Never used'
                        expires = f' · Expires {t.expires_at:%Y-%m-%d}' if t.expires_at else ''
                        ui.label(used + expires).classes('text-muted text-caption')
                    ui.button(icon='delete', on_click=lambda _, tid=t.id, o=is_oauth: revoke(tid, o)) \
                        .props('flat dense color=negative')

    def revoke(token_id: int, is_oauth: bool = False) -> None:
        async def do_revoke() -> None:
            confirm.dialog.close()
            try:
                await service.revoke_token(user, token_id)
                ui.notify('Token revoked.', color='positive', icon='check_circle')
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
            token_list.refresh()

        message = (
            'Disconnect this AI client? It will lose access immediately and must '
            'be reconnected to use Wizzrobe again.'
            if is_oauth else
            'Revoke this token? Any integration using it will stop working immediately.'
        )
        confirm = ConfirmationDialog(
            message=message,
            on_confirm=do_revoke, confirm_text='Revoke',
        )
        confirm.open()

    async def generate(name: str, read_only: bool, expires_str: str, dialog) -> None:
        expires_at = None
        if expires_str and expires_str.strip():
            try:
                expires_at = datetime.strptime(expires_str.strip(), '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                ui.notify('Expiry must be in YYYY-MM-DD format.', color='warning')
                return
        try:
            _, raw_token = await service.create_token(
                user, name=name or '', read_only=read_only, expires_at=expires_at,
            )
        except (ValueError, PermissionError) as e:
            ui.notify(str(e), color='warning')
            return
        dialog.close()
        token_list.refresh()
        show_token_dialog(raw_token)

    def open_generate_dialog() -> None:
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Generate API Token').classes('section-title')
            name_input = ui.input('Token name', placeholder='e.g. OBS overlay') \
                .classes('input-full-width').props('outlined dense')
            read_only_cb = ui.checkbox('Read-only (can only call GET endpoints)')
            expires_input = ui.input('Expiry date (optional)', placeholder='YYYY-MM-DD') \
                .classes('input-full-width').props('outlined dense')
            with ui.row().classes('button-row'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button(
                    'Generate', icon='vpn_key',
                    on_click=lambda: generate(name_input.value, read_only_cb.value, expires_input.value, dialog),
                ).props('color=primary')
        dialog.open()

    def show_token_dialog(raw_token: str) -> None:
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('Your new API token').classes('section-title')
            ui.label('Copy it now — you will not be able to see it again.').classes('text-warning')
            ui.input(value=raw_token).classes('input-full-width').props('outlined readonly dense')
            with ui.row().classes('button-row'):
                ui.button('Copy', icon='content_copy', on_click=lambda: copy_token(raw_token)).props('flat')
                ui.button('Done', on_click=dialog.close).props('color=primary')
        dialog.open()

    def copy_token(raw_token: str) -> None:
        ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(raw_token)})')
        ui.notify('Token copied to clipboard.', color='positive', icon='content_copy')

    def copy_text(value: str, label: str) -> None:
        ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(value)})')
        ui.notify(f'{label} copied to clipboard.', color='positive', icon='content_copy')

    def render_mcp_callout() -> None:
        """The connect-your-AI-client callout, above the credential list.

        There is no button here on purpose: an MCP connection is started from the
        client, not from us. The one thing the user needs from this page is the
        URL to paste, so that is what the callout gives them — everything after
        that is the OAuth flow, which signs them in and shows a consent screen.
        """
        mcp_url = f'{get_base_url()}/mcp'
        with ui.card().classes('card-full-width q-mb-sm').props('flat bordered'):
            with ui.row().classes('row-centered no-wrap'):
                ui.icon('smart_toy').classes('text-primary')
                ui.label('Connect an AI client').classes('text-weight-medium')
            ui.label(
                'Add this URL as a custom connector in Claude (or any MCP client) to '
                'ask questions about your communities. You will be asked to sign in '
                'and approve the connection. It can only read unless you tick the box '
                'to let it make changes.'
            ).classes('text-muted text-caption')
            with ui.row().classes('row-centered no-wrap input-full-width'):
                ui.input(value=mcp_url).classes('col').props('outlined readonly dense')
                ui.button(
                    icon='content_copy',
                    on_click=lambda: copy_text(mcp_url, 'MCP server URL'),
                ).props('flat dense').tooltip('Copy MCP server URL')

    # Developer-only surface — collapsed by default so it doesn't dominate the
    # profile for the majority of users who never touch the REST API.
    with ui.card().classes('card-full-width'):
        with ui.expansion('API tokens & AI clients', icon='vpn_key').classes('w-full') \
                .props('header-class=text-weight-bold'):
            render_mcp_callout()
            ui.label(
                'Personal tokens for the Wizzrobe REST API. Each token acts with your '
                'permissions; mark a token read-only to limit it to read endpoints.'
            ).classes('text-muted text-caption')
            ui.link('API documentation', '/api/docs', new_tab=True).classes('text-caption')
            with ui.row().classes('q-mt-sm'):
                ui.button('Generate token', icon='add', on_click=open_generate_dialog) \
                    .props('color=primary dense')
            await token_list()
