"""Grid (mobile) slot builder for the match table.

Below Quasar's ``lt.md`` breakpoint ``ui.table`` renders the ``item`` slot per
row instead of columns. This module builds a single purpose-built match card for
that mode, driven by the same server-injected admin/can_crud booleans and the
current user's discord id the column slots use (``match_slots.py``).

The card is deliberately bespoke (not a generic ``label: value`` loop): a
headline row (scheduled time + compact state chip), a players line (ack icons,
``(auto)`` markers, winner emphasis, admin stations, self-ack), the dispute flag
with the proctor's note as text, a muted caption (tournament + ``#id`` edit
link), ``v-if``-gated detail rows that render nothing when empty (commentators,
trackers, stage, seed, comment), and a single top-bordered actions row
(lifecycle button, Assign Stations, watch toggle).

Two orders exist. By default the actions row is last, below every detail —
right for a board that is read more than it is acted on. With
``actions_first=True`` (the proctor board) it sits directly under the player
names so the next action is reachable without scrolling past the metadata, and
carries ``mgc-actions--first`` to move its divider from top to bottom.

Styling lives entirely in ``.match-grid-card`` / ``.mgc-*`` (``styles.css``) so
light/dark parity is automatic — no inline colors here. The template is
assembled from plain (non-f) string fragments; the server-side values are
substituted via ``__IA__`` / ``__CC__`` / ``__DID__`` / ``__WATCH__`` /
``__ACTCLS__`` placeholders (the same technique ``match_slots.py`` uses), which
keeps every literal Vue ``{{ }}`` unescaped and the braces valid.

Frozen event contract (payload shapes the handlers in ``match_handlers.py``
depend on — do not change):
    edit_match                     -> { row: props.row }
    acknowledge_match              -> props.row
    signup_/undo_commentator|tracker -> props.row
    acknowledge_/view_/toggle_commentator|tracker -> { row: props.row, idx }
    seat/start/finish/confirm      -> { key: props.row.id }
    edit_result                    -> { key: props.row.id }
    roll                           -> { key: props.row.id }   (+ _generating_seed)
    edit-stream-room               -> { key: props.row.id }
    assign_stations                -> { row: props.row }
    toggle_watch                   -> props.row
"""

from theme.tables.match_slots import SEED_ROLLABLE, crew_wanted_js

# --- Headline: scheduled time (large) + compact state chip -----------------

_STATE_CHIP = '''
        <span class="mgc-state">
            <span v-if="props.row.state === 'Confirmed'" class="wiz-chip wiz-chip--ok">
                <q-icon name="verified" size="14px" />Confirmed</span>
            <span v-else-if="props.row.state === 'Finished'" class="wiz-chip wiz-chip--pending">
                <q-icon name="flag" size="14px" />Finished</span>
            <span v-else-if="props.row.state === 'Started'" class="wiz-chip wiz-chip--live">
                <q-icon name="play_arrow" size="14px" />Started</span>
            <span v-else-if="props.row.state === 'Checked In'" class="wiz-chip wiz-chip--neutral">
                <q-icon name="check" size="14px" />Checked In</span>
            <span v-else class="wiz-chip wiz-chip--neutral">
                <q-icon name="schedule" size="14px" />{{ props.row.state || 'Scheduled' }}</span>
            <span v-if="props.row.state_time" class="cell-timestamp">{{ props.row.state_time }}</span>
        </span>'''


# --- Players line ----------------------------------------------------------

