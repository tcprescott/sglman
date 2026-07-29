# Wave 3 — a purpose-built proctor board

**Read [README.md](README.md) first.** **Waves 1 and 2 must be merged.**

Today `/volunteer` → *Proctor Station* renders `admin_schedule_page` with
`can_crud=False`: same page title ("Schedule Management"), same nine columns, two
of which the proctor never acts on. Wave 3 gives the proctor their own surface
while leaving the admin's Schedule tab exactly as it is.

**Constraint from the product owner: one proctor runs a room.** This is a *room*
board showing every match in flight. Do **not** build match→proctor assignment,
a "my matches" filter, or per-proctor worklists.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T3.1 | F2 | wave 2 | medium — refactor + new page |
| T3.2 | F2, F10 | T3.1 | medium |
| T3.3 | F6 | — | small |
| T3.4 | F11 | T3.1 | small |
| T3.5 | F12 | — | tiny |
| T3.6 | F13 | — | tiny |

T3.3, T3.5 and T3.6 are independent of the rest and can be done first if you want
early wins.

---

## T3.1 — Extract the lifecycle handlers, then give the proctor their own tab

**Why.** The proctor board needs the same lifecycle dialogs as the admin table but
a different frame around them. Copying ~120 lines of handler code into a second
page would guarantee drift (and `check_dry_regressions.py` may block it), so
extract first, then build the new page on the extraction.

### Step 1 — extract `MatchLifecycleHandlers`

New file `theme/tables/match_lifecycle.py`. Move the handler bodies out of
`pages/admin_tabs/admin_schedule.py` **unchanged in behaviour**:

```python
"""Dialog-backed lifecycle callbacks for a ``MatchTableView``.

Presentation-layer glue: opens the shared dialogs, calls the match services,
reports failures through ``notify_error``, and refreshes the row it touched.
The admin Schedule tab and the proctor board both build their view from an
instance of this, so their lifecycle behaviour cannot drift.

Construction is two-phase because the dependency is circular — the view needs
the callbacks, and the callbacks need the view to refresh a row::

    handlers = MatchLifecycleHandlers(page_container, can_crud=can_crud)
    table_view = MatchTableView(columns=..., get_query=..., **handlers.callbacks())
    handlers.table_view = table_view

The read-only ``Match.get(id=..., tenant_id=require_tenant_id())`` loads here are
the sanctioned presentation-layer load-or-404 shape (CLAUDE.md, entry surfaces);
every *write* goes through a service.
"""


class MatchLifecycleHandlers:
    def __init__(self, page_container, *, can_crud: bool):
        self.page_container = page_container
        self.can_crud = can_crud
        self.table_view = None          # assigned by the caller after the view exists
        self.schedule_service = MatchScheduleService()

    def callbacks(self) -> dict:
        """The ``on_*`` kwargs for ``MatchTableView``, gated by ``can_crud``.

        The crud-only three are omitted entirely rather than passed as ``None``:
        ``MatchTableView`` keys its slot registration off callback presence, so
        omission is what hides the control.
        """
        cb = {
            'on_generate_seed': self.on_generate_seed,
            'on_seat': self.on_seat,
            'on_start': self.on_start,
            'on_finish': self.on_finish,
            'on_assign_stations': self.on_assign_stations,
        }
        if self.can_crud:
            cb['on_edit'] = self.on_edit
            cb['on_confirm'] = self.on_confirm
            cb['on_edit_stream_room'] = self.on_edit_stream_room
        return cb
```

Move `on_edit`, `on_generate_seed`, `on_seat`, `confirm_seating`, `on_start`,
`confirm_starting`, `on_finish`, `confirm_finishing`, `on_confirm`,
`confirm_confirming`, `on_edit_stream_room` and `on_assign_stations` across as
methods, replacing the closed-over `table_view` with `self.table_view` and
`page_container` with `self.page_container`. Keep the T2.1 changes (the check-in
toast, `notify_error`, `purpose=` on the station dialog).

Then rewrite `pages/admin_tabs/admin_schedule.py` to use it. `submit_admin_match`
stays in the page — creating a match is a scheduling action, not a lifecycle one:

