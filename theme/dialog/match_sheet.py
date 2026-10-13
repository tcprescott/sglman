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


def _names(names: list) -> str:
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def readiness(row: dict, *, crew: bool = True) -> list[dict]:
    """The match sheet's checklist, one item per thing a match needs.

    ``ready`` is True or False for what a match can't start well without, and
    None for what's only information (no stage just means off stream). Seed and
    crew appear only where the tournament uses them, and crew only when the
    viewer looks after crew (``crew``).
    """
    players = row.get('players') or []
    acks = row.get('acknowledgments') or []
    items = []

    if not players:
        items.append({'key': 'players', 'label': 'Players', 'ready': False, 'detail': 'Not decided yet'})
    else:
        unconfirmed = [a.get('name') or '' for a in acks if not a.get('acknowledged')]
        if not unconfirmed:
            detail = 'Everyone has confirmed'
        elif len(unconfirmed) == len(players) and len(players) == 2:
            detail = f'Neither {unconfirmed[0]} nor {unconfirmed[1]} has confirmed'
        else:
            detail = f"{_names(unconfirmed)} {'hasn' if len(unconfirmed) == 1 else 'haven'}'t confirmed"
        items.append({'key': 'players', 'label': 'Players confirmed', 'ready': not unconfirmed, 'detail': detail})

        stations = [(p.get('name') or '', p.get('station')) for p in players]
        missing = [name for name, station in stations if not station]
        if len(missing) == len(stations):
            detail = 'Not assigned'
        else:
            detail = ' · '.join(f'{name} {station}' for name, station in stations if station)
            if missing:
                detail += f" · {_names(missing)} {'has' if len(missing) == 1 else 'have'} none"
        items.append({'key': 'stations', 'label': 'Stations', 'ready': not missing, 'detail': detail})

    stage = row.get('_stage') or ''
    items.append({
        'key': 'stage', 'label': 'Stage', 'ready': True if row.get('stage') else None,
        'detail': stage or 'No stage',
    })

    seed = row.get('generated_seed')
    if seed or row.get('tournament_seed_generator'):
        if seed:
            ready, detail = True, ''
        elif row.get('seed_rolling_since'):
            ready, detail = False, f"Rolling… {row.get('seed_rolling_label') or ''}".strip()
        elif row.get('seed_roll_error'):
            ready, detail = False, row['seed_roll_error']
        elif row.get('is_racetime'):
            ready, detail = None, 'The race room rolls it'
        else:
            ready, detail = False, 'Not rolled'
        items.append({'key': 'seed', 'label': 'Seed', 'ready': ready, 'detail': detail})

    wanted = row.get('crew_wanted') or {}
    required = row.get('crew_required') or {}
    need = approved = waiting = 0
    for key, _role, _label in _ROLES:
        if not wanted.get(key):
            continue
        people = row.get(key) or []
        got = sum(1 for p in people if p.get('approved'))
        need += max((required.get(key) or 0) - got, 0)
        approved += got
        waiting += sum(1 for p in people if not p.get('approved'))
    if crew and any(required.get(k) for k, _r, _l in _ROLES if wanted.get(k)):
        if need:
            detail = f'{need} more needed'
            if waiting:
                detail += f', {waiting} waiting for approval below'
        else:
            detail = 'Covered'
        items.append({'key': 'crew', 'label': 'Crew', 'ready': not need, 'detail': detail})
    return items