_PLAYERS = '''
        <div class="mgc-players">
            <template v-for="(player, idx) in props.row.players">
                <div class="mgc-player">
                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                            name="how_to_reg" class="st-ok" size="xs">
                        <q-tooltip>Confirmed they're playing{{ props.row.acknowledgments[idx].ts ? ' — ' + props.row.acknowledgments[idx].ts : '' }}. Not a check-in.</q-tooltip>
                    </q-icon>
                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                            name="person_outline" class="st-pending" size="xs">
                        <q-tooltip>Hasn't confirmed they're playing</q-tooltip>
                    </q-icon>
                    <span :class="player.finish_rank === 1 ? 'st-ok-strong' : ''">
                        {{ player.name }}<span v-if="__IA__ && player.station" class="wiz-chip wiz-chip--neutral q-ml-xs">
                            <q-icon name="chair" size="12px" />{{ player.station }}</span>
                    </span>
                    <span v-if="player.finish_rank === 1" class="wiz-chip wiz-chip--ok q-ml-xs">
                        <q-icon name="emoji_events" size="12px" />Winner</span>
                    <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].auto"
                          class="st-neutral italic-note"> (auto)</span>
                    <q-btn v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && !props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].discord_id && props.row.acknowledgments[idx].discord_id == __DID__"
                           icon="check" color="primary" size="xs" dense flat
                           @click="$parent.$emit('acknowledge_match', props.row)">
                        <q-tooltip>Acknowledge</q-tooltip>
                    </q-btn>
                </div>
            </template>
        </div>'''


# --- Dispute flag ----------------------------------------------------------

# Mirrors the "Needs review" chip in the desktop State cell — but renders the
# proctor's note as **text**. The desktop hangs it on a q-tooltip, and a tooltip
# is unreachable on a touch screen, which is where most of this board is read.
# Sits directly under the player names: "an admin should look at this" outranks
# every other line on the card.
_REVIEW_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.needs_review">
            <span class="mgc-label">Review</span>
            <span class="mgc-detail-value">
                <span class="wiz-chip wiz-chip--pending">
                    <q-icon name="report_problem" size="14px" />Needs review</span>
                <span v-if="props.row.review_note" class="st-pending" style="flex-basis: 100%;">{{ props.row.review_note }}</span>
            </span>
        </div>'''


# --- Detail rows (each v-if-gated: empty -> renders nothing) ----------------

# Commentators / trackers. Row shows when the list is non-empty, or (non-admin
# only) when a signup is still possible — so an empty admin crew line collapses
# but a volunteer can still sign up. Emits props.row for signup/undo and
# { row, idx } for view/toggle/acknowledge.
_CREW_DETAIL = '''
        <div class="mgc-detail" v-if="(props.row.__KEY__ && props.row.__KEY__.length) || (__WANTED__ && !__IA__ && props.row.__KEY__ && !props.row.__KEY__.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__))">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">
                <template v-for="(item, idx) in props.row.__KEY__">
                    <span class="mgc-crew-item">
                        <q-btn v-if="__IA__ && __CC__" dense flat size="xs" class="wiz-crew-approve"
                               :icon="item.approved ? 'check_circle' : 'radio_button_unchecked'"
                               :color="item.approved ? 'positive' : 'grey-7'"
                               @click="$parent.$emit('toggle___SING__', { row: props.row, idx })">
                            <q-tooltip>{{ item.approved ? 'Approved — tap to un-approve' : 'Not approved — tap to approve' }}</q-tooltip>
                        </q-btn>
                        <q-icon v-else-if="item.approved && item.acknowledged" name="check_circle" class="st-ok" size="xs">
                            <q-tooltip v-if="item.ack_ts">Acknowledged {{ item.ack_ts }}</q-tooltip>
                        </q-icon>
                        <q-icon v-else-if="item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                            <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                        </q-icon>
                        <a v-if="__IA__ && __CC__" href="#" @click="$parent.$emit('view___SING__', { row: props.row, idx })"
                           class="table-link">{{ item.name }}</a>
                        <span v-else :class="item.approved ? 'st-ok-strong' : 'st-pending'">{{ item.name }}{{ idx < props.row.__KEY__.length - 1 ? ', ' : '' }}</span>
                        <q-icon v-if="__IA__ && __CC__ && item.approved && item.acknowledged" name="how_to_reg" class="st-ok" size="xs">
                            <q-tooltip>Acknowledged{{ item.ack_ts ? ' ' + item.ack_ts : '' }}</q-tooltip>
                        </q-icon>
                        <q-icon v-if="__IA__ && __CC__ && item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                            <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                        </q-icon>
                        <span v-if="__IA__ && __CC__ && idx < props.row.__KEY__.length - 1">,</span>
                        <q-btn v-if="!__IA__ && item.approved && !item.acknowledged && item.discord_id == __DID__"
                               icon="check" color="primary" size="xs" dense flat
                               @click="$parent.$emit('acknowledge___SING__', { row: props.row, idx })">
                            <q-tooltip>Acknowledge</q-tooltip>
                        </q-btn>
                    </span>
                </template>
                <template v-if="!__IA__">
                    <q-btn v-if="props.row.__KEY__ && props.row.__KEY__.some(item => item.discord_id == __DID__)"
                           icon="undo" color="negative" size="sm" dense flat round
                           @click="$parent.$emit('undo___SING__', props.row)">
                        <q-tooltip>Remove yourself</q-tooltip>
                    </q-btn>
                    <q-btn v-if="__WANTED__ && props.row.__KEY__ && !props.row.__KEY__.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__)"
                           icon="assignment" color="primary" size="sm" dense outline
                           @click="$parent.$emit('signup___SING__', props.row)">
                        Sign Up
                    </q-btn>
                </template>
            </span>
        </div>'''

# Stage / stream room. Shows when assigned, a candidate, or an admin who can
# assign; otherwise nothing. Emits { key: props.row.id } for the assign action.
_STREAM_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.stream_room || props.row.is_stream_candidate || (__IA__ && __CC__)">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">
                <a v-if="props.row.stream_room && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--wiz-link); text-decoration: underline;">{{ props.row.stream_room }}</a>
                <span v-else-if="props.row.stream_room">{{ props.row.stream_room }}</span>
                <span v-if="props.row.is_stream_candidate && !props.row.stream_room" class="wiz-chip wiz-chip--candidate q-ml-xs">candidate</span>
                <q-btn v-if="__IA__ && __CC__ && !props.row.stream_room"
                       icon="movie" color="primary" size="sm" dense outline class="q-ml-xs"
                       @click="$parent.$emit('edit-stream-room', { key: props.row.id })">
                    Assign Stage
                </q-btn>
            </span>
        </div>'''