```python
        handlers = MatchLifecycleHandlers(page_container, can_crud=can_crud)
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            can_crud=can_crud,
            submit_match_callback=submit_admin_match if can_crud else None,
            extra_slots=extra_slots,
            **handlers.callbacks(),
        )
        handlers.table_view = table_view
```

**This is a refactor — the admin Schedule tab must behave identically.** Verify by
screenshotting `/admin/schedule` as `staff_user` before and after and diffing what
you see.

### Step 2 — the proctor tab

New file `pages/volunteer_tabs/proctor_station.py`:

```python
"""Proctor Station tab — the on-site match board.

One proctor runs a room, so this is a *room* board: every match in play, ordered
by what needs a proctor next. Deliberately not the admin Schedule tab — that one
is for scheduling matches, this one is for running them. It therefore drops the
crew, stage and scheduling columns and carries no create/edit controls.
"""

from nicegui import ui

from application.tenant_context import require_tenant_id
from models import Match
from theme.tables.match import MatchTableView
from theme.tables.match_lifecycle import MatchLifecycleHandlers

# Action-bearing columns first: on a phone-width table the right-hand columns are
# what gets clipped, and the proctor's next action must never be the clipped one.
PROCTOR_COLUMNS = [
    {'name': 'scheduled_at', 'label': 'Time', 'field': 'scheduled_at', 'sortable': True},
    {'name': 'state', 'label': 'Next step', 'field': 'state'},
    {'name': 'players', 'label': 'Players & stations', 'field': 'players'},
    {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament',
     'sortable': True, 'filterable': True},
    {'name': 'id', 'label': '#', 'field': 'id'},
]


async def proctor_station_tab() -> None:
    with ui.column().classes('page-container-wide') as page_container:
        with ui.row().classes('header-row'):
            ui.label('Proctor Station').classes('page-title')
        ui.label(
            'Every match in this room. Check players in, seat them, roll the seed, '
            'start them, then record the winner.'
        ).classes('text-caption text-grey')
        ui.separator().classes('separator-spacing')

        def get_query():
            return Match.filter(tenant_id=require_tenant_id())

        handlers = MatchLifecycleHandlers(page_container, can_crud=False)
        table_view = MatchTableView(
            columns=PROCTOR_COLUMNS,
            get_query=get_query,
            admin_controls=True,
            can_crud=False,
            exclude_racetime=True,      # T3.2
            row_sort=proctor_row_order,  # T3.2
            actions_first=True,          # T3.4
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Proctor Station' else None)
```

Note the `selected_tab` label is `'Proctor Station'` here, not `'Schedule'` — the
existing handler in `admin_schedule.py` keys off `'Schedule'`, which is why the
proctor tab's refresh-on-switch never fired before.

### Step 3 — point the tab at it

`pages/volunteer.py` (~line 38):

```python
        if is_proctor or is_staff:
            tabs.append({'label': 'Proctor Station', 'icon': 'sports_esports',
                         'content': proctor_station_tab})
```

Import `proctor_station_tab` from `pages.volunteer_tabs.proctor_station` and drop
the now-unused `admin_schedule_page` import. Note the tab slug stays
`proctor-station` (derived from the label by `theme.base.tab_slug`), so existing
deep links keep working.

Export `proctor_station_tab` from `pages/volunteer_tabs/__init__.py` if that file
re-exports the other tabs (check it — it is currently one line).

### Docs

`docs/reference/frontend.md` — the volunteer-tabs table (~line 220) says the
Proctor Station tab renders `admin_tabs/admin_schedule.py:admin_schedule_page`.
Update that row and the surrounding prose (~line 263) to name the new module and
say the two surfaces have deliberately diverged.

### Verify

`/t/default/volunteer/proctor-station` as `proctor_user` at 1500px and 430px:
six columns, no Commentators/Trackers/Stage, title "Proctor Station", no Create
Match button, and nothing clipped at the right edge. Then `/admin/schedule` as
`staff_user` — unchanged from before the refactor.

---

## T3.2 — Order the board by what needs doing, and drop the racetime noise

**Depends on:** T3.1.

**Why.** The board is in repository order across three days with the current hour
buried in the middle, and five of eleven seeded rows are racetime matches a
proctor cannot act on at all.

### Step 1 — sortable/overdue data on the row

`application/services/match/match_display_service.py`, in
`_format_match_for_display`, add two keys to the returned dict:

```python
            # Sort key and urgency flag for the proctor board. The formatted
            # ``scheduled_at`` string is display-only and does not sort.
            'scheduled_ts': match.scheduled_at.timestamp() if match.scheduled_at else None,
            'is_overdue': bool(
                match.scheduled_at
                and match.seated_at is None
                and match.finished_at is None
                and match.scheduled_at < datetime.now(timezone.utc)
            ),
```

Import `datetime, timezone` at the top of that module. `enforce_datetime_safety.py`
requires an aware UTC comparison — `match.scheduled_at` is stored aware, so this
is correct; do **not** use `datetime.utcnow()`.

### Step 2 — a `row_sort` hook on the view

`theme/tables/match.py`. Add `row_sort=None` and `exclude_racetime=False` to
`MatchTableView.__init__`, store both, and apply them in `refresh()` right before
`self.table.rows = rows`:

```python
        if self.row_sort is not None:
            rows = self.row_sort(rows)
```

Pass `exclude_racetime` through to the display service call in `refresh()`.

### Step 3 — the ordering function

Back in `pages/volunteer_tabs/proctor_station.py`:

```python
# What the proctor has to deal with next, most-urgent first. Within a bucket,
# earliest scheduled time wins.
_URGENCY = {
    'overdue':    0,   # scheduled time has passed and nobody is checked in
    'Checked In': 1,   # seated, waiting on a countdown
    'Started':    2,   # in play, watching for a raised hand
    'Scheduled':  3,   # not due yet
    'Finished':   4,   # proctor's work is done
    'Confirmed':  5,
}


def proctor_row_order(rows: list[dict]) -> list[dict]:
    def key(row):
        state = row.get('state') or 'Scheduled'
        bucket = _URGENCY['overdue'] if (state == 'Scheduled' and row.get('is_overdue')) \
            else _URGENCY.get(state, 3)
        return (bucket, row.get('scheduled_ts') or 0)
    return sorted(rows, key=key)
```

### Step 4 — the summary strip

Add an `on_rows_changed` callback to `MatchTableView.__init__` (default `None`),
invoked at the end of both `refresh()` and `update_row_by_id()` with
`self.table.rows`. In the proctor tab, use it to drive a `@ui.refreshable`
counter strip above the table:

```python
        @ui.refreshable
        def summary() -> None:
            rows = table_view.table.rows if table_view else []
            counts = {
                'To check in': sum(1 for r in rows if r['state'] == 'Scheduled'),
                'To start':    sum(1 for r in rows if r['state'] == 'Checked In'),
                'In play':     sum(1 for r in rows if r['state'] == 'Started'),
                'Overdue':     sum(1 for r in rows if r.get('is_overdue')),
            }
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                for label, n in counts.items():
                    tone = 'wiz-chip--pending' if (label == 'Overdue' and n) else 'wiz-chip--neutral'
                    ui.html(f'<span class="wiz-chip {tone}">{label}: {n}</span>')
```

Build `summary` **before** the view (so it exists to be referenced) and pass
`on_rows_changed=lambda _rows: summary.refresh()`. Guard against `table_view`
being `None` on the first render, as above.

### Step 5 — overdue emphasis on the row

`theme/tables/match_slots.py`, `SCHEDULED_AT_SLOT`:

```html
SCHEDULED_AT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <span class="cell-time" :class="props.row.is_overdue ? 'st-pending' : ''">{{ props.value }}</span>
    <q-icon v-if="props.row.is_overdue" name="schedule" class="st-pending q-ml-xs" size="xs">
        <q-tooltip>Past its scheduled time and not checked in</q-tooltip>
    </q-icon>
</q-td>'''
```

Mirror it on the mobile card headline in `theme/tables/match_grid.py`
(`render_grid_slot`, the `headline` fragment ~line 220) by adding the same
conditional class to `.mgc-time`.

### Step 6 — exclude racetime at the query

`application/repositories/match_repository.py`, `get_all` (~line 100): add
`exclude_racetime: bool = False` and, in the query build:

```python
        if exclude_racetime:
            query = query.filter(tournament__is_racetime_enabled=False)
```

Thread the same parameter through
`MatchDisplayService.get_matches_for_display`. Only the proctor board passes
`True`; every other caller keeps today's behaviour.

### Tests

`tests/services/test_match_display_service.py`:

