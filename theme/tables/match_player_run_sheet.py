"""The run sheet for the Event > Schedule board everyone reads.

The same one-line-per-match board staff got (``match_run_sheet``), with the
buttons a player or volunteer actually uses left on the line: their own crew
Sign up / Withdraw next to each role, Acknowledge on a match they play, and the
watch bell. Anything else about a match (seed, stations, who's confirmed) is in
the details sheet a tapped line opens.

The viewer's own state is stamped server-side by :func:`arrange_player_run_sheet`
rather than worked out in the templates, so the rules live in one tested place:
a line's buttons are only ever as current as its row, which the board already
re-fetches after every change.
"""

from theme.tables.match_run_sheet import decorate_run_sheet_row

PLAYER_RUN_SHEET_COLUMNS = [
    {'name': 'scheduled_at', 'label': 'Time', 'field': 'scheduled_at', 'align': 'left'},
    {'name': 'match', 'label': 'Match', 'field': 'title', 'align': 'left'},
    {'name': 'stage', 'label': 'Stage', 'field': 'stage', 'align': 'left'},
    {'name': 'crew', 'label': 'Crew', 'field': 'commentators', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'state', 'align': 'left'},
    {'name': 'watch', 'label': 'Watch', 'field': 'watch', 'align': 'center'},
]

# (order, header) per group. What's happening now leads; results trail, newest
# first, for whoever brought them back with the State filter.
_LIVE = (0, 'Live now')
_NEXT = (1, 'Up next')
_NO_PLAYERS = (2, 'Waiting for players')
_DONE = (3, 'Finished')

_ROLES = (
    # (row key, singular the board's handlers take, label)
    ('commentators', 'commentator', 'Commentary'),
    ('trackers', 'tracker', 'Tracking'),
)


def player_status(row: dict) -> tuple[str, str]:
    """``(label, chip tone)`` for the Status cell, in a player's words.

    "To confirm" and "No result" are staff's to-do list, not something a player
    can act on, so a recorded result reads as Finished until it's official.
    """
    state = row.get('state')
    if state == 'Confirmed':
        return 'Confirmed', 'ok'
    if state == 'Finished':
        return 'Finished', 'neutral'
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
    if state in ('Finished', 'Confirmed'):
        return _DONE
    if state == 'Started':
        return _LIVE
    if not row.get('players'):
        return _NO_PLAYERS
    return _NEXT


def player_crew(row: dict, discord_id) -> list[dict]:
    """One entry per crew role the tournament uses, with the viewer's place in it.

    ``count`` is approved crew over need: someone waiting on approval hasn't
    filled the slot (the rule the Needs crew switch uses). ``mine`` is
    ``'approved'``, ``'waiting'`` or None; ``can_sign_up`` mirrors the gate the
    old crew cell used (``match_slots.CREW_CAN_SIGN_UP_JS``), and ``ack_idx`` is
    set when the viewer is approved but hasn't confirmed they'll cover it.
    """
    wanted = row.get('crew_wanted') or {}
    required = row.get('crew_required') or {}
    open_ = bool(row.get('crew_signup_open'))
    plays = bool(discord_id) and any(
        str(p.get('discord_id')) == str(discord_id) for p in row.get('players') or [])
    roles = []
    for key, singular, label in _ROLES:
        people = row.get(key) or []
        if wanted.get(key) is False or not (wanted.get(key) or people):
            continue
        need = required.get(key, 1) or 0
        approved = sum(1 for p in people if p.get('approved'))
        mine, ack_idx = None, None
        if discord_id:
            for idx, person in enumerate(people):
                if str(person.get('discord_id')) == str(discord_id):
                    mine = 'approved' if person.get('approved') else 'waiting'
                    if person.get('approved') and not person.get('acknowledged'):
                        ack_idx = idx
                    break
        roles.append({
            'key': key,
            'singular': singular,
            'label': label,
            'count': f'{approved}/{need}' if need else str(approved),
            'short': open_ and approved < need,
            'mine': mine,
            'can_sign_up': bool(discord_id) and open_ and mine is None and not plays,
            'can_withdraw': mine is not None,
            'ack_idx': ack_idx,
        })
    return roles