# Generated seed. Admin with a configured generator and no seed gets a Generate
# button (emitting { key: props.row.id } and flagging _generating_seed); once a
# seed exists everyone gets a truncated link. Empty for non-admins -> nothing.
# A racetime.gg room owns its own seed, so no Generate button there.
_SEED_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.generated_seed || (__IA__ && __ROLLABLE__)">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">
                <q-btn v-if="__IA__ && __ROLLABLE__ && !props.row.generated_seed"
                       :loading="props.row._generating_seed" :disabled="props.row._generating_seed"
                       icon="casino" color="primary" size="sm" dense outline
                       @click="(props.row._generating_seed = true, $parent.$emit('roll', { key: props.row.id }))">
                    Generate
                </q-btn>
                <template v-if="props.row.generated_seed">
                    <a v-if="props.row.generated_seed.startsWith('https://') || props.row.generated_seed.startsWith('http://')"
                       :href="props.row.generated_seed" target="_blank" style="color: var(--wiz-link); text-decoration: underline;">{{ props.row.generated_seed.length > 40 ? props.row.generated_seed.substring(0, 40) + '...' : props.row.generated_seed }}</a>
                    <span v-else>{{ props.row.generated_seed.length > 40 ? props.row.generated_seed.substring(0, 40) + '...' : props.row.generated_seed }}</span>
                </template>
                <template v-if="props.row.generated_seed && props.row.seed_dm_blocked && props.row.seed_dm_blocked.length">
                    <span class="st-pending" style="flex-basis: 100%;">
                        <q-icon name="notifications_off" size="14px" class="q-mr-xs" />Can't receive a Discord DM: {{ props.row.seed_dm_blocked.join(', ') }} — hand them the seed.
                    </span>
                    <span class="st-neutral italic-note" style="flex-basis: 100%;">
                        Shows who is unreachable, not whether a DM arrived.
                    </span>
                </template>
            </span>
        </div>'''

# Free-text comment. Only present when the row actually carries one.
_COMMENT_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.comment">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">{{ props.row.comment }}</span>
        </div>'''


# --- Actions row: lifecycle button + Change Winner + Assign Stations + watch --
# "Change Winner" mirrors the desktop pencil, but labelled: an icon-only button
# whose meaning lives in a tooltip is unreadable on a touch screen.

