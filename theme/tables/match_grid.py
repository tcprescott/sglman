"""Grid (mobile) slot builder for the match table.

Below Quasar's ``lt.md`` breakpoint ``ui.table`` renders the ``item`` slot per
row instead of columns. This module builds a single purpose-built match card for
that mode, driven by the same server-injected admin/can_crud booleans and the
current user's discord id the column slots use (``match_slots.py``).

The card is deliberately bespoke (not a generic ``label: value`` loop): a
headline row (scheduled time + compact state chip), a players line (ack icons,
``(auto)`` markers, winner emphasis, admin stations, self-ack), a muted caption
(tournament + ``#id`` edit link), ``v-if``-gated detail rows that render nothing
when empty (commentators, trackers, stage, seed, comment), and a single
top-bordered actions row (lifecycle button, Assign Stations, watch toggle).

Styling lives entirely in ``.match-grid-card`` / ``.mgc-*`` (``styles.css``) so
light/dark parity is automatic — no inline colors here. The template is
assembled from plain (non-f) string fragments; the four server booleans are
substituted via ``__IA__`` / ``__CC__`` / ``__DID__`` / ``__WATCH__`` placeholders
(the same technique ``match_slots.py`` uses), which keeps every literal Vue
``{{ }}`` unescaped and the braces valid.

Frozen event contract (payload shapes the handlers in ``match_handlers.py``
depend on — do not change):
    edit_match                     -> { row: props.row }
    acknowledge_match              -> props.row
    signup_/undo_commentator|tracker -> props.row
    acknowledge_/edit_commentator|tracker -> { row: props.row, idx }
    seat/start/finish/confirm      -> { key: props.row.id }
    roll                           -> { key: props.row.id }   (+ _generating_seed)
    edit-stream-room               -> { key: props.row.id }
    assign_stations                -> { row: props.row }
    toggle_watch                   -> props.row
"""

# --- Headline: scheduled time (large) + compact state chip -----------------

_STATE_CHIP = '''
        <span class="mgc-state">
            <span v-if="props.row.state === 'Confirmed'" class="sgl-chip sgl-chip--ok">
                <q-icon name="verified" size="14px" />Confirmed</span>
            <span v-else-if="props.row.state === 'Finished'" class="sgl-chip sgl-chip--pending">
                <q-icon name="flag" size="14px" />Finished</span>
            <span v-else-if="props.row.state === 'Started'" class="sgl-chip sgl-chip--live">
                <q-icon name="play_arrow" size="14px" />Started</span>
            <span v-else-if="props.row.state === 'Checked In'" class="sgl-chip sgl-chip--neutral">
                <q-icon name="check" size="14px" />Checked In</span>
            <span v-else class="sgl-chip sgl-chip--neutral">
                <q-icon name="schedule" size="14px" />{{ props.row.state || 'Scheduled' }}</span>
            <span v-if="props.row.state_time" class="cell-timestamp">{{ props.row.state_time }}</span>
        </span>'''


# --- Players line ----------------------------------------------------------

