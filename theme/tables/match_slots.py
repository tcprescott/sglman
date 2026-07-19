"""Parameterized Vue slot templates for the match table.

One template per cell type. The three admin / admin+crud / non-admin variants
that ``theme/tables/match.py`` used to register separately are collapsed here into
a single template per cell, driven by server-injected boolean flags
(``__IA__`` → admin_controls, ``__CC__`` → can_crud) and the current user's
discord id (``__DID__``) — the same server-side boolean-injection the grid slot
(``match_grid.py``) already relies on. ``__SING__`` is the singular crew role
(``commentator`` / ``tracker``).

The presentation layer owns these strings; they contain no business logic and no
data access. ``register_body_slots`` wires them onto a ``ui.table``.
"""


def _bool_js(value: bool) -> str:
    return 'true' if value else 'false'


def _fill(template: str, *, admin_controls: bool, can_crud: bool,
          discord_id_js: str, singular: str = '') -> str:
    return (
        template
        .replace('__IA__', _bool_js(admin_controls))
        .replace('__CC__', _bool_js(can_crud))
        .replace('__DID__', discord_id_js)
        .replace('__SING__', singular)
    )


# --- Static pass-through slots (flash-aware) -------------------------------

ID_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <a href="#" @click="$parent.$emit('edit_match', props)" class="table-link cell-id">{{ props.value }}</a>
</q-td>'''

# Plain id for viewers without an edit callback (e.g. proctors) — a link that
# emits an unhandled event reads as broken.
ID_SLOT_READONLY = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <span class="cell-id">{{ props.value }}</span>
</q-td>'''

TOURNAMENT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    {{ props.value }}
</q-td>'''

SCHEDULED_AT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <span class="cell-time">{{ props.value }}</span>
</q-td>'''

WATCH_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <q-btn :icon="props.row._watching ? 'notifications' : 'notifications_none'"
           :color="props.row._watching ? 'primary' : 'grey'"
           size="sm" flat round
           @click="$parent.$emit('toggle_watch', props.row)">
        <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
    </q-btn>
</q-td>'''

SEED_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <q-btn v-if="props.row.tournament_seed_generator && !props.value"
           :loading="props.row._generating_seed"
           :disabled="props.row._generating_seed"
           @click="(props.row._generating_seed = true, $parent.$emit('roll', props))"
           icon="casino" color="primary" size="sm">
        Generate
    </q-btn>
    <span v-if="props.value">
        <template v-if="/^https?:\\/\\//.test(props.value)">
            <a :href="props.value" target="_blank" style="color: var(--sgl-link); text-decoration: underline;" :title="props.value">
                {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
            </a>
        </template>
        <template v-else>{{ props.value }}</template>
    </span>
</q-td>'''

STATE_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <!-- Scheduled state: show Check In button (on-site only; racetime rooms
         drive the lifecycle, so racetime matches show a note instead) -->
    <div v-if="props.value === 'Scheduled'" style="display: flex; justify-content: center;">
        <q-btn v-if="!props.row.is_racetime" @click="$parent.$emit('seat', props)"
               icon="chair" color="primary" size="sm">
            Check In
        </q-btn>
        <span v-else class="st-neutral italic-note">
            racetime.gg
            <q-tooltip>Managed by the racetime.gg room</q-tooltip>
        </span>
    </div>

    <!-- Checked In: show Start button and timestamp -->
    <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <q-btn @click="$parent.$emit('start', props)"
               icon="play_arrow" color="primary" size="sm">
            Start
        </q-btn>
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="check" class="st-neutral" size="xs" />
            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
        </div>
    </div>

    <!-- Started: show Finish button and timestamp -->
    <div v-else-if="props.value === 'Started'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <q-btn @click="$parent.$emit('finish', props)"
               icon="sports_score" color="primary" size="sm">
            Finish
        </q-btn>
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="play_arrow" class="st-live" size="xs" />
            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
        </div>
    </div>

    <!-- Finished: show Confirm button and timestamp -->
    <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <q-btn @click="$parent.$emit('confirm', props)"
               icon="check_circle" color="primary" size="sm">
            Confirm
        </q-btn>
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="flag" class="st-pending" size="xs" />
            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
        </div>
    </div>

    <!-- Confirmed: show state with icon and timestamp -->
    <div v-else-if="props.value === 'Confirmed'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="verified" class="st-ok" size="sm" />
            <span style="font-weight: 500;">{{ props.value }}</span>
        </div>
        <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
    </div>

    <!-- Fallback -->
    <span v-else>{{ props.value }}</span>