def needs_my_ack(row: dict, discord_id) -> bool:
    """Whether the viewer plays this match and hasn't acknowledged it yet."""
    if not discord_id:
        return False
    return any(
        str(a.get('discord_id')) == str(discord_id) and not a.get('acknowledged')
        for a in row.get('acknowledgments') or []
    )


def decorate_player_row(row: dict, discord_id) -> dict:
    """The run sheet's display fields plus the viewer's own. Mutates ``row``."""
    decorate_run_sheet_row(row)
    label, tone = player_status(row)
    row['_status'] = label
    row['_tone'] = tone
    row['_roles'] = player_crew(row, discord_id)
    row['_ack'] = needs_my_ack(row, discord_id)
    row['_mine'] = bool(discord_id) and any(
        str(p.get('discord_id')) == str(discord_id) for p in row.get('players') or [])
    return row


def arrange_player_run_sheet(rows: list, discord_id) -> list:
    """Decorate, group and order ``rows``; mark the first row of each group."""
    for row in rows:
        decorate_player_row(row, discord_id)

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


_WHEN = r'''<span v-if="props.row._time" class="run-sheet__time" :class="props.row._status === 'Late' ? 'st-pending' : ''">{{ props.row._time }}</span>
<span v-else class="run-sheet__day">No time</span>
<span v-if="props.row._day && props.row._day !== 'Today'" class="run-sheet__day">{{ props.row._day }}</span>'''

_TITLE = "props.row._who || (props.row.bracket ? props.row.bracket.name : props.row.title)"

_YOU = '<span v-if="props.row._mine" class="player-sheet__you">You</span>'

# One role: its count, then the viewer's own control. "needs crew" is spelled
# out rather than left to the amber. Every button stops the click so pressing it
# doesn't also open the details sheet.
_ROLE = r'''<span class="run-sheet__crew" :class="c.short ? 'st-pending' : ''">{{ c.label }} <b>{{ c.count }}</b><template v-if="c.short"> · needs crew</template></span>
<span class="player-sheet__act">
<span v-if="c.mine" class="player-sheet__mine">You · {{ c.mine === 'approved' ? 'approved' : 'waiting for approval' }}</span>
<q-btn v-if="c.ack_idx !== null" outline no-caps no-wrap color="primary" dense label="Confirm"
       @click.stop="$parent.$emit('acknowledge_' + c.singular, { row: props.row, idx: c.ack_idx })">
    <q-tooltip>Confirm you can cover this {{ c.singular }} slot</q-tooltip>
</q-btn>
<q-btn v-if="c.can_withdraw" outline no-caps no-wrap color="negative" dense label="Withdraw"
       :aria-label="'Withdraw as ' + c.singular"
       @click.stop="$parent.$emit('undo_' + c.singular, props.row)" />
<q-btn v-else-if="c.can_sign_up" outline no-caps no-wrap color="primary" dense label="Sign up"
       :aria-label="'Sign up as ' + c.singular"
       @click.stop="$parent.$emit('signup_' + c.singular, props.row)" />
</span>'''

_ACK = r'''<q-btn v-if="props.row._ack" unelevated no-caps no-wrap color="primary" dense label="Acknowledge"
       @click.stop="$parent.$emit('acknowledge_match', props.row)">
    <q-tooltip>Confirm you've seen this match and will play it</q-tooltip>
</q-btn>'''

_BELL = r'''<q-btn :icon="props.row._watching ? 'notifications' : 'notifications_none'"
       :color="props.row._watching ? 'primary' : 'grey-8'" flat round dense
       @click.stop="$parent.$emit('toggle_watch', props.row)"
       :aria-label="props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates'">
    <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
</q-btn>'''

