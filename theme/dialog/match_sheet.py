"""Everything staff can do to one match, in one sheet.

The run-sheet board (``theme.tables.match_run_sheet``) shows a line per match and
opens this when a line is tapped: a side sheet on a desktop, a full-screen sheet
on a phone. It reads the board's own row for the match, so a change made here or
by someone else elsewhere repaints it through the same live update that repaints
the line (:meth:`MatchSheet.sync`).

Every control calls the board's existing callbacks — ``MatchLifecycleHandlers``
for the lifecycle, stage, seed and stations, the view's handlers for crew — so
the sheet adds no second path to a service, and each control shows only when the
viewer's ``MatchBoardAccess`` covers it.
"""

from types import SimpleNamespace
from typing import Any, Optional

from nicegui import ui

from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_actions, dialog_header
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_run_sheet import decorate_run_sheet_row
from theme.tables.match_slots import CANDIDATE_STAGE

_NO_STAGE = ''

_STATE_SINCE = {
    'Checked In': 'Checked in at',
    'Started': 'Started at',
    'Finished': 'Finished at',
    'Confirmed': 'Confirmed at',
}

_ROLES = (
    # (row key, singular used by the view's handlers, heading)
    ('commentators', 'commentator', 'Commentary'),
    ('trackers', 'tracker', 'Tracking'),
)


def seed_rollable(row: dict) -> bool:
    """Python twin of ``match_slots.SEED_ROLLABLE``: may a seed be rolled now."""
    return bool(
        row.get('tournament_seed_generator') and not row.get('is_racetime')
        and row.get('players')
        and row.get('state') not in ('Finished', 'Confirmed')
    )


