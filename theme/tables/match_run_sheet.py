"""The run-sheet layout of a match board: one line per match, grouped by what it needs.

The card-per-match layout put every control on every match — stage select, seed
button, crew chips, stations, the lifecycle button and a pencil — at the same
weight, so a staff member looking for the one match that needed them read all
forty. Here a line carries only what identifies a match and where it stands;
everything you can *do* to it lives in the match sheet (``theme.dialog.match_sheet``)
that opens when the line is tapped.

Rows are arranged server-side (:func:`arrange_run_sheet`) rather than by column
sort: the groups *are* the order, so the columns are not sortable and a group
header rides on the first row of its group (``_group_start``).
"""

from datetime import datetime, timedelta, timezone

from application.utils.timezone import to_local, today_local

#: The board's columns. Kept short on purpose: anything wider than "which match,
#: when, where, how is it doing" belongs in the sheet.
RUN_SHEET_COLUMNS = [
    {'name': 'scheduled_at', 'label': 'Time', 'field': 'scheduled_at', 'align': 'left'},
    {'name': 'match', 'label': 'Match', 'field': 'title', 'align': 'left'},
    {'name': 'stage', 'label': 'Stage', 'field': 'stage', 'align': 'left'},
    {'name': 'crew', 'label': 'Crew', 'field': 'commentators', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'state', 'align': 'left'},
]

# (order, header) per group. Decisions first: a finished match nobody has
# confirmed is the only row on the board that is waiting on staff rather than on
# the clock.
_DECIDE = (0, 'Needs a decision')
_LIVE = (1, 'Live now')
_NEXT = (2, 'Up next')
_NO_PLAYERS = (3, 'Waiting for players')
_DONE = (4, 'Confirmed')


def run_sheet_status(row: dict) -> tuple[str, str]:
    """``(label, chip tone)`` for a row's status cell.

    One word or two, never the raw state plus a timestamp: "Late" and "No
    result" are what an operator acts on, and neither is a state.
    """
    state = row.get('state')
    if state == 'Finished':
        if row.get('needs_review'):
            return 'Flagged', 'cancelled'
        if not row.get('has_result'):
            return 'No result', 'cancelled'
        return 'To confirm', 'pending'
    if state == 'Confirmed':
        return 'Confirmed', 'ok'
    if state == 'Started':
        return 'Live', 'live'
    if not row.get('players'):
        return 'Waiting for players', 'neutral'
    if state == 'Checked In':
        return 'Checked in', 'neutral'
    if row.get('is_overdue'):
        return 'Late', 'pending'
    return 'Scheduled', 'neutral'


def _group(row: dict) -> tuple[int, str]:
    state = row.get('state')
    if state == 'Finished':
        return _DECIDE
    if state == 'Confirmed':
        return _DONE
    if state == 'Started':
        return _LIVE
    if not row.get('players'):
        return _NO_PLAYERS
    return _NEXT


def _day_label(ts) -> str:
    """'Today', 'Tomorrow', 'Yesterday', or the date, on the viewer's clock."""
    if ts is None:
        return ''
    local = to_local(datetime.fromtimestamp(ts, tz=timezone.utc))
    if local is None:
        return ''
    today = today_local()
    day = local.date()
    if day == today:
        return 'Today'
    if day == today + timedelta(days=1):
        return 'Tomorrow'
    if day == today - timedelta(days=1):
        return 'Yesterday'
    return f'{local:%a} {local.day} {local:%b}'


_CREW_ROLES = (('commentators', 'Commentary'), ('trackers', 'Tracking'))


def run_sheet_crew(row: dict) -> list[dict]:
    """Signups against need, per crew role the tournament uses.

    ``short`` marks a role with fewer signups than it needs, while that can
    still be fixed: once a match has started, a gap is history, not a task.
    """
    wanted = row.get('crew_wanted') or {}
    required = row.get('crew_required') or {}
    open_ = row.get('state') in ('Scheduled', 'Checked In')
    crew = []
    for key, label in _CREW_ROLES:
        people = row.get(key) or []
        if not (wanted.get(key) or people):
            continue
        need = required.get(key) or 0
        approved = sum(1 for p in people if p.get('approved'))
        count = f'{len(people)}/{need}' if need else str(len(people))
        crew.append({
            'label': label, 'count': count,
            'short': open_ and len(people) < need,
            'unapproved': open_ and len(people) >= need > approved,
        })
    return crew


def decorate_run_sheet_row(row: dict) -> dict:
    """Stamp the display fields the run-sheet templates read. Mutates ``row``."""
    label, tone = run_sheet_status(row)
    row['_status'] = label
    row['_tone'] = tone
    scheduled = row.get('scheduled_at') or ''
    row['_time'] = scheduled[-5:] if scheduled else ''
    row['_day'] = _day_label(row.get('scheduled_ts'))
    names = [p.get('name') or '' for p in row.get('players') or []]
    row['_who'] = ' vs '.join(names) if len(names) == 2 else ', '.join(names)
    if row.get('stage'):
        row['_stage'] = row['stage']
    elif row.get('is_stream_candidate'):
        row['_stage'] = 'Candidate'
    else:
        row['_stage'] = ''
    row['_crew'] = run_sheet_crew(row)
    return row