_ACTIONS = '''
        <div class="__ACTCLS__" v-if="(__IA__ && ['Scheduled', 'Checked In', 'Started', 'Finished'].includes(props.row.state)) || (__IA__ && !props.row.is_racetime && props.row.players && props.row.players.length) || __WATCH__">
            <q-btn v-if="__IA__ && props.row.state === 'Scheduled' && !props.row.is_racetime && props.row.players && props.row.players.length"
                   icon="chair" color="primary" size="md"
                   @click="$parent.$emit('seat', { key: props.row.id })">Check In</q-btn>
            <div v-else-if="__IA__ && props.row.state === 'Scheduled' && !props.row.is_racetime" class="st-neutral italic-note">
                Awaiting players</div>
            <div v-else-if="__IA__ && props.row.state === 'Scheduled' && props.row.is_racetime" class="st-neutral italic-note">
                Managed by racetime.gg</div>
            <q-btn v-else-if="__IA__ && props.row.state === 'Checked In'" icon="play_arrow" color="primary" size="md"
                   @click="$parent.$emit('start', { key: props.row.id })">Start</q-btn>
            <q-btn v-else-if="__IA__ && props.row.state === 'Started'" icon="sports_score" color="primary" size="md"
                   @click="$parent.$emit('finish', { key: props.row.id })">Finish</q-btn>
            <q-btn v-else-if="__IA__ && __CC__ && props.row.state === 'Finished' && props.row.has_result" icon="check_circle" color="primary" size="md"
                   @click="$parent.$emit('confirm', { key: props.row.id })">Confirm</q-btn>
            <!-- Mirrors the desktop State cell: Finished with nobody recorded is
                 not confirmable, so say so instead of offering a refusal. -->
            <span v-else-if="__IA__ && __CC__ && props.row.state === 'Finished'" class="wiz-chip wiz-chip--pending">
                <q-icon name="report_problem" size="14px" />No result recorded</span>
            <span v-else-if="__IA__ && props.row.state === 'Finished'" class="wiz-chip wiz-chip--pending">
                <q-icon name="flag" size="14px" />Awaiting confirmation</span>
            <q-btn v-if="__IA__ && __CC__ && props.row.state === 'Finished'"
                   :icon="props.row.has_result ? 'edit' : 'emoji_events'" color="primary" size="md" outline
                   @click="$parent.$emit('edit_result', { key: props.row.id })">{{ props.row.has_result ? 'Change Winner' : 'Record Winner' }}</q-btn>
            <q-btn v-if="__IA__ && !props.row.is_racetime && props.row.players && props.row.players.length"
                   icon="chair" color="primary" size="md" outline
                   @click="$parent.$emit('assign_stations', { row: props.row })">Assign Stations</q-btn>
            <q-space />
            <q-btn v-if="__WATCH__" :icon="props.row._watching ? 'notifications' : 'notifications_none'"
                   :color="props.row._watching ? 'primary' : 'grey'" size="md" flat round
                   @click="$parent.$emit('toggle_watch', props.row)">
                <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
            </q-btn>
        </div>'''


_CARD_OPEN = '''<div class="match-grid-card q-pa-md q-mb-sm" :class="props.row._flash ? 'wiz-row-flash' : ''" style="width: 100%; box-sizing: border-box;">'''
_CARD_CLOSE = '''
    </div>'''


