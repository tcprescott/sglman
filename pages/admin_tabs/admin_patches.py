"""Admin Patches — ROM patches the community hosts for its players.

Staff (or a preset manager) upload a BPS, IPS or UPS file and share the
``/patch/<token>`` link it gets; players patch their own ROM on that page,
in their browser. Layout A (Thomas, 2026-10-16): one list, a row ⋮ for
Copy link, Open page, Edit, Replace file and Delete.
"""

from typing import Any, Optional

from nicegui import background_tasks, ui

from application.services import RomPatchService, TenantService, TournamentService
from application.tenant_context import get_current_tenant_id
from application.utils.rom_patch_format import MAX_PATCH_BYTES, read_patch
from application.utils.tenant_urls import tenant_url
from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.empty_state import empty_state
from theme.notify import notify_error
from theme.page_header import page_header
from theme.tables.admin_crud import current_actor, refresh_button, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_ACCEPT = '.bps,.ips,.ups'

_PATCH_CELL = '''
    <div class="text-weight-bold">{{ props.row.title }}</div>
    <div class="text-muted text-caption">{{ props.row.tournament || 'No tournament' }}</div>
'''

_NEEDS_CELL = '''
    <div>{{ props.row.game }}</div>
    <div class="text-muted text-caption">{{ props.row.format_label }} · {{ props.row.crc || 'No CRC' }}</div>
'''

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="more_vert" color="grey-7"
           :aria-label="'More for ' + props.row.title">
        <q-menu auto-close anchor="bottom right" self="top right">
            <q-list style="min-width: 200px">
                <q-item clickable @click="$parent.$emit('copy', props.row)">
                    <q-item-section avatar><q-icon name="link"/></q-item-section>
                    <q-item-section>Copy link</q-item-section>
                </q-item>
                <q-item clickable :href="props.row.link" target="_blank">
                    <q-item-section avatar><q-icon name="open_in_new"/></q-item-section>
                    <q-item-section>Open page</q-item-section>
                </q-item>
                <q-item clickable @click="$parent.$emit('edit', props.row)">
                    <q-item-section avatar><q-icon name="edit"/></q-item-section>
                    <q-item-section>Edit</q-item-section>
                </q-item>
                <q-item clickable @click="$parent.$emit('replace', props.row)">
                    <q-item-section avatar><q-icon name="upload_file"/></q-item-section>
                    <q-item-section>Replace file…</q-item-section>
                </q-item>
                <q-separator />
                <q-item clickable class="text-negative" @click="$parent.$emit('remove', props.row)">
                    <q-item-section avatar><q-icon name="delete" color="negative"/></q-item-section>
                    <q-item-section>Delete…</q-item-section>
                </q-item>
            </q-list>
        </q-menu>
    </q-btn>
