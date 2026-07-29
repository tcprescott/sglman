"""Admin Brackets page — native tournament brackets management (STAFF).

Staff-facing surface over :class:`~application.services.bracket_service.BracketService`:
pick a tournament, author its bracket stages (create/edit/delete while DRAFT),
manage the tournament roster and per-stage enrollment/seeding, start a stage,
record results (with overrides), complete a stage, and advance the field into the
next stage.

This module owns the layout — the tournament selector, the stage table and its
row-action dispatch; the three dialogs live beside it in this package. Every row
action is ``v-if``-gated on the row's own state, so the table never offers a
transition the service would refuse.

Presentation-only: renders NiceGUI, calls the service for every write, and shows
service ``ValueError`` / ``PermissionError`` as toasts. Read-only ``Tournament``
lookups for the selector are the sanctioned display query. All scoped reads and
service calls run inside ``tenant_scope`` because row-action handlers and the
tournament selector fire from detached client events that have lost the tenant
contextvar.
"""

from typing import Dict, Optional

from nicegui import background_tasks, context, ui

from application.services import BracketService
from application.tenant_context import require_tenant_id, tenant_scope
from models import BracketState, Tournament
from theme.brackets import FORMAT_OPTIONS
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid

from .manage import open_manage
from .results import open_results
from .shared import ELIM_FORMATS, entry_name_map
from .stage_form import confirm_delete_stage, open_stage_form

# Every action is `v-if`-gated on the row's own state: the service guards each
# transition anyway, so an ungated button could only ever produce a toast
# explaining why it was never going to work. The one exception is the disabled
# `flag` on an elimination stage — that one is present to say *why* completing is
# not something staff do there, rather than to be clicked.
_ROW_ACTIONS = '''
    <q-btn v-if="props.row.state !== 'complete'" flat round dense icon="tune" color="primary"
           @click="$parent.$emit('manage', props.row)">
        <q-tooltip>{{ props.row.state === 'draft' ? 'Entrants, seeding & start' : 'Entrants & round settings' }}</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.state !== 'draft'" flat round dense icon="scoreboard" color="primary"
           @click="$parent.$emit('results', props.row)">
        <q-tooltip>Results</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.can_complete" flat round dense icon="flag" color="secondary"
           @click="$parent.$emit('complete', props.row)">
        <q-tooltip>Complete stage</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.state === 'active' && props.row.is_elim" flat round dense
           icon="flag" color="grey" disable>
        <q-tooltip>Completes itself when the final resolves</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.can_advance" flat round dense icon="fast_forward" color="secondary"
           @click="$parent.$emit('advance', props.row)">
        <q-tooltip>Advance the field into the next stage</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.state === 'draft'" flat round dense icon="edit" color="primary"
           @click="$parent.$emit('edit', props.row)">
        <q-tooltip>Edit stage</q-tooltip>
    </q-btn>
    <q-btn v-if="props.row.state === 'draft'" flat round dense icon="delete" color="negative"
           @click="$parent.$emit('remove', props.row)">
        <q-tooltip>Delete stage</q-tooltip>
    </q-btn>
'''