class MatchSheet:
    """The match sheet. Two-phase like the lifecycle handlers: set ``view`` after
    the board exists, since the board needs ``open`` as its callback."""

    def __init__(self, handlers, *, access: MatchBoardAccess):
        self.handlers = handlers
        self.access = access
        self.view: Any = None
        self.row: Optional[dict] = None
        # mobile_sheet's own breakpoint, but a side sheet rather than a centred
        # card above it: the board stays readable beside the open match.
        with ui.dialog().props(''':position="Quasar.Screen.lt.sm ? 'bottom' : 'right'"''') as self.dialog, \
                ui.card().classes('dialog-card match-sheet'):
            dialog_header('Match details', self.dialog)
            self._content = ui.refreshable(self._render)
            self._content()
        self.dialog.on('hide', self._closed)

    def _closed(self) -> None:
        self.row = None

    async def open(self, match_id) -> None:
        row = self._find(match_id)
        if row is None:
            return
        self.row = row
        with self.dialog:
            self._content.refresh()
            self.dialog.open()

    def sync(self, rows) -> None:
        """Repaint from the board's latest copy of the open match's row."""
        if self.row is None:
            return
        fresh = next((r for r in rows if r.get('id') == self.row.get('id')), None)
        if fresh is not None:
            self.row = fresh
        self._content.refresh()

    def _find(self, match_id) -> Optional[dict]:
        rows = self.view.table.rows if self.view else []
        return next((r for r in rows if r.get('id') == match_id), None)

    # -- rendering -------------------------------------------------------

    def _render(self) -> None:
        row = self.row
        if row is None:
            return
        decorate_run_sheet_row(row)
        with ui.column().classes('match-sheet__body full-width'):
            self._headline(row)
            self._status(row)
            self._setup(row)
            self._crew(row)
        self._footer(row)

    def _headline(self, row: dict) -> None:
        when = ' '.join(part for part in (row.get('_day'), row.get('_time')) if part)
        context = ' · '.join(part for part in (when, row.get('tournament')) if part)
        ui.label(context).classes('match-sheet__note')
        title = row.get('_who') or (row.get('bracket') or {}).get('name') or row.get('title') or 'Match'
        heading = ui.label(title).classes('match-sheet__title')
        heading.tag = 'h3'
        bracket = row.get('bracket')
        if bracket and bracket.get('id'):
            label = bracket.get('name') or 'Bracket'
            if bracket.get('game'):
                label += f" · Game {bracket['game']}"
            ui.button(label, icon='account_tree',
                      on_click=lambda: self.view._handle_open_bracket(SimpleNamespace(args=row))) \
                .props('flat dense no-caps color=primary').classes('self-start')

    def _status(self, row: dict) -> None:
        with ui.row().classes('items-center gap-2 full-width match-sheet__status'):
            with ui.element('span').classes(f"wiz-chip wiz-chip--{row['_tone']}"):
                ui.label(row['_status'])
            since = _STATE_SINCE.get(row.get('state') or '')
            if since and row.get('state_time'):
                ui.label(f"{since} {row['state_time']}").classes('match-sheet__note')
            ui.space()
            self._primary_actions(row)

    def _primary_actions(self, row: dict) -> None:
        """The one thing to do next, and the result correction beside a result."""
        match_id = row['id']
        state = row.get('state')
        h = self.handlers
        if self.access.run and row.get('players') and not row.get('is_racetime'):
            if state == 'Scheduled':
                ui.button('Check in', icon='event_seat',
                          on_click=lambda: h.on_seat(match_id)).props('color=primary')
            elif state == 'Checked In':
                ui.button('Start match', icon='play_arrow',
                          on_click=lambda: h.on_start(match_id)).props('color=primary')
            elif state == 'Started':
                ui.button('Finish', icon='sports_score',
                          on_click=lambda: h.on_finish(match_id)).props('color=primary')
        if self.access.confirm and state == 'Finished':
            if not row.get('has_result'):
                ui.button('Record winner', icon='emoji_events',
                          on_click=lambda: h.on_edit_result(match_id)).props('color=primary')
            else:
                ui.button('Change result', on_click=lambda: h.on_edit_result(match_id)) \
                    .props('flat color=primary')
                ui.button('Review result' if row.get('needs_review') else 'Confirm result',
                          icon='verified', on_click=lambda: h.on_confirm(match_id)) \
                    .props('color=primary')
        if self.access.confirm and state == 'Confirmed':
            ui.button('Change result', on_click=lambda: h.on_edit_result(match_id)) \
                .props('flat color=primary')
        if row.get('is_racetime') and state not in ('Finished', 'Confirmed'):
            ui.label('Runs on racetime.gg').classes('match-sheet__note')

    def _field(self, label: str):
        """One label/value line; returns the value cell to build into."""
        ui.label(label).classes('match-sheet__label')
        return ui.column().classes('match-sheet__value gap-1')

    def _setup(self, row: dict) -> None:
        match_id = row['id']
        h = self.handlers
        heading = ui.label('Setup').classes('match-sheet__section')
        heading.tag = 'h4'
        with ui.element('div').classes('match-sheet__fields'):
            players = row.get('players') or []
            acks = row.get('acknowledgments') or []
            with self._field('Players'):
                if not players:
                    ui.label('Not decided yet').classes('match-sheet__note')
                for idx, player in enumerate(players):
                    with ui.column().classes('gap-0'):
                        with ui.row().classes('items-center gap-1'):
                            winner = player.get('finish_rank') == 1
                            ui.label(player.get('name') or '').classes('st-ok-strong' if winner else '')
                            if winner:
                                ui.label('(winner)').classes('match-sheet__note')
                            if player.get('ada'):
                                ui.button(icon='accessible', on_click=lambda p=player: self.view._show_accommodation(
                                    {'name': p.get('name'), 'note': p.get('ada_note')})) \
                                    .props('flat round dense size=sm color=primary') \
                                    .tooltip('ADA accommodation')
                        notes = []
                        if player.get('station'):
                            notes.append(f"Station {player['station']}")
                        ack = acks[idx] if idx < len(acks) else None
                        if ack and not ack.get('acknowledged'):
                            notes.append("hasn't confirmed they're playing")
                        if notes:
                            ui.label(' · '.join(notes)).classes('match-sheet__note')
            if self.access.run and players \
                    and row.get('state') in ('Scheduled', 'Checked In', 'Started'):
                ui.button('Stations', on_click=lambda: h.on_assign_stations(match_id)) \
                    .props('flat dense no-caps color=primary').classes('match-sheet__act')
            else:
                ui.element('span')

            with self._field('Stage'):
                if self.access.assign_stream and self.view is not None:
                    options = {_NO_STAGE: 'No stage'}
                    for opt in self.view._stage_options() or []:
                        if opt['value'] is not None:
                            options[opt['value']] = opt['label']
                    current = row.get('stage_id') or (CANDIDATE_STAGE if row.get('is_stream_candidate') else _NO_STAGE)

                    async def set_stage(e, mid=match_id):
                        value = e.value if e.value != _NO_STAGE else None
                        await h.on_set_stage(mid, value)

                    ui.select(options, value=current, on_change=set_stage) \
                        .props('dense outlined options-dense aria-label="Stage"').classes('match-sheet__select')
                else:
                    ui.label(row.get('_stage') or 'None').classes('' if row.get('_stage') else 'text-muted')
            if row.get('stage_url'):
                ui.link('Watch', row['stage_url'], new_tab=True).classes('match-sheet__act')
            else:
                ui.element('span')

            with self._field('Seed'):
                seed = row.get('generated_seed')
                if seed:
                    if str(seed).startswith(('http://', 'https://')):
                        ui.link(seed, seed, new_tab=True).classes('match-sheet__seed')
                    else:
                        ui.label(seed).classes('match-sheet__seed')
                elif row.get('seed_rolling_since'):
                    ui.label(f"Rolling… {row.get('seed_rolling_label') or ''}").classes('match-sheet__note')
                elif row.get('seed_roll_error'):
                    ui.label(row['seed_roll_error']).classes('st-cancelled')
                else:
                    ui.label('Not rolled').classes('match-sheet__note')
                blocked = row.get('seed_dm_blocked') or []
                if seed and blocked:
                    ui.label("Couldn't DM " + ', '.join(str(b) for b in blocked) + '. Hand them the seed.') \
                        .classes('match-sheet__note')
            if seed and not str(seed).startswith(('http://', 'https://')):
                ui.button('Copy', on_click=lambda: copy_to_clipboard(seed, 'Seed')) \
                    .props('flat dense no-caps color=primary').classes('match-sheet__act')
            elif not seed and not row.get('seed_rolling_since') and self.access.run \
                    and seed_rollable(row):
                ui.button('Generate seed', on_click=lambda: h.on_generate_seed(match_id)) \
                    .props('flat dense no-caps color=primary').classes('match-sheet__act')
            else:
                ui.element('span')

    def _crew(self, row: dict) -> None:
        wanted = row.get('crew_wanted') or {}
        roles = [r for r in _ROLES if wanted.get(r[0]) or row.get(r[0])]
        if not roles:
            return
        heading = ui.label('Crew').classes('match-sheet__section')
        heading.tag = 'h4'
        required = row.get('crew_required') or {}
        with ui.element('div').classes('match-sheet__fields'):
            for key, role, label in roles:
                people = row.get(key) or []
                need = required.get(key)
                approved = sum(1 for p in people if p.get('approved'))
                with self._field(label):
                    if not people:
                        ui.label('No signups yet').classes('match-sheet__note italic-note')
                    for idx, person in enumerate(people):
                        self._crew_person(row, role, idx, person)
                if need and approved < need:
                    ui.label(f'{need - approved} more needed').classes('match-sheet__note match-sheet__act')
                else:
                    ui.element('span')

    def _crew_person(self, row: dict, role: str, idx: int, person: dict) -> None:
        event = SimpleNamespace(args={'row': row, 'idx': idx})
        if person.get('approved') and person.get('acknowledged'):
            note = 'confirmed'
        elif person.get('approved'):
            note = "approved, hasn't confirmed"
        else:
            note = 'signed up'
        with ui.row().classes('items-center gap-1'):
            if self.access.approve_crew:
                ui.button(person.get('name') or '', on_click=lambda: self.view._handle_edit_role(role, event)) \
                    .props('flat dense no-caps color=primary').classes('match-sheet__name')
            else:
                ui.label(person.get('name') or '')
            ui.label(note).classes('match-sheet__note')
            if self.access.approve_crew:
                ui.button('Un-approve' if person.get('approved') else 'Approve',
                          on_click=lambda: self.view._handle_toggle_approval(role, event)) \
                    .props('flat dense no-caps color=primary')

    def _footer(self, row: dict) -> None:
        if not self.access.edit:
            return
        with dialog_actions().classes('justify-end'):
            ui.button('Edit match', icon='edit', on_click=lambda: self.handlers.on_edit(row['id'])) \
                .props('flat color=primary')
