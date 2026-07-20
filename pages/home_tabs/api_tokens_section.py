"""API token management UI for the player profile page.

Lets a user create, view, and revoke their personal REST API tokens. All
mutations go through :class:`ApiTokenService`; the page never writes the ORM
directly. The plaintext token is shown exactly once, at creation.
"""

import json
from datetime import datetime, timezone

from nicegui import ui

from application.services import ApiTokenService
from models import User
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
                with ui.row().classes('row-centered').style('justify-content: space-between; width: 100%;'):
                    with ui.column().classes('gap-0'):
                        with ui.row().classes('row-centered'):
                            ui.label(t.name).classes('text-weight-medium')
                            if t.read_only:
                                ui.badge('read-only').props('color=grey')
                            ui.label(f'{t.token_prefix}…').classes('text-muted text-caption')
                        used = f'Last used {t.last_used_at:%Y-%m-%d}' if t.last_used_at else 'Never used'
                        expires = f' · Expires {t.expires_at:%Y-%m-%d}' if t.expires_at else ''
                        ui.label(used + expires).classes('text-muted text-caption')
                    ui.button(icon='delete', on_click=lambda _, tid=t.id: revoke(tid)) \
                        .props('flat dense color=negative')

    def revoke(token_id: int) -> None:
        async def do_revoke() -> None:
            confirm.dialog.close()
            try:
                await service.revoke_token(user, token_id)
                ui.notify('Token revoked.', color='positive', icon='check_circle')
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
            token_list.refresh()

        confirm = ConfirmationDialog(
            message='Revoke this token? Any integration using it will stop working immediately.',
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

    # Developer-only surface — collapsed by default so it doesn't dominate the
    # profile for the majority of users who never touch the REST API.
    with ui.card().classes('card-full-width'):
        with ui.expansion('API tokens', icon='vpn_key').classes('w-full') \
                .props('header-class=text-weight-bold'):
            ui.label(
                'Personal tokens for the Wizzrobe REST API. Each token acts with your '
                'permissions; mark a token read-only to limit it to read endpoints.'
            ).classes('text-muted text-caption')
            ui.link('API documentation', '/api/docs', new_tab=True).classes('text-caption')
            with ui.row().classes('q-mt-sm'):
                ui.button('Generate token', icon='add', on_click=open_generate_dialog) \
                    .props('color=primary dense')
            await token_list()
