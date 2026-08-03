"""Room token management, for the Settings tab.

Staff issue one token per shared machine, tape the URL to it (or bookmark it),
and read back which machines are still using theirs. The URL is shown once, at
issue: only the hash is stored, so a lost one is replaced rather than recovered.

Presentation only — every mutation goes through :class:`RoomTokenService`.
"""

import json

from nicegui import app, ui

from application.services import RoomTokenService, TenantService, get_user_from_discord_id
from application.services.room_token_service import room_seeds_path
from application.tenant_context import require_tenant_id
from application.utils.tenant_urls import tenant_url
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error


def _copy(value: str, label: str) -> None:
    ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(value)})')
    ui.notify(f'{label} copied to clipboard.', color='positive', icon='content_copy')


async def render_room_tokens_section(can_edit: bool) -> None:
    service = RoomTokenService()

    async def _actor():
        return await get_user_from_discord_id(app.storage.user.get('discord_id'))

    async def _url_for(raw_token: str) -> str:
        # Absolute and tenant-qualified: the URL is pasted into a browser on a
        # different machine, where a bare path resolves against nothing.
        tenant = await TenantService.get_by_id(require_tenant_id())
        return tenant_url(tenant, room_seeds_path(raw_token))

    @ui.refreshable
    async def token_list() -> None:
        try:
            tokens = await service.list_tokens(await _actor())
        except PermissionError:
            return
        if not tokens:
            ui.label(
                'No room tokens yet. Issue one to open the seeds board on a '
                'machine nobody signs in on.'
            ).classes('text-caption text-grey')
            return

        for token in tokens:
            revoked = token.revoked_at is not None
            with ui.row().classes('items-center gap-3 q-mb-xs full-width no-wrap'):
                with ui.column().classes('gap-0 col'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(token.label).classes('text-weight-medium')
                        if revoked:
                            ui.badge('revoked').props('color=grey')
                    used = (
                        f'Last used {token.last_used_at:%Y-%m-%d %H:%M}'
                        if token.last_used_at else 'Never used'
                    )
                    issuer = token.created_by.preferred_name if token.created_by else 'someone since removed'
                    ui.label(f'{used} · issued by {issuer}').classes('text-caption text-grey')
                if can_edit and not revoked:
                    ui.button(
                        icon='delete',
                        on_click=lambda _, tid=token.id, lbl=token.label: confirm_revoke(tid, lbl),
                    ).props('flat dense color=negative').tooltip('Revoke')

    def confirm_revoke(token_id: int, label: str) -> None:
        async def do_revoke() -> None:
            try:
                await service.revoke(await _actor(), token_id)
                ui.notify('Room token revoked.', color='positive', icon='check_circle')
            except (ValueError, PermissionError) as e:
                notify_error(e)
            token_list.refresh()

        ConfirmationDialog(
            message=(
                f'Revoke “{label}”? The machine using it will get a 404 on its '
                'next refresh, and the URL cannot be brought back.'
            ),
            on_confirm=do_revoke, confirm_text='Revoke',
        ).open()

    async def show_url_dialog(raw_token: str) -> None:
        url = await _url_for(raw_token)
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            ui.label('The room PC’s URL').classes('section-title')
            ui.label(
                'Copy it now — only the hash is stored, so this is the last time '
                'you can see it. Anyone with this URL can read the seeds board, '
                'so bookmark it on the machine rather than posting it anywhere.'
            ).classes('text-warning')
            ui.input(value=url).classes('input-full-width').props('outlined readonly dense')
            with ui.row().classes('button-row'):
                ui.button('Copy', icon='content_copy',
                          on_click=lambda: _copy(url, 'Room URL')).props('flat')
                ui.button('Done', on_click=dialog.close).props('color=primary')
        dialog.open()

    async def issue() -> None:
        try:
            _, raw_token = await service.issue(await _actor(), label_input.value or '')
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        label_input.value = ''
        token_list.refresh()
        await show_url_dialog(raw_token)

    ui.separator().classes('separator-spacing')
    ui.label('Tournament Room Screens').classes('section-title q-mt-md')
    ui.label(
        'A read-only board of matches whose seed is rolled but which nobody has '
        'started, for a machine in the room that nobody signs in on. Each token '
        'is an unlisted URL that opens that one page — it cannot roll a seed, '
        'run a match, or read anything else. It is not linked from anywhere, so '
        'bookmark it on the machine it belongs to.'
    ).classes('text-caption text-grey')

    with ui.column().classes('gap-1 full-width q-mt-sm'):
        await token_list()

    if not can_edit:
        return

    with ui.row().classes('items-center gap-3 q-mt-sm'):
        label_input = ui.input('Label', placeholder='e.g. Room A desk PC') \
            .props('outlined dense maxlength=100').classes('w-64')
        ui.button('Issue token', icon='add', on_click=issue).props('color=primary')