```python
async def test_display_marks_an_unchecked_past_match_overdue(db)
async def test_display_does_not_mark_a_seated_past_match_overdue(db)
async def test_exclude_racetime_omits_racetime_tournament_matches(db)
```

`tests/theme/test_proctor_row_order.py` — pure function, no DB:

```python
def test_overdue_scheduled_sorts_above_checked_in()
def test_within_a_bucket_earlier_scheduled_time_wins()
def test_finished_sorts_below_everything_live()
def test_missing_scheduled_ts_does_not_raise()
```

### Verify

Screenshot the proctor board: no racetime rows, overdue rows at the top with an
amber time, and the summary strip counts matching what you can see. Confirm
`/admin/schedule` still shows racetime rows (only the proctor board excludes
them).

---

## T3.3 — Two winner buttons instead of a dropdown

**Why.** `MatchResultDialog` renders an empty `ui.select` labelled "Winner". The
players' names are not visible anywhere on the dialog until it is opened, and
their stations are not shown at all, so a proctor who identified the winner by
seat cannot cross-check. On a phone that is five interactions for the one action
that happens under time pressure.

### Files

- `theme/dialog/match_result_dialog.py`

### Change

Replace the `Select Winner:` block (~lines 61-73) so that a two-player match gets
one large button per player and anything else falls back to the select:

```python
                    ui.label('Who won?').classes('text-subtitle2')

                    if len(self.match.players) == 2:
                        # The overwhelmingly common case, and the one that happens
                        # under time pressure: one tap, name and station on the
                        # button so it can be checked against the room.
                        for player in self.match.players:
                            name = player.user.preferred_name or player.user.username
                            station = f'  ·  Station {player.assigned_station}' if player.assigned_station else ''
                            ui.button(
                                f'{name}{station}',
                                on_click=lambda _, pid=player.id: self._submit_winner(pid),
                            ).props('color=primary size=lg no-caps').classes('full-width q-mb-sm')
                    else:
                        player_options = {
                            p.id: (p.user.preferred_name or p.user.username)
                            for p in self.match.players
                        }
                        self.winner_select = ui.select(
                            options=player_options, label='Winner', with_input=True,
                        ).props('outlined required').classes('full-width')
```

Refactor `_handle_submit` into a `_submit_winner(winner_id)` that both paths call;
`_handle_submit` reads `self.winner_select.value` and delegates. Keep the
`Submit Results` button only on the select path — with the buttons, tapping a name
*is* the submit, so render only `Cancel` in `dialog_actions()`.

Guard the `bind_enabled_from` at line ~80: it dereferences `self.winner_select`,
which is now `None` on the two-player path. The existing
`if self.winner_select is not None:` already covers this — keep it.

Also add a line above the buttons naming the match so the proctor can confirm
they are on the right row:

```python
                ui.label(f'Match #{self.match.id}').classes('text-caption text-grey')
```

**Do not add forfeit / DQ / no-result options.** One winner and one loser is the
only outcome being modelled (README).

### Tests

`tests/theme/` cannot easily click NiceGUI buttons. Instead assert the service
contract this depends on stays true — `tests/services/test_match_service.py`:

```python
async def test_record_result_sets_rank_one_and_two_for_two_players(db)
async def test_record_result_rejects_a_non_participant_winner(db)
```

(Both may already exist — check before adding.)

### Verify

One-off Playwright: open the Finish dialog on a started match as `proctor_user`
and dump `.q-dialog` innerText. It must contain both players' names (and their
stations, once wave 2 seeds them) before anything is clicked. Click a name and
assert the row moves to Finished with that player emphasised. Check at 430px that
both buttons are full-width and reachable without scrolling.

---

## T3.4 — Put the action at the top of the mobile card

**Depends on:** T3.1.

**Why.** The card renders headline → players → caption → commentators → trackers
→ stage → seed → *then* the lifecycle button. On a phone the proctor scrolls past
four rows of metadata to reach "Start".

### Files

- `theme/tables/match_grid.py`
- `theme/tables/match.py`

### Change

`theme/tables/match_grid.py`, `render_grid_slot`: add an `actions_first: bool =
False` keyword and use it to assemble the template (~line 274):

