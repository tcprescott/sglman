"""API token management UI for the player profile page.

Lets a user create, view, and revoke their personal REST API tokens. All
mutations go through :class:`ApiTokenService`; the page never writes the ORM
directly. The plaintext token is shown exactly once, at creation.
"""

from datetime import datetime, timezone

from nicegui import ui

from application.services import ApiTokenService
from application.utils.environment import get_base_url
from application.utils.timezone import format_local_date
from models import ApiTokenOrigin, User
from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.dialog.secret_dialog import show_secret_dialog


async def render_api_tokens_section(user: User) -> None:
    service = ApiTokenService()

    @ui.refreshable
    async def token_list() -> None:
        tokens = await service.list_tokens(user)
        if not tokens:
            ui.label('No API tokens yet.').classes('text-muted')
            return
        with ui.column().classes('input-full-width gap-0'):
            for i, t in enumerate(tokens):
                is_oauth = t.origin == ApiTokenOrigin.OAUTH.value
                if i:
                    ui.separator().classes('q-my-sm')
                with ui.row().classes('items-center no-wrap w-full gap-2'):
                    with ui.column().classes('gap-1 col min-w-0'):
                        with ui.row().classes('items-center gap-1'):
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
                            elif t.read_only:
                                ui.badge('read-only').props('color=grey')
                        used = (
                            f'Last used {format_local_date(t.last_used_at)}'
                            if t.last_used_at else 'Never used'
                        )
                        expires = f' · Expires {format_local_date(t.expires_at)}' if t.expires_at else ''
                        prefix = '' if is_oauth else f'{t.token_prefix}… · '
                        ui.label(prefix + used + expires) \
                            .classes('text-caption text-grey-7') \
                            .style('overflow-wrap: anywhere')
                    label = f'Disconnect {t.name}' if is_oauth else f'Revoke {t.name}'
                    ui.button(icon='delete', on_click=lambda _, tid=t.id, o=is_oauth: revoke(tid, o)) \
                        .classes('col-auto') \
                        .props('flat dense round color=negative') \
                        .tooltip(label)

    def revoke(token_id: int, is_oauth: bool = False) -> None:
        async def do_revoke() -> None:
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
        with form_dialog('Generate API Token') as dialog:
            name_input = ui.input('Token name', placeholder='e.g. OBS overlay') \
                .classes('input-full-width').props('outlined dense')
            read_only_cb = ui.checkbox('Read-only (can only call GET endpoints)')
            expires_input = ui.input('Expiry date (optional)', placeholder='YYYY-MM-DD') \
                .classes('input-full-width').props('outlined dense')
            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button(
                    'Generate', icon='vpn_key',
                    on_click=lambda: generate(name_input.value, read_only_cb.value, expires_input.value, dialog),
                ).props('color=primary')
        dialog.open()

    def show_token_dialog(raw_token: str) -> None:
        show_secret_dialog('Your new API token', raw_token, noun='token')

    def render_mcp_callout() -> None:
        """The connect-your-AI-client callout, above the credential list.

        There is no button here on purpose: an MCP connection is started from the
        client, not from us. The one thing the user needs from this page is the
        URL to paste, so that is what the callout gives them — everything after
        that is the OAuth flow, which signs them in and shows a consent screen.
        """
        mcp_url = f'{get_base_url()}/mcp'
        # Not a nested card: inside the expansion a second border and padding
        # cost a phone a third of its width, and the URL was cut to a few letters.
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.icon('smart_toy').classes('text-primary')
            ui.label('Connect an AI client').classes('subsection-title')
        ui.label(
            'Add this URL as a custom connector in Claude or any MCP client. '
            "It's read-only unless you allow changes when you approve it."
        ).classes('text-muted text-caption')
        # Shown whole, wrapping if it must: a readonly input cut the URL to a
        # few letters on a phone, and the copy button is how it gets used.
        with ui.row().classes('items-center no-wrap w-full gap-2 q-mt-xs'):
            ui.label(mcp_url).classes('col min-w-0') \
                .style('font-family: var(--font-mono); font-size: 0.8125rem; overflow-wrap: anywhere')
            ui.button(
                icon='content_copy',
                on_click=lambda: copy_to_clipboard(mcp_url, 'MCP server URL'),
            ).classes('col-auto').props('flat dense round').tooltip('Copy MCP server URL')
        ui.separator().classes('q-my-md')

    # Developer-only surface — collapsed by default so it doesn't dominate the
    # profile for the majority of users who never touch the REST API.
    with ui.card().classes('card-full-width'):
        with ui.expansion('API tokens & AI clients', icon='vpn_key').classes('w-full') \
                .props('header-class=text-weight-bold'):
            render_mcp_callout()
            ui.label(
                'Personal tokens for the REST API act with your permissions. '
                'Make one read-only to limit it to reads.'
            ).classes('text-muted text-caption')
            ui.link('API documentation', '/api/docs', new_tab=True).classes('text-caption')
            with ui.row().classes('q-mt-sm'):
                ui.button('Generate token', icon='add', on_click=open_generate_dialog) \
                    .props('color=primary dense')
            await token_list()