async def admin_brackets_page() -> None:
    service = BracketService()
    # Captured while the request context is live; rebound around every detached
    # client-event handler (see module docstring).
    tenant_id = require_tenant_id()
    state: Dict[str, Optional[int]] = {'tournament_id': None}
    # The Results dialog embeds the shared bracket renderer for click-to-report.
    ui.add_head_html('<link rel="stylesheet" href="/static/css/brackets.css">')

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Brackets').classes('page-title')
        ui.separator().classes('separator-spacing')

        ui.label(
            'Native tournament brackets. Pick a tournament, author its stages, '
            'manage the roster and seeding, then start, record results, complete '
            'a stage, and advance into the next.'
        ).classes('text-caption text-grey')

        # Challonge-linked tournaments are excluded, not just sorted down: a
        # tournament uses a native bracket or a Challonge link and never both, so
        # every one of them could only ever answer "Create bracket" with an error.
        # Inactive ones stay — their existing stages must remain reachable — but
        # sort last and say so.
        tournaments = await Tournament.filter(
            tenant_id=tenant_id, challonge_tournament_id__isnull=True,
        ).order_by('-is_active', 'name')
        options = {
            t.id: t.name if t.is_active else f'{t.name} (inactive)'
            for t in tournaments
        }

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
            stage_orders = {b.stage_order for b in brackets}
            table.rows = [
                {
                    'id': b.id,
                    'stage_order': b.stage_order,
                    'name': b.name,
                    'format': FORMAT_OPTIONS.get(b.format.value, b.format.value),
                    'state': b.state.value,
                    'is_elim': b.format in ELIM_FORMATS,
                    # Elimination completes itself when the final resolves, so the
                    # explicit finalizer is a Swiss / round-robin action only.
                    'can_complete': (
                        b.state == BracketState.ACTIVE and b.format not in ELIM_FORMATS
                    ),
                    'can_advance': (
                        b.state == BracketState.COMPLETE
                        and (b.stage_order + 1) in stage_orders
                    ),
                }
                for b in brackets
            ]
            table.update()

        def on_tournament_change(e) -> None:
            state['tournament_id'] = e.value
            background_tasks.create(refresh_table())

        def next_stage_order() -> int:
            """The stage order a new stage should default to."""
            if not table.rows:
                return 0
            return max(r['stage_order'] for r in table.rows) + 1

        # --- complete stage ----------------------------------------------
        async def complete_stage(row, client) -> None:
            """Confirm, then finalize the stage.

            ``complete_stage`` writes every entry's ``final_rank`` and locks the
            stage — there is no un-complete — and this fires from one of several
            adjacent 44px icon buttons on a phone card, so it asks first.
            """
            with client:
                async def do_complete() -> None:
                    confirm.dialog.close()
                    actor = await current_actor()
                    with tenant_scope(tenant_id):
                        try:
                            await service.complete_stage(actor, row['id'])
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    ui.notify('Stage completed', color='positive')
                    await refresh_table()

                confirm = ConfirmationDialog(
                    f"Complete “{row['name']}”? This writes every entrant's final "
                    'rank and locks the stage — it cannot be undone.',
                    on_confirm=do_complete,
                    confirm_text='Complete stage',
                )
                confirm.open()

        # --- advance stage (preview + confirm) ---------------------------
        async def open_advance(row, client) -> None:
            tid = state['tournament_id']
            from_stage_order = row['stage_order']
            with client:
                actor = await current_actor()
                with tenant_scope(tenant_id):
                    try:
                        preview = await service.get_advancing_preview(tid, from_stage_order)
                        names = await entry_name_map(service, row['id'], tid)
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return

                with form_dialog(f"Advance from stage {from_stage_order}") as dialog:
                    ui.label(
                        f'{len(preview)} entrant(s) would advance into the next stage:'
                    ).classes('text-caption text-grey')
                    for e in preview:
                        ui.label(
                            f'#{e.final_rank} — {names.get(e.id, f"Entry {e.id}")}'
                        ).classes('ellipsis w-full')

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

                    with dialog_actions().classes('justify-end'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Advance', icon='fast_forward', on_click=do_advance).props('color=primary')
                dialog.open()

        # --- dialog dispatch ---------------------------------------------
        def _dialog_kwargs() -> dict:
            return {
                'service': service,
                'tenant_id': tenant_id,
                'tournament_id': state['tournament_id'],
                'on_change': refresh_table,
            }

        async def create_stage(client) -> None:
            await open_stage_form(
                client, default_stage_order=next_stage_order(), **_dialog_kwargs(),
            )

        async def edit_stage(row, client) -> None:
            await open_stage_form(client, row=row, **_dialog_kwargs())

        # --- layout ------------------------------------------------------
        with page_container:
            selector = ui.select(
                options, label='Tournament', with_input=True,
                on_change=on_tournament_change,
            ).classes('w-full max-w-md').props('outlined')
            selector.add_slot('no-option', '''
                <q-item><q-item-section class="text-grey">
                    No tournament matches
                </q-item-section></q-item>
            ''')
            if not options:
                ui.label(
                    'No tournament is eligible for a native bracket — every one in '
                    'this community is linked to a Challonge bracket, which a '
                    'native bracket cannot coexist with.'
                ).classes('text-caption text-warning')
            elif len(options) == 1:
                # One choice is not a choice: pick it rather than making the first
                # thing anyone does on this page be confirming the obvious.
                only_id = next(iter(options))
                selector.value = only_id
                state['tournament_id'] = only_id

            with ui.row().classes('full-width q-mt-sm'):
                ui.button(
                    'Create bracket', icon='add',
                    on_click=lambda: background_tasks.create(create_stage(context.client))
                    if state['tournament_id'] else
                    ui.notify('Select a tournament first', color='warning'),
                ).props('color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS)

            table.on('manage', lambda e: background_tasks.create(
                open_manage(e.args, context.client, **_dialog_kwargs())))
            table.on('results', lambda e: background_tasks.create(
                open_results(e.args, context.client, **_dialog_kwargs())))
            table.on('complete', lambda e: background_tasks.create(complete_stage(e.args, context.client)))
            table.on('advance', lambda e: background_tasks.create(open_advance(e.args, context.client)))
            table.on('edit', lambda e: background_tasks.create(edit_stage(e.args, context.client)))
            table.on('remove', lambda e: background_tasks.create(confirm_delete_stage(
                e.args, context.client, service=service, tenant_id=tenant_id,
                on_change=refresh_table)))

        wire_tab_refresh('Brackets', refresh_table)
        background_tasks.create(refresh_table())