class MatchSheet:
    """The match sheet. Two-phase like the lifecycle handlers: set ``view`` after
    the board exists, since the board needs ``open`` as its callback."""

    def __init__(self, handlers, *, access: MatchBoardAccess, show_crew: bool = True,
                 decorate=decorate_run_sheet_row):
        self.handlers = handlers
        self.access = access
        # Off on the proctor's board: crew is not theirs to fix, so a crew gap
        # must not hold their checklist below "ready".
        self.show_crew = show_crew
        # The board's own row decorator, so the sheet's status chip says what
        # the line it opened from says.
        self.decorate = decorate
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
        self.decorate(row)
        with ui.column().classes('match-sheet__body full-width'):
            self._headline(row)
            self._status(row)
            self._setup(row)
            if self.show_crew:
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

    def _setup(self, row: dict) -> None:
        """The setup as a checklist: what's ready, what's missing, and the fix
        on the same line. Before the match starts it counts what's ready."""
        items = readiness(row, crew=self.show_crew)
        counted = [i for i in items if i['ready'] is not None]
        before = row.get('state') in ('Scheduled', 'Checked In')
        title = (f"Ready to play? {sum(1 for i in counted if i['ready'])} of {len(counted)}"
                 if before and counted else 'Setup')
        heading = ui.label(title).classes('match-sheet__section')
        heading.tag = 'h4'
        with ui.column().classes('match-sheet__checklist full-width gap-0'):
            for item in items:
                with ui.row().classes('match-sheet__check no-wrap full-width'):
                    if item['ready'] is True:
                        ui.icon('check_circle').classes('match-sheet__check-icon st-ok') \
                            .props('aria-label=Ready role=img')
                    elif item['ready'] is False:
                        ui.icon('error_outline').classes('match-sheet__check-icon st-pending') \
                            .props('aria-label="Not ready" role=img')
                    else:
                        ui.icon('remove_circle_outline').classes('match-sheet__check-icon text-muted') \
                            .props('aria-hidden=true')
                    with ui.column().classes('match-sheet__check-body col gap-1'):
                        ui.label(item['label']).classes('match-sheet__check-label')
                        getattr(self, f"_check_{item['key']}")(row, item)

    def _check_players(self, row: dict, item: dict) -> None:
        ui.label(item['detail']).classes('match-sheet__note')
        for player in row.get('players') or []:
            if player.get('ada'):
                name = player.get('name') or ''
                ui.button(f'{name}: ADA accommodation', icon='accessible',
                          on_click=lambda p=player: self.view._show_accommodation(
                              {'name': p.get('name'), 'note': p.get('ada_note')})) \
                    .props('flat dense no-caps color=primary').classes('self-start')

    def _check_stations(self, row: dict, item: dict) -> None:
        with ui.row().classes('items-center no-wrap full-width gap-2'):
            ui.label(item['detail']).classes('match-sheet__note col')
            if self.access.run and row.get('state') in ('Scheduled', 'Checked In', 'Started'):
                ui.button('Assign' if item['ready'] is False else 'Change',
                          on_click=lambda: self.handlers.on_assign_stations(row['id'])) \
                    .props('outline dense no-caps color=primary').classes('match-sheet__check-act')

    def _check_stage(self, row: dict, item: dict) -> None:
        match_id = row['id']
        with ui.row().classes('items-center no-wrap full-width gap-2'):
            if self.access.assign_stream and self.view is not None:
                options = {_NO_STAGE: 'No stage'}
                for opt in self.view._stage_options() or []:
                    if opt['value'] is not None:
                        options[opt['value']] = opt['label']
                current = row.get('stage_id') or (CANDIDATE_STAGE if row.get('is_stream_candidate') else _NO_STAGE)

                async def set_stage(e, mid=match_id):
                    value = e.value if e.value != _NO_STAGE else None
                    await self.handlers.on_set_stage(mid, value)

                ui.select(options, value=current, on_change=set_stage) \
                    .props('dense outlined options-dense aria-label="Stage"').classes('match-sheet__select col')
            else:
                ui.label(item['detail']).classes('match-sheet__note col')
            if row.get('stage_url'):
                ui.link('Watch', row['stage_url'], new_tab=True).classes('match-sheet__check-act')

    def _check_seed(self, row: dict, item: dict) -> None:
        seed = row.get('generated_seed')
        with ui.row().classes('items-center no-wrap full-width gap-2'):
            if seed and str(seed).startswith(('http://', 'https://')):
                ui.link(seed, seed, new_tab=True).classes('match-sheet__seed col')
            elif seed:
                ui.label(seed).classes('match-sheet__seed col')
            else:
                ui.label(item['detail']).classes(
                    'col ' + ('st-cancelled' if row.get('seed_roll_error') else 'match-sheet__note'))
            if seed:
                ui.button('Copy', on_click=lambda: copy_to_clipboard(seed, 'Seed')) \
                    .props('outline dense no-caps color=primary').classes('match-sheet__check-act')
            elif not row.get('seed_rolling_since') and self.access.run and seed_rollable(row):
                ui.button('Generate', on_click=lambda: self.handlers.on_generate_seed(row['id'])) \
                    .props('outline dense no-caps color=primary').classes('match-sheet__check-act')
        blocked = row.get('seed_dm_blocked') or []
        if seed and blocked:
            ui.label("Couldn't DM " + ', '.join(str(b) for b in blocked) + '. Hand them the seed.') \
                .classes('match-sheet__note')

    def _check_crew(self, row: dict, item: dict) -> None:
        ui.label(item['detail']).classes('match-sheet__note')

    def _crew(self, row: dict) -> None:
        wanted = row.get('crew_wanted') or {}
        roles = [r for r in _ROLES if wanted.get(r[0]) or row.get(r[0])]
        if not roles:
            return
        heading = ui.label('Crew').classes('match-sheet__section')
        heading.tag = 'h4'
        required = row.get('crew_required') or {}
        for key, role, label in roles:
            people = list(enumerate(row.get(key) or []))
            need = required.get(key) or 0
            approved = [(i, p) for i, p in people if p.get('approved')]
            waiting = [(i, p) for i, p in people if not p.get('approved')]
            with ui.column().classes('match-sheet__role full-width gap-2'):
                with ui.row().classes('match-sheet__role-head items-baseline no-wrap full-width'):
                    title = ui.label(label).classes('match-sheet__role-title col')
                    title.tag = 'h5'
                    if need and len(approved) < need and row.get('crew_signup_open'):
                        ui.label(f'{need - len(approved)} more needed').classes('match-sheet__short')
                if not people:
                    ui.label('No signups yet').classes('match-sheet__note italic-note')
                    continue
                with ui.row().classes('match-sheet__approved items-center'):
                    ui.label('Approved:' if approved else 'Approved: nobody yet').classes('match-sheet__note')
                    for idx, person in approved:
                        self._approved_pill(row, role, idx, person)
                if waiting:
                    self._waiting(row, role, waiting)

    def _profile(self, row: dict, role: str, idx: int):
        event = SimpleNamespace(args={'row': row, 'idx': idx})
        return lambda: self.view._handle_edit_role(role, event)

    def _toggle(self, row: dict, role: str, idx: int):
        event = SimpleNamespace(args={'row': row, 'idx': idx})
        return lambda: self.view._handle_toggle_approval(role, event)

    def _approved_pill(self, row: dict, role: str, idx: int, person: dict) -> None:
        name = person.get('name') or ''
        with ui.element('span').classes('match-sheet__pill'):
            ui.label(name).classes('match-sheet__pill-name')
            if person.get('acknowledged'):
                ui.label('confirmed').classes('match-sheet__pill-state st-ok')
            else:
                ui.label("hasn't confirmed").classes('match-sheet__pill-state')
            if self.access.approve_crew:
                with ui.button(icon='more_horiz').props(f'flat round dense size=sm color=primary aria-label="More for {name}"'):
                    with ui.menu():
                        ui.menu_item('Open profile', on_click=self._profile(row, role, idx))
                        ui.menu_item('Un-approve', on_click=self._toggle(row, role, idx))

    def _waiting(self, row: dict, role: str, waiting: list) -> None:
        # The people waiting on staff get the weight; approved crew shrinks to
        # pills above. Three runs of link-coloured text per person read as one blur.
        with ui.column().classes('match-sheet__waiting full-width gap-0'):
            heading = 'Waiting for you' if self.access.approve_crew else 'Signed up'
            ui.label(f'{heading} · {len(waiting)}').classes('match-sheet__waiting-head')
            for idx, person in waiting:
                with ui.row().classes('match-sheet__waiting-row items-center no-wrap full-width'):
                    name = person.get('name') or ''
                    if self.access.approve_crew:
                        ui.button(name, on_click=self._profile(row, role, idx), color=None) \
                            .props('flat dense no-caps align=left').classes('match-sheet__waiting-name col') \
                            .tooltip(f"Open {name}'s profile")
                        ui.button('Approve', on_click=self._toggle(row, role, idx)).props('no-caps color=primary')
                    else:
                        ui.label(name).classes('match-sheet__waiting-name col')

    def _footer(self, row: dict) -> None:
        if not self.access.edit:
            return
        with dialog_actions().classes('justify-end'):
            ui.button('Edit match', icon='edit', on_click=lambda: self.handlers.on_edit(row['id'])) \
                .props('flat color=primary')