def arrange_run_sheet(rows: list) -> list:
    """Decorate, group and order ``rows``; mark the first row of each group.

    Inside a group the order is the clock, earliest first, except Confirmed,
    where the most recent result is the one anyone is still looking for.
    """
    for row in rows:
        decorate_run_sheet_row(row)

    def key(row):
        order, _ = _group(row)
        ts = row.get('scheduled_ts') or 0
        return (order, -ts if order == _DONE[0] else ts)

    arranged = sorted(rows, key=key)
    previous = None
    for row in arranged:
        _, header = _group(row)
        row['_group'] = header
        row['_group_start'] = header != previous
        previous = header
    return arranged


_STATUS_CHIP = '''<span class="wiz-chip" :class="'wiz-chip--' + props.row._tone">{{ props.row._status }}</span>'''

# Signups over need, per role. "needs crew" is spelled out rather than left to
# the amber, which no screen reader and not every eye can read.
_CREW = r'''<span v-for="c in props.row._crew" :key="c.label" class="run-sheet__crew" :class="c.short ? 'st-pending' : ''">{{ c.label }} <b>{{ c.count }}</b><template v-if="c.short"> · needs crew</template><template v-else-if="c.unapproved"> · to approve</template></span>'''

# Desktop: one row per match, a group header row above the first of each group.
# The Match cell's names are the row's button, so the row is reachable and
# operable from the keyboard; the rest of the row is a mouse convenience.
_BODY_SLOT = r'''
<q-tr v-if="props.row._group_start" class="run-sheet__group-row">
    <q-td colspan="100%" class="run-sheet__group">{{ props.row._group }}</q-td>
</q-tr>
<q-tr :props="props" class="run-sheet__row" :class="props.row._flash ? 'wiz-row-flash' : ''"
      @click="$parent.$emit('open_match', props.row.id)">
    <q-td v-for="col in props.cols" :key="col.name" :props="props">
        <template v-if="col.name === 'scheduled_at'">
            <span v-if="props.row._time" class="run-sheet__time" :class="props.row._status === 'Late' ? 'st-pending' : ''">{{ props.row._time }}</span>
            <span v-else class="run-sheet__day">No time</span>
            <span v-if="props.row._day && props.row._day !== 'Today'" class="run-sheet__day">{{ props.row._day }}</span>
        </template>
        <template v-else-if="col.name === 'match'">
            <button type="button" class="run-sheet__open" @click.stop="$parent.$emit('open_match', props.row.id)">
                {{ props.row._who || (props.row.bracket ? props.row.bracket.name : props.row.title) }}
            </button>
            <span class="run-sheet__meta">{{ props.row.tournament }}<template v-if="props.row.bracket"> · {{ props.row.bracket.name }}<template v-if="props.row.bracket.game"> · Game {{ props.row.bracket.game }}</template></template></span>
        </template>
        <template v-else-if="col.name === 'stage'">
            <span v-if="props.row._stage">{{ props.row._stage }}</span>
            <span v-else class="run-sheet__none">None</span>
        </template>
        <template v-else-if="col.name === 'crew'">
            <span class="run-sheet__crew-list">''' + _CREW + '''</span>
        </template>
        <template v-else-if="col.name === 'status'">''' + _STATUS_CHIP + '''</template>
        <template v-else>{{ col.value }}</template>
    </q-td>
</q-tr>
'''

# Phone: the whole line is one button. A plain "Scheduled" is the default, so
# the chip is left off it and the names get the width.
_ITEM_SLOT = r'''
<div class="run-sheet__item">
    <div v-if="props.row._group_start" class="run-sheet__group">{{ props.row._group }}</div>
    <button type="button" class="run-sheet__card" :class="props.row._flash ? 'wiz-row-flash' : ''"
            @click="$parent.$emit('open_match', props.row.id)">
        <span class="run-sheet__when">
            <span v-if="props.row._time" class="run-sheet__time" :class="props.row._status === 'Late' ? 'st-pending' : ''">{{ props.row._time }}</span>
            <span v-else class="run-sheet__day">No time</span>
            <span v-if="props.row._day && props.row._day !== 'Today'" class="run-sheet__day">{{ props.row._day }}</span>
        </span>
        <span class="run-sheet__main">
            <span class="run-sheet__who">{{ props.row._who || (props.row.bracket ? props.row.bracket.name : props.row.title) }}</span>
            <span class="run-sheet__meta">{{ props.row.tournament }}<template v-if="props.row._stage"> · {{ props.row._stage }}</template></span>
            <span v-if="props.row._crew.length" class="run-sheet__crew-list">''' + _CREW + '''</span>
        </span>
        <span v-if="props.row._status !== 'Scheduled'" class="wiz-chip" :class="'wiz-chip--' + props.row._tone">{{ props.row._status }}</span>
    </button>
</div>
'''


def register_run_sheet_slots(table) -> None:
    """The run sheet's desktop ``body`` and phone ``item`` slots on ``table``."""
    table.add_slot('body', _BODY_SLOT)
    table.add_slot('item', _ITEM_SLOT)