_PLAYERS = '''
        <div class="mgc-players">
            <template v-for="(player, idx) in props.row.players">
                <div class="mgc-player">
                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                            name="check_circle" class="st-ok" size="xs">
                        <q-tooltip v-if="props.row.acknowledgments[idx].ts">Acknowledged {{ props.row.acknowledgments[idx].ts }}</q-tooltip>
                    </q-icon>
                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                            name="schedule" class="st-pending" size="xs">
                        <q-tooltip>Awaiting acknowledgment</q-tooltip>
                    </q-icon>
                    <span :class="player.finish_rank === 1 ? 'st-ok-strong' : ''">
                        {{ player.name }}<span v-if="__IA__ && player.station" class="st-neutral italic-note"> ({{ player.station }})</span>
                    </span>
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


# --- Detail rows (each v-if-gated: empty -> renders nothing) ----------------

# Commentators / trackers. Row shows when the list is non-empty, or (non-admin
# only) when a signup is still possible — so an empty admin crew line collapses
# but a volunteer can still sign up. Emits props.row for signup/undo and
# { row, idx } for edit/acknowledge.
_CREW_DETAIL = '''
        <div class="mgc-detail" v-if="(props.row.__KEY__ && props.row.__KEY__.length) || (!__IA__ && props.row.__KEY__ && !props.row.__KEY__.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__))">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">
                <template v-for="(item, idx) in props.row.__KEY__">
                    <span class="mgc-crew-item">
                        <q-icon v-if="item.approved && item.acknowledged" name="check_circle" class="st-ok" size="xs">
                            <q-tooltip v-if="item.ack_ts">Acknowledged {{ item.ack_ts }}</q-tooltip>
                        </q-icon>
                        <q-icon v-else-if="item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                            <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                        </q-icon>
                        <a v-if="__IA__ && __CC__" href="#" @click="$parent.$emit('edit___SING__', { row: props.row, idx })"
                           :class="item.approved ? 'st-ok-strong' : 'st-pending'" style="text-decoration: underline;">{{ item.name }}{{ idx < props.row.__KEY__.length - 1 ? ', ' : '' }}</a>
                        <span v-else :class="item.approved ? 'st-ok-strong' : 'st-pending'">{{ item.name }}{{ idx < props.row.__KEY__.length - 1 ? ', ' : '' }}</span>
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
                    <q-btn v-if="props.row.__KEY__ && !props.row.__KEY__.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__)"
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
                <a v-if="props.row.stream_room && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{ props.row.stream_room }}</a>
                <span v-else-if="props.row.stream_room">{{ props.row.stream_room }}</span>
                <span v-if="props.row.is_stream_candidate && !props.row.stream_room" class="sgl-chip sgl-chip--candidate q-ml-xs">candidate</span>
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
_SEED_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.generated_seed || (__IA__ && props.row.tournament_seed_generator)">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">
                <q-btn v-if="__IA__ && props.row.tournament_seed_generator && !props.row.generated_seed"
                       :loading="props.row._generating_seed" :disabled="props.row._generating_seed"
                       icon="casino" color="primary" size="sm" dense outline
                       @click="(props.row._generating_seed = true, $parent.$emit('roll', { key: props.row.id }))">
                    Generate
                </q-btn>
                <template v-if="props.row.generated_seed">
                    <a v-if="props.row.generated_seed.startsWith('https://') || props.row.generated_seed.startsWith('http://')"
                       :href="props.row.generated_seed" target="_blank" style="color: var(--sgl-link); text-decoration: underline;">{{ props.row.generated_seed.length > 40 ? props.row.generated_seed.substring(0, 40) + '...' : props.row.generated_seed }}</a>
                    <span v-else>{{ props.row.generated_seed.length > 40 ? props.row.generated_seed.substring(0, 40) + '...' : props.row.generated_seed }}</span>
                </template>
            </span>
        </div>'''

# Free-text comment. Only present when the row actually carries one.
_COMMENT_DETAIL = '''
        <div class="mgc-detail" v-if="props.row.comment">
            <span class="mgc-label">__LABEL__</span>
            <span class="mgc-detail-value">{{ props.row.comment }}</span>
        </div>'''


# --- Actions row: lifecycle button + Assign Stations + watch toggle --------

_ACTIONS = '''
        <div class="mgc-actions row items-center" v-if="(__IA__ && ['Scheduled', 'Checked In', 'Started', 'Finished'].includes(props.row.state)) || (__IA__ && __CC__) || __WATCH__">
            <q-btn v-if="__IA__ && props.row.state === 'Scheduled'" icon="chair" color="primary" size="md"
                   @click="$parent.$emit('seat', { key: props.row.id })">Check In</q-btn>
            <q-btn v-else-if="__IA__ && props.row.state === 'Checked In'" icon="play_arrow" color="primary" size="md"
                   @click="$parent.$emit('start', { key: props.row.id })">Start</q-btn>
            <q-btn v-else-if="__IA__ && props.row.state === 'Started'" icon="sports_score" color="primary" size="md"
                   @click="$parent.$emit('finish', { key: props.row.id })">Finish</q-btn>
            <q-btn v-else-if="__IA__ && props.row.state === 'Finished'" icon="check_circle" color="primary" size="md"
                   @click="$parent.$emit('confirm', { key: props.row.id })">Confirm</q-btn>
            <q-btn v-if="__IA__ && __CC__" icon="switch_access_shortcut" color="primary" size="md" outline
                   @click="$parent.$emit('assign_stations', { row: props.row })">Assign Stations</q-btn>
            <q-space />
            <q-btn v-if="__WATCH__" :icon="props.row._watching ? 'visibility' : 'visibility_off'"
                   :color="props.row._watching ? 'primary' : 'grey'" size="md" flat round
                   @click="$parent.$emit('toggle_watch', props.row)">
                <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
            </q-btn>
        </div>'''


_CARD_OPEN = '''<div class="match-grid-card q-pa-md q-mb-sm" :class="props.row._flash ? 'sgl-row-flash' : ''" style="width: 100%; box-sizing: border-box;">'''
_CARD_CLOSE = '''
    </div>'''


def render_grid_slot(table, columns, *, admin_controls: bool, can_crud: bool, discord_id,
                     has_edit: bool = True) -> None:
    """Register the purpose-built grid ``item`` slot on ``table``.

    Only fields that appear as (non-hidden) columns are rendered, preserving
    parity with the desktop table on each page. The four server-side flags are
    baked into the template so client-side branches collapse to constants.
    ``has_edit`` mirrors the caller's edit callback: without one the caption id
    renders as plain text instead of a dead link.
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
        '<span class="mgc-time">{{ props.row.scheduled_at }}</span>'
        + (_STATE_CHIP if 'state' in present else '')
        + '\n        </div>'
    )

    # Players line
    players = _PLAYERS if 'players' in present else ''

    # Caption (tournament + #id edit link)
    caption_inner = ''
    if 'tournament' in present:
        caption_inner += '<span v-if="props.row.tournament">{{ props.row.tournament }}</span>'
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

    # Actions (only worth emitting when an admin or the watch toggle is in play)
    actions = _ACTIONS if (admin_controls or 'watch' in present) else ''

    template = _CARD_OPEN + headline + players + caption + details + actions + _CARD_CLOSE

    template = (
        template
        .replace('__IA__', ia)
        .replace('__CC__', cc)
        .replace('__WATCH__', watch_js)
        .replace('__DID__', did)
    )

    table.add_slot('item', template)