_STAGE = r'''<a v-if="props.row._stage && props.row.stage_url" :href="props.row.stage_url" target="_blank" rel="noopener noreferrer"
   class="table-link" @click.stop>{{ props.row._stage }}</a>
<span v-else-if="props.row._stage">{{ props.row._stage }}</span>
<span v-else class="run-sheet__none">None</span>'''

_BODY_SLOT = r'''
<q-tr v-if="props.row._group_start" class="run-sheet__group-row">
    <q-td colspan="100%" class="run-sheet__group">{{ props.row._group }}</q-td>
</q-tr>
<q-tr :props="props" class="run-sheet__row player-sheet__row" :class="props.row._flash ? 'wiz-row-flash' : ''"
      @click="$parent.$emit('open_match', props.row.id)">
    <q-td v-for="col in props.cols" :key="col.name" :props="props">
        <template v-if="col.name === 'scheduled_at'">''' + _WHEN + '''</template>
        <template v-else-if="col.name === 'match'">
            <button type="button" class="run-sheet__open" @click.stop="$parent.$emit('open_match', props.row.id)">
                {{ ''' + _TITLE + ''' }}</button>
            <span class="run-sheet__meta">''' + _YOU + '''{{ props.row.tournament }}<template v-if="props.row.bracket"> · {{ props.row.bracket.name }}<template v-if="props.row.bracket.game"> · Game {{ props.row.bracket.game }}</template></template></span>
        </template>
        <template v-else-if="col.name === 'stage'">''' + _STAGE + '''</template>
        <template v-else-if="col.name === 'crew'">
            <div class="player-sheet__roles">
                <div v-for="c in props.row._roles" :key="c.key" class="player-sheet__role">''' + _ROLE + '''</div>
            </div>
        </template>
        <template v-else-if="col.name === 'status'">
            <div class="player-sheet__status">
                <span class="wiz-chip" :class="'wiz-chip--' + props.row._tone">{{ props.row._status }}</span>''' + _ACK + '''
            </div>
        </template>
        <template v-else-if="col.name === 'watch'">''' + _BELL + '''</template>
        <template v-else>{{ col.value }}</template>
    </q-td>
</q-tr>
'''

# Phone: the names are the button that opens the sheet; the bell and the crew
# buttons sit beside it rather than inside it (a button can't hold buttons).
_ITEM_SLOT = r'''
<div class="run-sheet__item">
    <div v-if="props.row._group_start" class="run-sheet__group">{{ props.row._group }}</div>
    <div class="player-sheet__card" :class="props.row._flash ? 'wiz-row-flash' : ''">
        <div class="player-sheet__top">
            <button type="button" class="player-sheet__open" @click="$parent.$emit('open_match', props.row.id)">
                <span class="run-sheet__when">''' + _WHEN + '''</span>
                <span class="run-sheet__main">
                    <span class="run-sheet__who">{{ ''' + _TITLE + ''' }}</span>
                    <span class="run-sheet__meta">''' + _YOU + '''{{ props.row.tournament }}<template v-if="props.row._stage"> · {{ props.row._stage }}</template></span>
                </span>
                <span v-if="props.row._status !== 'Scheduled'" class="wiz-chip" :class="'wiz-chip--' + props.row._tone">{{ props.row._status }}</span>
            </button>''' + _BELL + '''
        </div>
        <div v-if="props.row._ack || props.row._roles.length" class="player-sheet__acts">''' + _ACK + '''
            <div v-for="c in props.row._roles" :key="c.key" class="player-sheet__role">''' + _ROLE + '''</div>
        </div>
    </div>
</div>
'''


def register_player_run_sheet_slots(table) -> None:
    """The player run sheet's desktop ``body`` and phone ``item`` slots."""
    table.add_slot('body', _BODY_SLOT)
    table.add_slot('item', _ITEM_SLOT)