```python
    template = (
        _CARD_OPEN + headline + players + actions + caption + details + _CARD_CLOSE
        if actions_first else
        _CARD_OPEN + headline + players + caption + details + actions + _CARD_CLOSE
    )
```

Update the module docstring's card-anatomy paragraph to mention both orders.

`theme/tables/match.py`: add `actions_first=False` to `MatchTableView.__init__`,
store it, and pass it to `render_grid_slot(...)` in `_setup_ui`. Only the proctor
tab passes `True`.

When `actions_first` is set, the actions row also needs its top border moved —
`.mgc-actions` is styled with a top border in `static/css/styles.css`. Add a
sibling class rather than editing the shared one:

```css
.mgc-actions--first { border-top: none; border-bottom: 1px solid var(--wiz-border); }
```

and emit `class="mgc-actions mgc-actions--first row items-center"` from `_ACTIONS`
when `actions_first`. Do this by substituting a placeholder the way the module
already substitutes `__IA__` — e.g. `__ACTCLS__`.

### Verify

430px screenshot of the proctor board: the lifecycle button sits directly under
the player names on every card, with the seed/tournament detail below it. Confirm
the home schedule board and the admin table (both `actions_first=False`) are
unchanged.

---

## T3.5 — Stop two different green checks meaning two different things

**Why.** The `check_circle` beside a player name is *player self-acknowledgment of
the assignment* — set days in advance, sometimes `(auto)`. The `check_circle` in
the State cell is *checked in*. A proctor scanning the Players column reads the
first as "this player is here", which it does not mean.

### Files

- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change

In `PLAYERS_SLOT` (`match_slots.py` ~line 265) and `_PLAYERS`
(`match_grid.py` ~line 59), change the two acknowledgment icons and their
tooltips. Keep the `st-ok` / `st-pending` colour classes:

```html
                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                            name="how_to_reg" class="st-ok" size="xs">
                        <q-tooltip>Confirmed they're playing{{ props.row.acknowledgments[idx].ts ? ' — ' + props.row.acknowledgments[idx].ts : '' }}. Not a check-in.</q-tooltip>
                    </q-icon>
                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                            name="person_outline" class="st-pending" size="xs">
                        <q-tooltip>Hasn't confirmed they're playing</q-tooltip>
                    </q-icon>
```

Leave the State cell's `check_circle` / `check` icons alone — that one genuinely
means checked in, and it is now the only check mark on the row.

### Verify

Hover both icons in the browser and read the tooltips back. Confirm at 430px that
`how_to_reg` and `person_outline` are legible at `size="xs"`; bump to `sm` if not.

---

## T3.6 — Say who won

**Why.** On a finished row the winner is conveyed only by `st-ok-strong` — colour
and font weight, no label, no icon, no legend.

### Files

- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change

In both `PLAYERS_SLOT` and `_PLAYERS`, after the player-name span, add:

```html
                    <span v-if="player.finish_rank === 1" class="wiz-chip wiz-chip--ok q-ml-xs">
                        <q-icon name="emoji_events" size="12px" />Winner</span>
```

Keep the existing `st-ok-strong` class on the name — the chip is additive, not a
replacement, so colour-blind and monochrome readers get the label while everyone
keeps the emphasis.

### Verify

Screenshot a Finished and a Confirmed row at both widths, in light and dark
theme. The chip must be legible in all four combinations — `.wiz-chip--ok`
already has dark-mode parity in `static/css/styles.css`, so do not add inline
colours.

---

## Wave 3 wrap-up

```bash
poetry run pytest
```

Browser-verify all four surfaces that share these templates, at 1500px and 430px:

- `/t/default/volunteer/proctor-station` as `proctor_user` — the new board
- `/t/default/admin/schedule` as `staff_user` — must be unchanged by T3.1
- `/t/default/` (home schedule) and `/t/default/home/player` as `player_one` —
  they embed the same players slot and read-only variants

Then run the flags-off sweep, because wave 3 adds a page that reaches
feature-gated services:

```bash
scripts/ui_flag_sweep.sh
```

Read the log half of its output, not just the pass/fail line — a tab that loads
through `background_tasks` fails after the DOM check.

Suggested PR split: *"Extract the match lifecycle handlers and give proctors
their own board"* (T3.1, T3.2, T3.4) and *"Make match results readable at a
glance"* (T3.3, T3.5, T3.6).
