"""Admin Presets Page — tenant-authored seed-rolling presets (PRESET_MANAGER/STAFF)."""

import json

from nicegui import app, background_tasks, context, ui

from application.services import (
    PresetService,
    RandomizerCredentialService,
    SeedGenerationService,
    get_user_from_discord_id,
)
from theme.notify import notify_error
from theme.tables.admin_crud import refresh_button, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="edit" color="primary"
           @click="$parent.$emit('edit', props.row)">
        <q-tooltip>Edit</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="delete" color="negative"
           @click="$parent.$emit('delete', props.row)">
        <q-tooltip>Delete</q-tooltip>
    </q-btn>
'''


async def admin_presets_page() -> None:
    service = PresetService()
    # Randomizers whose API key this community has not configured are dropped from
    # the create/edit select (mirrors the tournament dialog); a stored preset on
    # such a randomizer stays valid and editable (its value is re-added below).
    configured = await RandomizerCredentialService().configured_randomizers()
    available_randomizers = SeedGenerationService.available_randomizers(configured)

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Seed Presets').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Named randomizer settings that seed generation resolves for a tournament. '
            "A tournament's Seed Preset (set on the tournament) overrides its Seed Generator. "
            'Import the built-in presets to get started, or pull a randomizer\'s '
            'own published presets over its API.'
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
            # Re-read the configured set, not just the rows: the admin tabs are
            # built once per page load, so a key entered on the Randomizer Keys
            # tab would otherwise not reach this select until a full reload —
            # and "set the key, then author the preset" is the expected flow.
            # ``wire_tab_refresh`` runs this on every switch back to this tab.
            nonlocal available_randomizers
            available_randomizers = SeedGenerationService.available_randomizers(
                await RandomizerCredentialService().configured_randomizers()
            )
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

        def open_remote_dialog() -> None:
            """Browse a randomizer's own published presets and keep the useful ones.

            The alternative to hand-authoring a settings blob: the community
            picks from what the randomizer's site already offers its players.
            """
            remote_choices = [
                r for r in available_randomizers
                if SeedGenerationService.offers_remote_presets(r)
            ]
            if not remote_choices:
                ui.notify(
                    'No randomizer with a preset catalogue is configured. '
                    'Add its API key under Randomizer Keys first.',
                    color='warning',
                )
                return

            existing_names = {(r['randomizer'], r['name']) for r in table.rows}
            selected: set[str] = set()
            catalogue_state: dict = {}

            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-[36rem]'):
                    ui.label('Import from Randomizer').classes('text-h6')
                    ui.label(
                        "Fetches the randomizer's published presets. Importing one "
                        'saves it as a preset of your own — later changes upstream '
                        'do not follow it.'
                    ).classes('text-caption text-grey')

                    first_branches = SeedGenerationService.remote_preset_branches(
                        remote_choices[0]
                    )
                    randomizer_input = ui.select(
                        remote_choices, label='Randomizer', value=remote_choices[0],
                    ).classes('w-full')
                    branch_input = ui.select(
                        first_branches, label='Branch',
                        value=first_branches[0] if first_branches else None,
                    ).classes('w-full')

                    def reset_catalogue() -> None:
                        selected.clear()
                        catalogue_state.clear()
                        results.refresh()

                    def on_randomizer_change() -> None:
                        branches = SeedGenerationService.remote_preset_branches(
                            randomizer_input.value
                        )
                        branch_input.options = branches
                        branch_input.value = branches[0] if branches else None
                        branch_input.set_visibility(bool(branches))
                        branch_input.update()
                        reset_catalogue()

                    randomizer_input.on_value_change(lambda _: on_randomizer_change())
                    branch_input.on_value_change(lambda _: reset_catalogue())

                    @ui.refreshable
                    def results() -> None:
                        """The picker itself, rebuilt whenever the catalogue changes.

                        A searchable multi-select rather than a checkbox list:
                        DK64R publishes dozens of presets, and a list that long
                        is a scroll-and-squint exercise. Typing filters it.
                        """
                        if not catalogue_state:
                            ui.label(
                                'Fetch the catalogue to choose presets.'
                            ).classes('text-caption text-grey')
                            return

                        catalogue = catalogue_state['entries']
                        if not catalogue:
                            ui.label(
                                'This randomizer published no presets.'
                            ).classes('text-caption text-grey')
                            return

                        importable = {
                            e.name: e for e in catalogue
                            if (randomizer_input.value, e.name) not in existing_names
                        }
                        already = len(catalogue) - len(importable)
                        if not importable:
                            ui.label(
                                f'All {len(catalogue)} published presets are already imported.'
                            ).classes('text-caption text-grey')
                            return

                        picker = ui.select(
                            # Description in the option label so the search box
                            # matches on it too — "sprint" finds the sprint
                            # rulesets whatever they happen to be called.
                            {
                                name: (f'{name} — {entry.description}'
                                       if entry.description else name)
                                for name, entry in importable.items()
                            },
                            label='Presets to import',
                            multiple=True, with_input=True, clearable=True,
                            value=sorted(selected),
                        ).classes('w-full').props('use-chips')

                        def on_pick(event) -> None:
                            selected.clear()
                            selected.update(event.value or [])

                        picker.on_value_change(on_pick)

                        note = f'{len(importable)} available'
                        if already:
                            note += f', {already} already imported'
                        ui.label(note).classes('text-caption text-grey')

                    results()

                    async def fetch() -> None:
                        fetch_button.disable()
                        try:
                            catalogue = await service.list_remote_presets(
                                await _current(), randomizer_input.value,
                                branch=branch_input.value,
                            )
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                            return
                        finally:
                            fetch_button.enable()
                        selected.clear()
                        catalogue_state['entries'] = catalogue
                        results.refresh()

                    async def do_import() -> None:
                        try:
                            created = await service.import_remote_presets(
                                await _current(), randomizer_input.value,
                                sorted(selected), branch=branch_input.value,
                            )
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                            return
                        if created:
                            ui.notify(f'Imported {len(created)} preset(s)', color='positive')
                        else:
                            ui.notify('Those presets are already imported', color='info')
                        dialog.close()
                        await refresh_table()

                    with ui.row().classes('justify-end w-full'):
                        fetch_button = ui.button(
                            'Fetch Presets', icon='cloud_download', on_click=fetch,
                        ).props('flat color=primary')
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button(
                            'Import', icon='download', on_click=do_import,
                        ).props('color=primary')

                    on_randomizer_change()
            dialog.open()

        def open_preset_dialog(existing=None) -> None:
            is_edit = existing is not None
            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-[36rem]'):
                    ui.label('Edit Preset' if is_edit else 'Add Preset').classes('text-h6')
                    name_input = ui.input(
                        'Name', value=existing['name'] if is_edit else '',
                    ).classes('w-full')
                    randomizer_choices = list(available_randomizers)
                    # Never drop the row's current randomizer from its own editor.
                    if is_edit and existing['randomizer'] not in randomizer_choices:
                        randomizer_choices = [*randomizer_choices, existing['randomizer']]
                    randomizer_input = ui.select(
                        randomizer_choices,
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
                ui.button(
                    'Import from Randomizer', icon='cloud_download',
                    on_click=open_remote_dialog,
                ).props('flat color=primary')
                ui.space()
                refresh_button(refresh_table)

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')

            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS,
                               table_key=TableKeys.ADMIN_PRESETS)

            table.on('edit', lambda e: open_preset_dialog(e.args))
            table.on('delete', lambda e: background_tasks.create(delete_preset(e.args, context.client)))

        wire_tab_refresh('Presets', refresh_table)
        background_tasks.create(refresh_table())