</q-td>'''

STREAM_ROOM_ADMIN_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <q-btn v-if="!props.value && !props.row.is_stream_candidate" @click="$parent.$emit('edit-stream-room', props)"
           icon="movie" color="primary" size="sm">
        Assign
    </q-btn>
    <template v-else>
        <a v-if="props.value && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{ props.value }}</a>
        <span v-else-if="props.value">{{ props.value }}</span>
        <span v-if="props.row.is_stream_candidate && !props.value" class="sgl-chip sgl-chip--candidate q-ml-xs">candidate</span>
        <q-btn v-if="!props.value && props.row.is_stream_candidate" @click="$parent.$emit('edit-stream-room', props)"
               icon="movie" color="primary" size="sm" class="q-ml-xs">
            Assign
        </q-btn>
    </template>
</q-td>'''

STREAM_ROOM_READONLY_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <a v-if="props.value && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{ props.value }}</a>
    <span v-else-if="props.value">{{ props.value }}</span>
    <span v-else>-</span>
</q-td>'''


# Read-only seed cell (no Generate button) — the variant the home schedule /
# player dashboards embed via ``extra_slots``. Identical to ``SEED_SLOT`` minus
# the roll button, so a viewer without a roll callback sees the value only.
SEED_SLOT_READONLY = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <span v-if="props.value">
        <template v-if="/^https?:\\/\\//.test(props.value)">
            <a :href="props.value" target="_blank" style="color: var(--sgl-link); text-decoration: underline;" :title="props.value">
                {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
            </a>
        </template>
        <template v-else>{{ props.value }}</template>
    </span>
</q-td>'''


