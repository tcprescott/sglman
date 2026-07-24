"""Admin Brackets Page — native tournament brackets management (STAFF).

Staff-facing surface over :class:`~application.services.bracket_service.BracketService`:
pick a tournament, author its bracket stages (create/edit/delete while DRAFT),
manage the tournament roster and per-stage enrollment/seeding, start a stage,
record results (with overrides), complete a stage, and advance the field into the
next stage.

Presentation-only: renders NiceGUI, calls the service for every write, and shows
service ``ValueError`` / ``PermissionError`` as toasts. Read-only ``Tournament``
lookups for the selector are the sanctioned display query. All scoped reads and
service calls run inside ``tenant_scope`` because row-action handlers and the
tournament selector fire from detached client events that have lost the tenant
contextvar.
"""

from typing import Dict, List, Optional

from nicegui import background_tasks, context, ui

from application.services import BracketService
from application.tenant_context import require_tenant_id, tenant_scope
from models import BracketFormat, BracketState, Tournament
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="tune" color="primary"
           @click="$parent.$emit('manage', props.row)">
        <q-tooltip>Manage entrants & start</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="scoreboard" color="primary"
           @click="$parent.$emit('results', props.row)">
        <q-tooltip>Results</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="flag" color="secondary"
           @click="$parent.$emit('complete', props.row)">
        <q-tooltip>Complete stage</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="fast_forward" color="secondary"
           @click="$parent.$emit('advance', props.row)">
        <q-tooltip>Advance to next stage</q-tooltip>
    </q-btn>
