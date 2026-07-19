"""Admin Presets Page — tenant-authored seed-rolling presets (PRESET_MANAGER/STAFF)."""

import json

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error

from application.services import PresetService, SeedGenerationService, get_user_from_discord_id


async def admin_presets_page() -> None:
    service = PresetService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Seed Presets').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Named randomizer settings that seed generation resolves for a tournament. '
            "A tournament's Seed Preset (set on the tournament) overrides its Seed Generator. "
            'Import the built-in presets to get started.'
        ).classes('text-caption text-grey')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'randomizer', 'label': 'Randomizer', 'field': 'randomizer', 'sortable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'description', 'label': 'Description', 'field': 'description'},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]

        table_container = ui.column().classes('w-full')

        async def _current():
            return await get_user_from_discord_id(app.storage.user.get('discord_id'))

        async def refresh_table():
            presets = await service.list_presets(await _current())
            table.rows = [
                {
                    'id': p.id,
                    'randomizer': p.randomizer,
                    'name': p.name,
                    'description': p.description or '',
                    'settings': json.dumps(p.settings, indent=2),
                }
                for p in presets
            ]
            table.update()

        async def delete_preset(row, client):
            with client:
                try:
                    await service.delete_preset(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Preset deleted', color='positive')
                await refresh_table()

        async def import_builtins(client):
            with client:
                try:
                    created = await service.import_builtins(await _current())
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                if created:
                    ui.notify(f'Imported {len(created)} preset(s)', color='positive')
                else:
                    ui.notify('No new presets to import', color='info')
                await refresh_table()

        def open_preset_dialog(existing=None) -> None:
            is_edit = existing is not None
            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-[36rem]'):
                    ui.label('Edit Preset' if is_edit else 'Add Preset').classes('text-h6')
                    name_input = ui.input(
                        'Name', value=existing['name'] if is_edit else '',
                    ).classes('w-full')
                    randomizer_input = ui.select(
                        SeedGenerationService.AVAILABLE_RANDOMIZERS,
                        label='Randomizer',
                        value=existing['randomizer'] if is_edit else 'alttpr',
                    ).classes('w-full')
                    description_input = ui.input(
                        'Description', value=existing['description'] if is_edit else '',
                    ).classes('w-full')
                    settings_input = ui.textarea(
                        'Settings (JSON)',
                        value=existing['settings'] if is_edit else '{}',
                    ).classes('w-full font-mono').props('rows=12')

                    async def submit():
                        try:
                            settings = json.loads(settings_input.value or '{}')
                        except json.JSONDecodeError as e:
                            ui.notify(f'Settings must be valid JSON: {e}', color='warning')
                            return
                        try:
                            current = await _current()
                            if is_edit:
                                await service.update_preset(
                                    current, existing['id'],
                                    name=name_input.value,
                                    randomizer=randomizer_input.value,
                                    settings=settings,
                                    description=description_input.value,
                                )
                                ui.notify('Preset updated', color='positive')
                            else:
                                await service.create_preset(
                                    current,
                                    name=name_input.value,
                                    randomizer=randomizer_input.value,
                                    settings=settings,
                                    description=description_input.value,
                                )
                                ui.notify('Preset created', color='positive')
                            dialog.close()
                            await refresh_table()
                        except (ValueError, PermissionError) as e:
                            notify_error(e)

                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button(
                            'Save' if is_edit else 'Add', icon='save' if is_edit else 'add',
                            on_click=submit,
                        ).props('color=primary')
            dialog.open()

        with table_container:
            with ui.row().classes('full-width'):
                ui.button('Add Preset', icon='add', on_click=lambda: open_preset_dialog()).props('color=primary')
                ui.button(
                    'Import Built-ins', icon='download',
                    on_click=lambda: background_tasks.create(import_builtins(context.client)),
                ).props('flat color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full sgl-table')

            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn flat round dense icon="edit" color="primary"
                           @click="$parent.$emit('edit', props.row)">
                        <q-tooltip>Edit</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="delete" color="negative"
                           @click="$parent.$emit('delete', props.row)">
                        <q-tooltip>Delete</q-tooltip>
                    </q-btn>
                </q-td>
            ''')

            table.on('edit', lambda e: open_preset_dialog(e.args))
            table.on('delete', lambda e: background_tasks.create(delete_preset(e.args, context.client)))

        ui.on('selected_tab', lambda e: background_tasks.create(refresh_table()) if e.args == 'Presets' else None)
        background_tasks.create(refresh_table())