def render_grid_slot(table, columns, *, admin_controls: bool, can_crud: bool, discord_id,
                     has_edit: bool = True, actions_first: bool = False) -> None:
    """Register the purpose-built grid ``item`` slot on ``table``.

    Only fields that appear as (non-hidden) columns are rendered, preserving
    parity with the desktop table on each page. The four server-side flags are
    baked into the template so client-side branches collapse to constants.
    ``has_edit`` mirrors the caller's edit callback: without one the caption id
    renders as plain text instead of a dead link. ``actions_first`` lifts the
    lifecycle row directly under the player names (the proctor board's order).
    """
    present = {c.get('name', '') for c in columns if not c.get('hidden')}
    labels = {c.get('name', ''): c.get('label', c.get('name', '')) for c in columns}

    ia = 'true' if admin_controls else 'false'
    cc = 'true' if can_crud else 'false'
    did = f"'{discord_id}'" if discord_id else 'null'
    watch_js = 'true' if 'watch' in present else 'false'

    # Headline (scheduled time + optional state chip)
    headline = (
        '\n        <div class="mgc-headline">'
        # Mirrors the desktop scheduled_at cell's overdue emphasis (match_slots).
        '<span class="mgc-time" :class="props.row.is_overdue ? \'st-pending\' : \'\'">{{ props.row.scheduled_at }}'
        '<q-icon v-if="props.row.is_overdue" name="schedule" class="st-pending q-ml-xs" size="xs">'
        '<q-tooltip>Past its scheduled time and not checked in</q-tooltip>'
        '</q-icon></span>'
        + (_STATE_CHIP if 'state' in present else '')
        + '\n        </div>'
    )

    # Players line, then the dispute flag (only when the row carries one).
    players = _PLAYERS if 'players' in present else ''
    review = _REVIEW_DETAIL if 'state' in present else ''

    # Caption (tournament + #id edit link)
    caption_inner = ''
    if 'tournament' in present:
        caption_inner += '<span v-if="props.row.tournament">{{ props.row.tournament }}</span>'
        # Same bracket link as the desktop Tournament cell (see match_slots).
        caption_inner += (
            '<a v-if="props.row.bracket" href="#" class="mgc-bracket-link q-ml-sm"'
            ' @click.prevent="$parent.$emit(\'open_bracket\', props.row)">'
            '<q-icon name="account_tree" size="14px" class="q-mr-xs" />'
            '{{ props.row.bracket.name }}'
            '<template v-if="props.row.bracket.game"> · Game {{ props.row.bracket.game }}</template>'
            '<template v-if="props.row.bracket.standing"> · {{ props.row.bracket.standing }}</template>'
            '</a>'
        )
    if 'id' in present:
        if has_edit:
            caption_inner += (
                '<a href="#" class="mgc-id-link q-ml-sm"'
                ' @click="$parent.$emit(\'edit_match\', { row: props.row })">#{{ props.row.id }}</a>'
            )
        else:
            caption_inner += '<span class="q-ml-sm">#{{ props.row.id }}</span>'
    caption = f'\n        <div class="mgc-caption">{caption_inner}</div>' if caption_inner else ''

    # Detail rows (order: commentators, trackers, stage, seed, comment)
    details = ''
    for role in ('commentators', 'trackers'):
        if role in present:
            details += (
                _CREW_DETAIL
                .replace('__WANTED__', crew_wanted_js(role))
                .replace('__KEY__', role)
                .replace('__SING__', role[:-1])
                .replace('__LABEL__', labels.get(role, role))
            )
    if 'stream_room' in present:
        details += _STREAM_DETAIL.replace('__LABEL__', labels.get('stream_room', 'Stage'))
    if 'generated_seed' in present:
        # Mobile label column is narrow; "Generated Seed" (the desktop column label) doesn't fit.
        details += _SEED_DETAIL.replace('__LABEL__', 'Seed')
    details += _COMMENT_DETAIL.replace('__LABEL__', labels.get('comment', 'Comment'))

    # Actions (only worth emitting when an admin or the watch toggle is in play).
    # Hoisted above the caption/detail rows when the caller asked for it, with a
    # sibling class that flips the row's divider from top to bottom.
    actions = _ACTIONS if (admin_controls or 'watch' in present) else ''
    act_cls = ('mgc-actions mgc-actions--first row items-center' if actions_first
               else 'mgc-actions row items-center')

    template = (
        _CARD_OPEN + headline + players + review + actions + caption + details + _CARD_CLOSE
        if actions_first else
        _CARD_OPEN + headline + players + review + caption + details + actions + _CARD_CLOSE
    )

    template = (
        template
        # Shared with the desktop seed cell so the two boards agree on when a
        # seed can still be rolled (match_slots.SEED_ROLLABLE).
        .replace('__ROLLABLE__', SEED_ROLLABLE)
        .replace('__IA__', ia)
        .replace('__CC__', cc)
        .replace('__WATCH__', watch_js)
        .replace('__DID__', did)
        .replace('__ACTCLS__', act_cls)
    )

    table.add_slot('item', template)