'''

_FORMAT_OPTIONS = {
    BracketFormat.SINGLE_ELIM.value: 'Single elimination',
    BracketFormat.DOUBLE_ELIM.value: 'Double elimination',
    BracketFormat.SWISS.value: 'Swiss',
    BracketFormat.ROUND_ROBIN.value: 'Round robin',
}


async def admin_brackets_page() -> None:
    service = BracketService()
    # Captured while the request context is live; rebound around every detached
    # client-event handler (see module docstring).
    tenant_id = require_tenant_id()
    state: Dict[str, Optional[int]] = {'tournament_id': None}

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Brackets').classes('page-title')
        ui.separator().classes('separator-spacing')

        ui.label(
            'Native tournament brackets. Pick a tournament, author its stages, '
            'manage the roster and seeding, then start, record results, complete '
            'a stage, and advance into the next.'
        ).classes('text-caption text-grey')

        tournaments = await Tournament.filter(tenant_id=tenant_id).order_by('name')
        options = {t.id: t.name for t in tournaments}

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'stage_order', 'label': 'Stage', 'field': 'stage_order', 'sortable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'format', 'label': 'Format', 'field': 'format'},
            {'name': 'state', 'label': 'State', 'field': 'state'},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]

        page_container = ui.column().classes('w-full')

        # --- brackets table refresh --------------------------------------
        async def refresh_table() -> None:
            with tenant_scope(tenant_id):
                tid = state['tournament_id']
                if tid is None:
                    table.rows = []
                    table.update()
                    return
                brackets = await service.list_brackets(tid)
            table.rows = [
                {
                    'id': b.id,
                    'stage_order': b.stage_order,
                    'name': b.name,
                    'format': _FORMAT_OPTIONS.get(b.format.value, b.format.value),
                    'state': b.state.value,
                }
                for b in brackets
            ]
            table.update()

        def on_tournament_change(e) -> None:
            state['tournament_id'] = e.value
            background_tasks.create(refresh_table())

        # --- name helpers ------------------------------------------------
        async def _entry_name_map(bracket_id: int, tid: int) -> Dict[int, str]:
            """entry_id → entrant display name (scoped read caller must supply scope)."""
            entrants = {en.id: en.display_name for en in await service.list_entrants(tid)}
            entries = await service.list_entries(bracket_id)
            return {
                e.id: entrants.get(e.entrant_id, f'Entry {e.id}') for e in entries
            }

        # --- manage dialog (roster / enrollment / seeding / start) -------
        async def open_manage(row, client) -> None:
            bracket_id = row['id']
            tid = state['tournament_id']
            with client:
                actor = await current_actor()
                with ui.dialog() as dialog, ui.card().classes('w-[40rem] max-w-full'):
                    ui.label(f"Manage — {row['name']}").classes('text-h6')

                    @ui.refreshable
                    async def body() -> None:
                        with tenant_scope(tenant_id):
                            bracket = await service.get_bracket(bracket_id)
                            entrants = await service.list_entrants(tid)
                            entries = await service.list_entries(bracket_id)
                        if bracket is None:
                            ui.label('Bracket not found.').classes('text-error')
                            return
                        is_draft = bracket.state == BracketState.DRAFT
                        enrolled_entrant_ids = {e.entrant_id for e in entries}

                        ui.label('Add entrant to tournament').classes('section-title')
                        with ui.row().classes('items-end gap-2 w-full'):
                            name_in = ui.input('Display name').classes('flex-grow')
                            user_in = ui.number('User ID (optional)', min=1).props('inputmode=numeric')

                            async def add_entrant() -> None:
                                with tenant_scope(tenant_id):
                                    try:
                                        await service.add_entrant(
                                            actor, tid, name_in.value or '',
                                            int(user_in.value) if user_in.value else None,
                                        )
                                    except (ValueError, PermissionError) as ex:
                                        notify_error(ex)
                                        return
                                ui.notify('Entrant added', color='positive')
                                await body.refresh()

                            ui.button('Add', icon='person_add', on_click=add_entrant).props('color=primary')

                        ui.separator()
                        ui.label('Roster — enroll into this stage').classes('section-title')
                        if not entrants:
                            ui.label('No entrants yet.').classes('text-muted')
                        for en in entrants:
                            with ui.row().classes('items-center gap-2 w-full'):
                                ui.label(en.display_name).classes('text-bold')
                                if en.id in enrolled_entrant_ids:
                                    ui.badge('enrolled', color='positive')
                                else:
                                    ui.space()
                                    seed_in = ui.number('Seed', min=1).props('inputmode=numeric dense').classes('w-24')

                                    async def enroll(_=None, entrant_id=en.id, seed_widget=seed_in) -> None:
                                        with tenant_scope(tenant_id):
                                            try:
                                                await service.enroll(
                                                    actor, bracket_id, entrant_id,
                                                    int(seed_widget.value) if seed_widget.value else None,
                                                )
                                            except (ValueError, PermissionError) as ex:
                                                notify_error(ex)
                                                return
                                        ui.notify('Enrolled', color='positive')
                                        await body.refresh()

                                    ui.button(
                                        'Enroll', icon='how_to_reg', on_click=enroll,
                                    ).props('flat color=primary' + ('' if is_draft else ' disable'))

                        ui.separator()
                        ui.label('Enrolled entries').classes('section-title')
                        if not entries:
                            ui.label('Nobody enrolled yet.').classes('text-muted')
                        name_by_entrant = {en.id: en.display_name for en in entrants}
                        seed_widgets: Dict[int, object] = {}
                        for entry in entries:
                            with ui.row().classes('items-center gap-2 w-full'):
                                ui.label(
                                    name_by_entrant.get(entry.entrant_id, f'Entry {entry.id}')
                                )
                                ui.space()
                                seed_widgets[entry.id] = ui.number(
                                    'Seed', value=entry.seed, min=1,
                                ).props('inputmode=numeric dense').classes('w-24')

                        async def save_seeds() -> None:
                            seeds = {
                                eid: int(w.value)
                                for eid, w in seed_widgets.items()
                                if w.value is not None
                            }
                            with tenant_scope(tenant_id):
                                try:
                                    await service.set_seeds(actor, bracket_id, seeds)
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Seeds saved', color='positive')
                            await body.refresh()

                        async def start() -> None:
                            with tenant_scope(tenant_id):
                                try:
                                    await service.start_bracket(actor, bracket_id)
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Bracket started', color='positive')
                            await body.refresh()
                            await refresh_table()

                        with ui.row().classes('justify-end w-full q-mt-md'):
                            if is_draft and entries:
                                ui.button('Save seeds', icon='save', on_click=save_seeds).props('flat color=primary')
                                ui.button('Start bracket', icon='play_arrow', on_click=start).props('color=primary')
                            ui.button('Close', on_click=dialog.close).props('flat')

                    await body()
                dialog.open()

        # --- results dialog (report / override) --------------------------
        async def open_results(row, client) -> None:
            bracket_id = row['id']
            tid = state['tournament_id']
            with client:
                actor = await current_actor()
                with ui.dialog() as dialog, ui.card().classes('w-[40rem] max-w-full'):
                    ui.label(f"Results — {row['name']}").classes('text-h6')

                    @ui.refreshable
                    async def body() -> None:
                        with tenant_scope(tenant_id):
                            matches = await service.list_matches(bracket_id)
                            names = await _entry_name_map(bracket_id, tid)

                        def slot_label(entry_id: Optional[int]) -> str:
                            if entry_id is None:
                                return '—'
                            return names.get(entry_id, f'Entry {entry_id}')

                        async def report(match_id: int, winner_entry_id: int) -> None:
                            with tenant_scope(tenant_id):
                                try:
                                    await service.report_result(actor, match_id, winner_entry_id)
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Result recorded', color='positive')
                            await body.refresh()
                            await refresh_table()

                        async def override(match_id: int, winner_entry_id: int) -> None:
                            with tenant_scope(tenant_id):
                                try:
                                    await service.override_result(actor, match_id, winner_entry_id)
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Result overridden', color='positive')
                            await body.refresh()
                            await refresh_table()

                        open_matches = [m for m in matches if m.state.value == 'open']
                        complete_matches = [
                            m for m in matches
                            if m.state.value == 'complete'
                            and m.entry1_id is not None and m.entry2_id is not None
                        ]

                        ui.label('Open matches').classes('section-title')
                        if not open_matches:
                            ui.label('No open matches.').classes('text-muted')
                        for m in open_matches:
                            with ui.row().classes('items-center gap-2 w-full'):
                                ui.label(
                                    f'R{m.round} #{m.position}: '
                                    f'{slot_label(m.entry1_id)} vs {slot_label(m.entry2_id)}'
                                )
                                ui.space()
                                if m.entry1_id is not None:
                                    ui.button(
                                        slot_label(m.entry1_id), icon='emoji_events',
                                        on_click=lambda _=None, mid=m.id, w=m.entry1_id: report(mid, w),
                                    ).props('flat dense color=primary')
                                if m.entry2_id is not None:
                                    ui.button(
                                        slot_label(m.entry2_id), icon='emoji_events',
                                        on_click=lambda _=None, mid=m.id, w=m.entry2_id: report(mid, w),
                                    ).props('flat dense color=primary')

                        ui.separator()
                        ui.label('Completed matches — override').classes('section-title')
                        if not complete_matches:
                            ui.label('No completed matches.').classes('text-muted')
                        for m in complete_matches:
                            with ui.row().classes('items-center gap-2 w-full'):
                                ui.label(
                                    f'R{m.round} #{m.position}: '
                                    f'{slot_label(m.entry1_id)} vs {slot_label(m.entry2_id)} '
                                    f'→ {slot_label(m.winner_id)}'
                                )
                                ui.space()
                                ui.button(
                                    slot_label(m.entry1_id), icon='published_with_changes',
                                    on_click=lambda _=None, mid=m.id, w=m.entry1_id: override(mid, w),
                                ).props('flat dense color=secondary')
                                ui.button(
                                    slot_label(m.entry2_id), icon='published_with_changes',
                                    on_click=lambda _=None, mid=m.id, w=m.entry2_id: override(mid, w),
                                ).props('flat dense color=secondary')

                        with ui.row().classes('justify-end w-full q-mt-md'):
                            ui.button('Close', on_click=dialog.close).props('flat')

                    await body()
                dialog.open()

        # --- complete stage ----------------------------------------------
        async def complete_stage(row, client) -> None:
            with client:
                actor = await current_actor()
                with tenant_scope(tenant_id):
                    try:
                        await service.complete_stage(actor, row['id'])
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return
                ui.notify('Stage completed', color='positive')
                await refresh_table()

        # --- advance stage (preview + confirm) ---------------------------
        async def open_advance(row, client) -> None:
            tid = state['tournament_id']
            from_stage_order = row['stage_order']
            with client:
                actor = await current_actor()
                with tenant_scope(tenant_id):
                    try:
                        preview = await service.get_advancing_preview(tid, from_stage_order)
                        names = await _entry_name_map(row['id'], tid)
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return

                with ui.dialog() as dialog, ui.card().classes('w-[32rem] max-w-full'):
                    ui.label(f"Advance from stage {from_stage_order}").classes('text-h6')
                    ui.label(
                        f'{len(preview)} entrant(s) would advance into the next stage:'
                    ).classes('text-caption text-grey')
                    for e in preview:
                        ui.label(
                            f'#{e.final_rank} — {names.get(e.id, f"Entry {e.id}")}'
                        )

                    async def do_advance() -> None:
                        with tenant_scope(tenant_id):
                            try:
                                await service.advance_stage(actor, tid, from_stage_order)
                            except (ValueError, PermissionError) as ex:
                                notify_error(ex)
                                return
                        ui.notify('Field advanced into next stage', color='positive')
                        dialog.close()
                        await refresh_table()

                    with ui.row().classes('justify-end w-full q-mt-md'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Advance', icon='fast_forward', on_click=do_advance).props('color=primary')
                dialog.open()

        # --- create bracket dialog ---------------------------------------
        def open_create() -> None:
            tid = state['tournament_id']
            with page_container:
                with ui.dialog() as dialog, ui.card().classes('w-[32rem] max-w-full'):
                    ui.label('Create bracket stage').classes('text-h6')
                    name_in = ui.input('Name').classes('w-full')
                    fmt_in = ui.select(
                        _FORMAT_OPTIONS, value=BracketFormat.SINGLE_ELIM.value, label='Format',
                    ).classes('w-full')
                    stage_in = ui.number('Stage order', value=0, min=0).props('inputmode=numeric').classes('w-full')

                    with ui.expansion('Format / advancement options').classes('w-full'):
                        swiss_in = ui.number('Swiss rounds (optional)', min=1).props('inputmode=numeric').classes('w-full')
                        groups_in = ui.number('Round-robin group count (optional)', min=1).props('inputmode=numeric').classes('w-full')
                        ui.label('Advancement (stage > 0 only)').classes('text-caption text-grey')
                        adv_count_in = ui.number('Advance count (optional)', min=1).props('inputmode=numeric').classes('w-full')
                        adv_per_group_in = ui.switch('Per group', value=False)
                        adv_seeding_in = ui.select(
                            {'snake': 'Snake', 'preserve': 'Preserve'}, value='snake', label='Seeding',
                        ).classes('w-full')

                    async def submit() -> None:
                        config: Dict[str, object] = {}
                        if swiss_in.value:
                            config['swiss_rounds'] = int(swiss_in.value)
                        if groups_in.value:
                            config['group_count'] = int(groups_in.value)
                        if adv_count_in.value:
                            config['advancement'] = {
                                'count': int(adv_count_in.value),
                                'per_group': adv_per_group_in.value,
                                'seeding': adv_seeding_in.value,
                            }
                        with tenant_scope(tenant_id):
                            actor = await current_actor()
                            try:
                                await service.create_bracket(
                                    actor, tid, name_in.value or '', fmt_in.value,
                                    int(stage_in.value or 0), config or None,
                                )
                            except (ValueError, PermissionError) as ex:
                                notify_error(ex)
                                return
                        ui.notify('Bracket created', color='positive')
                        dialog.close()
                        await refresh_table()

                    with ui.row().classes('justify-end w-full q-mt-md'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Create', icon='add', on_click=submit).props('color=primary')
            dialog.open()

        # --- layout ------------------------------------------------------
        with page_container:
            ui.select(
                options, label='Tournament', on_change=on_tournament_change,
            ).classes('w-full max-w-md').props('outlined')

            with ui.row().classes('full-width q-mt-sm'):
                ui.button(
                    'Create bracket', icon='add',
                    on_click=lambda: open_create() if state['tournament_id'] else
                    ui.notify('Select a tournament first', color='warning'),
                ).props('color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS)

            table.on('manage', lambda e: background_tasks.create(open_manage(e.args, context.client)))
            table.on('results', lambda e: background_tasks.create(open_results(e.args, context.client)))
            table.on('complete', lambda e: background_tasks.create(complete_stage(e.args, context.client)))
            table.on('advance', lambda e: background_tasks.create(open_advance(e.args, context.client)))

        wire_tab_refresh('Brackets', refresh_table)
        background_tasks.create(refresh_table())