# Read-only state cell (icons + timestamps, no lifecycle action buttons) — the
# variant the home schedule / player dashboards embed. The only divergence
# between the two page copies is the ``Scheduled`` fallback: the schedule board
# renders an icon + timestamp (``scheduled_detailed=True``); the player board
# renders a plain label (``scheduled_detailed=False``). Everything else matches
# byte-for-byte so pages can drop their inline templates.
_STATE_READONLY_HEAD = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <!-- Confirmed state -->
                <div v-if="props.value === 'Confirmed'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="verified" class="st-ok" size="sm" />
                        <span style="font-weight: 500;">{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Finished state -->
                <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="flag" class="st-pending" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Started state -->
                <div v-else-if="props.value === 'Started'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="play_arrow" class="st-live" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Checked In state -->
                <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="check" class="st-neutral" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
'''

_STATE_READONLY_SCHEDULED_DETAILED = '''                <!-- Scheduled state -->
                <div v-else style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="schedule" class="st-neutral" size="sm" />
                        <span>{{ props.value || 'Scheduled' }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
            </q-td>'''

_STATE_READONLY_SCHEDULED_PLAIN = '''                <!-- Scheduled state -->
                <span v-else>{{ props.value || 'Scheduled' }}</span>
            </q-td>'''


def state_readonly_slot(*, scheduled_detailed: bool = True) -> str:
    """Return the read-only match-state cell template.

    ``scheduled_detailed=True`` renders the ``Scheduled`` fallback with an icon
    and timestamp (home schedule board); ``False`` renders a plain label (player
    dashboard). All other states render identically.
    """
    tail = (_STATE_READONLY_SCHEDULED_DETAILED if scheduled_detailed
            else _STATE_READONLY_SCHEDULED_PLAIN)
    return _STATE_READONLY_HEAD + tail


# --- Parameterized slots (admin / admin+crud / non-admin collapsed) --------

# Players: station shown only for admins; the self-acknowledge button and the
# Assign-Stations button are mutually exclusive across the variants.
PLAYERS_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <div style="display: flex; align-items: center; gap: 8px;">
        <div>
            <template v-for="(player, idx) in props.value">
                <div style="display: flex; align-items: center; gap: 4px;">
                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                            name="check_circle" class="st-ok" size="xs">
                        <q-tooltip v-if="props.row.acknowledgments[idx].ts">Acknowledged {{ props.row.acknowledgments[idx].ts }}</q-tooltip>
                    </q-icon>
                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                            name="schedule" class="st-pending" size="xs">
                        <q-tooltip>Awaiting acknowledgment</q-tooltip>
                    </q-icon>
                    <span :class="player.finish_rank === 1 ? 'st-ok-strong' : ''">
                        {{ player.name }}
                        <span v-if="__IA__ && player.station" class="st-neutral italic-note"> ({{ player.station }})</span>
                    </span>
                    <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].auto"
                          class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                    <q-btn v-if="!__IA__ && props.row.acknowledgments && props.row.acknowledgments[idx] && !props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].discord_id && props.row.acknowledgments[idx].discord_id == __DID__"
                           icon="check" color="primary" size="xs" dense flat
                           @click="$parent.$emit('acknowledge_match', props.row)">
                        <q-tooltip>Acknowledge</q-tooltip>
                    </q-btn>
                </div>
            </template>
        </div>
        <q-btn v-if="__IA__ && __CC__ && !props.row.is_racetime" @click="$parent.$emit('assign_stations', props)"
               icon="switch_access_shortcut" color="primary" size="xs" flat round>
            <q-tooltip>Assign Stations</q-tooltip>
        </q-btn>
    </div>
</q-td>'''

# Crew (commentators/trackers): admins get a clickable approval link (only when
# can_crud), everyone else a plain name; non-admins get signup/undo + self-ack.
CREW_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
    <div class="wrap">
        <div v-if="!__IA__" style="margin-bottom: 6px;">
            <q-btn v-if="props.value && props.value.some(item => item.discord_id == __DID__)"
                   icon="undo" color="negative" size="sm" no-caps dense label="Withdraw"
                   @click="$parent.$emit('undo___SING__', props.row)" style="margin-right: 6px;">
                   <q-tooltip>Withdraw my __SING__ signup</q-tooltip>
            </q-btn>
            <q-btn v-if="props.value && !props.value.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__)"
                   icon="assignment_ind" color="primary" size="sm" no-caps dense label="Sign up"
                   @click="$parent.$emit('signup___SING__', props.row)" style="margin-right: 6px;">
                   <q-tooltip>Sign up as __SING__</q-tooltip>
            </q-btn>
        </div>
        <template v-for="(item, idx) in props.value">
            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                <q-icon v-if="item.approved && item.acknowledged" name="check_circle" class="st-ok" size="xs">
                    <q-tooltip v-if="item.ack_ts">Acknowledged {{ item.ack_ts }}</q-tooltip>
                </q-icon>
                <q-icon v-else-if="item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                </q-icon>
                <a v-if="__IA__ && __CC__" href="#" @click="$parent.$emit('edit___SING__', { row: props.row, idx })"
                   :class="item.approved ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px; text-decoration: underline;">
                    {{ item.name }}
                </a>
                <span v-else :class="item.approved ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px;">
                    {{ item.name }}
                </span>
                <q-btn v-if="!__IA__ && item.approved && !item.acknowledged && item.discord_id == __DID__"
                       icon="check" color="primary" size="xs" dense flat
                       @click="$parent.$emit('acknowledge___SING__', { row: props.row, idx })">
                    <q-tooltip>Acknowledge</q-tooltip>
                </q-btn>
            </div>
        </template>
    </div>
</q-td>'''


def register_body_slots(table, *, admin_controls: bool, can_crud: bool, discord_id,
                        extra_slots=None, has_edit: bool = True,
                        want_seed_slot: bool = False,
                        want_state_slot: bool = False,
                        want_stream_room_admin: bool = False,
                        want_stream_room_readonly: bool = False) -> None:
    """Register every body-cell slot on ``table``.

    ``discord_id`` is the current user's id (or None); the watch slot is only
    added for a logged-in user. The ``want_*`` flags mirror the caller's callback
    availability so the seed/state/stream-room slots register exactly as before;
    ``has_edit`` does the same for the id cell's edit link.
    """
    discord_id_js = f"'{discord_id}'" if discord_id else 'null'

    table.add_slot('body-cell-id', ID_SLOT if has_edit else ID_SLOT_READONLY)
    table.add_slot('body-cell-tournament', TOURNAMENT_SLOT)
    table.add_slot('body-cell-scheduled_at', SCHEDULED_AT_SLOT)

    table.add_slot('body-cell-players', _fill(
        PLAYERS_SLOT, admin_controls=admin_controls, can_crud=can_crud, discord_id_js=discord_id_js,
    ))
    for role in ('commentators', 'trackers'):
        table.add_slot(f'body-cell-{role}', _fill(
            CREW_SLOT, admin_controls=admin_controls, can_crud=can_crud,
            discord_id_js=discord_id_js, singular=role[:-1],
        ))

    if extra_slots:
        for slot_name, slot_template in extra_slots.items():
            table.add_slot(slot_name, slot_template)

    if discord_id:
        table.add_slot('body-cell-watch', WATCH_SLOT)

    if want_seed_slot:
        table.add_slot('body-cell-generated_seed', SEED_SLOT)
    if want_state_slot:
        table.add_slot('body-cell-state', STATE_SLOT)
    if want_stream_room_admin:
        table.add_slot('body-cell-stream_room', STREAM_ROOM_ADMIN_SLOT)
    if want_stream_room_readonly:
        table.add_slot('body-cell-stream_room', STREAM_ROOM_READONLY_SLOT)