'''


class _FilePicker:
    """A named button that opens a hidden ``ui.upload``, plus a line saying what was picked.

    Quasar's uploader card fails axe (an unnamed input, a nameless nested
    button), so it stays hidden, as on Admin → Appearance. The upload request
    only reads the bytes; nothing touches the database until Save.
    """

    def __init__(self, label: str, on_change=None) -> None:
        self.data: Optional[bytes] = None
        self.name: Optional[str] = None
        self.format: Optional[str] = None
        self.crc: Optional[str] = None
        self.on_change = on_change
        self.uploader = ui.upload(
            auto_upload=True, max_file_size=MAX_PATCH_BYTES, on_upload=self._on_upload,
            on_rejected=lambda: ui.notify('Patches can be up to 16 MB.', color='warning'),
        ).props(f'accept="{_ACCEPT}"').classes('hidden')
        with ui.row().classes('items-center no-wrap gap-3 w-full'):
            ui.button(label, icon='upload_file', on_click=lambda: self.uploader.run_method('pickFiles'),
                      color=None).props('outline no-caps')
            self.status = ui.label('BPS, IPS or UPS, up to 16 MB').classes('text-muted col')

    async def _on_upload(self, e) -> None:
        data = await e.file.read()
        self.uploader.reset()
        try:
            info = read_patch(data)
        except ValueError as err:
            ui.notify(str(err), color='warning')
            return
        self.data, self.name, self.format, self.crc = data, e.file.name, info.format, info.source_crc
        needs = f'needs CRC32 {info.source_crc}' if info.source_crc else "doesn't name a ROM"
        self.status.set_text(f'{e.file.name} · {info.format.upper()}, {needs}')
        if self.on_change:
            self.on_change()


async def admin_patches_page() -> None:
    service = RomPatchService()
    state: dict[str, Any] = {'rows': None}
    tid = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tid) if tid is not None else None

    def link_for(token: str) -> str:
        return tenant_url(tenant, f'/patch/{token}') if tenant is not None else f'/patch/{token}'

    async def tournament_options() -> dict:
        tournaments = await TournamentService().get_all_tournaments()
        return {None: 'No tournament', **{t.id: t.name for t in tournaments}}

    with ui.column().classes('page-container-narrow'):
        page_header(
            'Patches',
            'ROM patches you host for players. Share a patch\'s link: players pick their own ROM '
            'once and patch it in their browser. No ROM is ever uploaded. Anyone can also use '
            'the open patcher at /patcher with a patch they already have.',
        )

        container = ui.column().classes('w-full')

        async def refresh_table() -> None:
            patches = await service.list_patches(await current_actor())
            state['rows'] = [
                {
                    'id': p.id,
                    'title': p.title,
                    'game': p.game,
                    'description': p.description or '',
                    'tournament': p.tournament.name if p.tournament else '',
                    'tournament_id': p.tournament.id if p.tournament else None,
                    'format': p.format,
                    'format_label': p.format.upper(),
                    'crc': p.source_crc or '',
                    'downloads': p.download_count,
                    'link': link_for(p.token),
                }
                for p in patches
            ]
            table.rows = state['rows']
            table.update()
            empty.set_visibility(not state['rows'])
            table.set_visibility(bool(state['rows']))

        def crc_input(value: str = '', visible: bool = True):
            field = ui.input('ROM CRC32 (optional)', value=value).props('hint="An IPS patch doesn\'t say which ROM it needs. Type its CRC32 to check players\' ROMs."') \
                .classes('w-full')
            field.set_visibility(visible)
            return field

        async def open_patch_dialog(existing: Optional[dict] = None) -> None:
            options = await tournament_options()
            is_edit = existing is not None
            values: dict = existing or {
                'title': '', 'game': '', 'description': '', 'tournament_id': None, 'crc': '', 'format': '',
            }
            with container, form_dialog('Edit patch' if is_edit else 'Upload patch',
                                        card_classes='dialog-card dialog-card--sm') as dialog:
                with ui.column().classes('w-full gap-2'):
                    picker = None
                    if not is_edit:
                        picker = _FilePicker('Choose patch file…', on_change=lambda: on_file())
                    title = ui.input('Title', value=values['title']) \
                        .props('maxlength=120').classes('w-full')
                    game = ui.input('ROM it needs', value=values['game']) \
                        .props('maxlength=120 hint="The game and region, like Super Metroid (Japan, USA)"') \
                        .classes('w-full')
                    description = ui.textarea(
                        'Description (optional)', value=values['description'],
                    ).props('maxlength=2000 autogrow').classes('w-full')
                    tournament = ui.select(
                        options, label='Tournament (optional)',
                        value=values['tournament_id'],
                    ).classes('w-full')
                    crc = crc_input(values['crc'], visible=values['format'] == 'ips')

                def on_file() -> None:
                    crc.set_visibility(picker is not None and picker.format == 'ips')
                    if picker is not None and not title.value and picker.name:
                        title.value = picker.name.rsplit('.', 1)[0]

                async def submit() -> None:
                    actor = await current_actor()
                    try:
                        if is_edit:
                            await service.update_patch(
                                actor, values['id'], title=title.value, game=game.value,
                                description=description.value, tournament_id=tournament.value,
                                source_crc=crc.value,
                            )
                        else:
                            if picker is None or picker.data is None:
                                raise ValueError('Choose a patch file first.')
                            await service.create_patch(
                                actor, title=title.value, game=game.value, filename=picker.name or '',
                                data=picker.data, description=description.value,
                                tournament_id=tournament.value, source_crc=crc.value,
                            )
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    dialog.close()
                    ui.notify('Patch saved' if is_edit else 'Patch uploaded', color='positive')
                    await refresh_table()

                with dialog_actions().classes('justify-end'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    ui.button('Save' if is_edit else 'Upload', icon='save' if is_edit else 'upload',
                              on_click=submit).props('color=primary')
            dialog.open()

        def open_replace_dialog(row: dict) -> None:
            with container, form_dialog(f"Replace file: {row['title']}",
                                        card_classes='dialog-card dialog-card--sm') as dialog:
                with ui.column().classes('w-full gap-2'):
                    ui.label('The link stays the same, so anyone who has it gets the new file.') \
                        .classes('text-muted')
                    picker = _FilePicker('Choose new file…')
                    crc = crc_input(row['crc'], visible=False)
                    picker.on_change = lambda: crc.set_visibility(picker.format == 'ips')

                async def submit() -> None:
                    try:
                        if picker.data is None:
                            raise ValueError('Choose a patch file first.')
                        await service.replace_file(
                            await current_actor(), row['id'], filename=picker.name or '',
                            data=picker.data, source_crc=crc.value,
                        )
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    dialog.close()
                    ui.notify('Patch file replaced', color='positive')
                    await refresh_table()

                with dialog_actions().classes('justify-end'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    ui.button('Replace', icon='upload', on_click=submit).props('color=primary')
            dialog.open()

        def confirm_delete(row: dict) -> None:
            async def do_delete() -> None:
                try:
                    await service.delete_patch(await current_actor(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Patch deleted', color='positive')
                await refresh_table()

            ConfirmationDialog(
                message=f"Delete {row['title']}? Its link stops working for everyone who has it.",
                on_confirm=do_delete, confirm_text='Delete', title='Delete patch?',
            ).open()

        with container:
            with ui.row().classes('full-width items-center'):
                ui.button('Upload patch', icon='upload',
                          on_click=lambda: open_patch_dialog()).props('color=primary')
                ui.space()
                refresh_button(refresh_table)

            with ui.column().classes('w-full') as empty:
                empty_state('No patches yet. Upload one to get a link to share.')
            empty.set_visibility(False)

            columns: list[dict] = [
                {'name': 'title', 'label': 'Patch', 'field': 'title', 'align': 'left', 'sortable': True},
                {'name': 'game', 'label': 'Needs', 'field': 'game', 'align': 'left', 'sortable': True},
                {'name': 'downloads', 'label': 'Downloads', 'field': 'downloads', 'align': 'right', 'sortable': True},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')
            table.add_slot('body-cell-title', f'<q-td :props="props">{_PATCH_CELL}</q-td>')
            table.add_slot('body-cell-game', f'<q-td :props="props">{_NEEDS_CELL}</q-td>')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            table.on('copy', lambda e: copy_to_clipboard(e.args['link'], 'Link'))
            table.on('edit', lambda e: open_patch_dialog(e.args))
            table.on('replace', lambda e: open_replace_dialog(e.args))
            table.on('remove', lambda e: confirm_delete(e.args))
            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS, table_key=TableKeys.ADMIN_ROM_PATCHES,
                               field_slots={'title': _PATCH_CELL, 'game': _NEEDS_CELL})
            table.set_visibility(False)

        wire_tab_refresh('Patches', refresh_table)
        background_tasks.create(refresh_table())
