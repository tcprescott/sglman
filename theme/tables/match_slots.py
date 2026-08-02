"""Parameterized Vue slot templates for the match table.

One template per cell type. The three admin / admin+crud / non-admin variants
that ``theme/tables/match.py`` used to register separately are collapsed here into
a single template per cell, driven by server-injected boolean flags
(``__IA__`` → admin_controls, plus one flag per capability in
``MatchBoardAccess``) and the current user's discord id (``__DID__``) — the same
server-side boolean-injection the grid slot (``match_grid.py``) already relies
on. ``__SING__`` is the singular crew role (``commentator`` / ``tracker``).

The capability flags are ``__RUN__`` (Check In / Start / Finish / Stations),
``__CONFIRM__`` (Confirm, Record/Change Winner) and ``__CREW__`` (the crew
approval toggle and name link); the grid adds ``__STREAM__``. They replaced a
single ``__CC__`` that stood in for all of them — see ``match_access.py`` for why
that was wrong. ``__IA__`` is not a capability: it means "this is an operator's
board", and still gates the station chips and the absence of self-signup.

The presentation layer owns these strings; they contain no business logic and no
data access. ``register_body_slots`` wires them onto a ``ui.table``.
"""

from theme.tables.match_access import MatchBoardAccess


def _bool_js(value: bool) -> str:
    return 'true' if value else 'false'


def _fill(template: str, *, admin_controls: bool, access: MatchBoardAccess,
          discord_id_js: str, singular: str = '', role: str = '') -> str:
    return (
        template
        .replace('__IA__', _bool_js(admin_controls))
        .replace('__RUN__', _bool_js(access.run))
        .replace('__CONFIRM__', _bool_js(access.confirm))
        .replace('__CREW__', _bool_js(access.approve_crew))
        .replace('__DID__', discord_id_js)
        .replace('__WANTED__', crew_wanted_js(role))
        .replace('__KEY__', role)
        .replace('__SING__', singular)
    )


def crew_wanted_js(role: str) -> str:
    """Vue test for "this tournament uses ``role``" (plural), for a row's crew cell.

    Only an explicit ``false`` hides the control: a row built without
    ``crew_wanted`` keeps its Sign up button rather than silently losing it.
    """
    if not role:
        return 'true'
    return f"((props.row.crew_wanted || {{}}).{role} !== false)"


# --- Static pass-through slots (flash-aware) -------------------------------

# The board's edit affordance. It used to be the primary key rendered as a link
# — "click the 17 to edit this match" — which is both a database value on screen
# and a control nobody can guess is a control. A labelled pencil in the same
# first-column slot costs the same width and says what it does.
EDIT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <q-btn flat round dense icon="edit" color="primary"
           @click="$parent.$emit('edit_match', props)">
        <q-tooltip>Edit this match</q-tooltip>
    </q-btn>
</q-td>'''

ID_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <a href="#" @click="$parent.$emit('edit_match', props)" class="table-link cell-id">{{ props.value }}</a>
</q-td>'''

# Plain id for viewers without an edit callback (e.g. proctors) — a link that
# emits an unhandled event reads as broken.
ID_SLOT_READONLY = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <span class="cell-id">{{ props.value }}</span>
</q-td>'''

# A bracket-scheduled match links to the stage it settles. The link emits rather
# than carrying an href: `ui.navigate.to` prepends the tenant's root_path, which
# a hand-built href in a slot template would miss under path-mode multitenancy.
TOURNAMENT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <div class="cell-tournament">{{ props.value }}</div>
    <a v-if="props.row.bracket" href="#" class="table-link cell-bracket-link"
       @click.prevent="$parent.$emit('open_bracket', props.row)">
        <q-icon name="account_tree" size="14px" class="q-mr-xs" />
        <span>{{ props.row.bracket.name }}<template v-if="props.row.bracket.game"> · Game {{ props.row.bracket.game }}<template v-if="props.row.bracket.best_of > 1"> of {{ props.row.bracket.best_of }}</template></template><template v-if="props.row.bracket.standing"> · {{ props.row.bracket.standing }}</template></span>
        <q-tooltip>View this match's bracket</q-tooltip>
    </a>
</q-td>'''

# ``is_overdue`` (set by MatchDisplayService) means the scheduled time has passed
# and nobody has checked the match in — the proctor board leans on it, every
# other board simply never sees a truthy value.
SCHEDULED_AT_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <span class="cell-time" :class="props.row.is_overdue ? 'st-pending' : ''">{{ props.value }}</span>
    <q-icon v-if="props.row.is_overdue" name="schedule" class="st-pending q-ml-xs" size="xs">
        <q-tooltip>Past its scheduled time and not checked in</q-tooltip>
    </q-icon>
</q-td>'''

WATCH_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <q-btn :icon="props.row._watching ? 'notifications' : 'notifications_none'"
           :color="props.row._watching ? 'primary' : 'grey'"
           size="sm" flat round
           @click="$parent.$emit('toggle_watch', props.row)">
        <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
    </q-btn>
</q-td>'''

# The player's own "we'd be happy to be streamed" toggle. Every copy on it says
# the offer is advisory, because a control beside a Stage column reads as
# booking one otherwise. Rendered only for a player *in* the match — the service
# refuses anyone else, so offering the button elsewhere teaches a refusal.
STREAM_VOLUNTEER_TOOLTIP = (
    "Offer this match for stream. Staff see it when they plan coverage — "
    "it doesn't book a stage."
)

# The *same* asymmetry ``MatchStreamVolunteerService`` enforces, not a second
# spelling of it: offering is refused once the match is under way (nothing left
# for staff to schedule), while withdrawing stays open, so a player who changes
# their mind is never stuck with a request they cannot unsay.
STREAM_VOLUNTEER_ACTIONABLE = (
    "props.row._stream_volunteer"
    " || ['Scheduled', 'Checked In'].includes(props.row.state)"
)

STREAM_VOLUNTEER_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <q-btn v-if="__ACTIONABLE__ && props.row.players && props.row.players.some(p => p.discord_id == __DID__)"
           :icon="props.row._stream_volunteer ? 'videocam' : 'videocam_off'"
           :color="props.row._stream_volunteer ? 'primary' : 'grey'"
           size="sm" flat round
           @click="$parent.$emit('toggle_stream_volunteer', props.row)">
        <q-tooltip>{{ props.row._stream_volunteer ? 'Withdraw your stream offer' : "__OFFER__" }}</q-tooltip>
    </q-btn>
    <span v-else-if="props.row.stream_volunteers && props.row.stream_volunteers.length"
          class="wiz-chip wiz-chip--candidate">
        <q-icon name="videocam" size="12px" />{{ props.row.stream_volunteers.length }}
        <q-tooltip>Volunteered for stream: {{ props.row.stream_volunteers.join(', ') }}. Advisory only.</q-tooltip>
    </span>
</q-td>'''.replace('__OFFER__', STREAM_VOLUNTEER_TOOLTIP).replace(
    '__ACTIONABLE__', STREAM_VOLUNTEER_ACTIONABLE,
)

# The Generate button's own gate, shared with the mobile grid's seed detail.
# A seed can only be rolled once, so offering the button where it cannot help is
# not merely noise: on a bracket row with no players yet it burns the one roll on
# a match whose players don't exist, and the DM reaches nobody. Past the finish
# there is nothing left to seed.
SEED_ROLLABLE = ("props.row.tournament_seed_generator && !props.row.is_racetime"
                 " && props.row.players && props.row.players.length"
                 " && !['Finished', 'Confirmed'].includes(props.row.state)")

SEED_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <q-btn v-if="__ROLLABLE__ && !props.value"
           :loading="props.row._generating_seed"
           :disabled="props.row._generating_seed"
           @click="(props.row._generating_seed = true, $parent.$emit('roll', props))"
           icon="casino" color="primary" size="sm">
        Generate
    </q-btn>
    <span v-if="props.value">
        <template v-if="/^https?:\\/\\//.test(props.value)">
            <a :href="props.value" target="_blank" style="color: var(--wiz-link); text-decoration: underline;" :title="props.value">
                {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
            </a>
        </template>
        <template v-else>{{ props.value }}</template>
        <q-icon v-if="props.row.seed_dm_blocked && props.row.seed_dm_blocked.length"
                name="notifications_off" class="st-pending q-ml-xs" size="xs">
            <q-tooltip>Can't receive a Discord DM: {{ props.row.seed_dm_blocked.join(', ') }} — hand them the seed. Shows who is unreachable, not whether a DM arrived.</q-tooltip>
        </q-icon>
    </span>
</q-td>'''.replace('__ROLLABLE__', SEED_ROLLABLE)

# Carries the capability flags — must be registered through ``_fill``, not raw.
STATE_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <!-- Scheduled state: show Check In button (on-site only, and only once the
         match has players; racetime rooms drive the lifecycle, so racetime
         matches show a note instead). A viewer who cannot run the match reads
         the state rather than being offered a button the service refuses. -->
    <div v-if="props.value === 'Scheduled'" style="display: flex; justify-content: center;">
        <q-btn v-if="__RUN__ && !props.row.is_racetime && props.row.players && props.row.players.length"
               @click="$parent.$emit('seat', props)"
               icon="chair" color="primary" size="sm">
            Check In
        </q-btn>
        <span v-else-if="__RUN__ && !props.row.is_racetime" class="st-neutral italic-note">
            awaiting players
            <q-tooltip>This match has no players yet</q-tooltip>
        </span>
        <span v-else-if="__RUN__" class="st-neutral italic-note">
            racetime.gg
            <q-tooltip>Managed by the racetime.gg room</q-tooltip>
        </span>
        <span v-else>{{ props.value }}</span>
    </div>

    <!-- Checked In: show Start button and timestamp -->
    <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <q-btn v-if="__RUN__" @click="$parent.$emit('start', props)"
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
        <q-btn v-if="__RUN__" @click="$parent.$emit('finish', props)"
               icon="sports_score" color="primary" size="sm">
            Finish
        </q-btn>
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="play_arrow" class="st-live" size="xs" />
            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
        </div>
    </div>

    <!-- Finished: Confirm (+ correct the winner) for whoever can_confirm_match
         admits; everyone else sees it is awaiting review. Correcting a result is
         the admin's call, so the pencil is confirm-gated — a proctor records,
         they do not amend. The dispute chip sits above both, since "an admin
         should look at this" is the first thing to read about a recorded
         result. -->
    <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <span v-if="props.row.needs_review" class="wiz-chip wiz-chip--pending">
            <q-icon name="report_problem" size="14px" />Needs review
            <q-tooltip>The proctor flagged this result. Confirming clears the flag.</q-tooltip>
        </span>
        <div v-if="__CONFIRM__" style="display: flex; align-items: center; gap: 4px;">
            <!-- No winner on the board: confirming is refused by the service, so
                 say what is missing and lead with the pencil, which is the
                 control that fixes it. Offering Confirm here only teaches the
                 admin to click it and read an error. -->
            <span v-if="!props.row.has_result" class="wiz-chip wiz-chip--pending">
                <q-icon name="report_problem" size="14px" />No result
                <q-tooltip>Nobody is recorded as the winner. Record one before confirming.</q-tooltip>
            </span>
            <q-btn v-else @click="$parent.$emit('confirm', props)"
                   icon="check_circle" color="primary" size="sm">
                Confirm
            </q-btn>
            <!-- Carries __CONFIRM__ itself, not just via the wrapping div:
                 correcting a result is the admin's call, and that gate belongs
                 on the control so it cannot be lost by re-nesting the markup. -->
            <q-btn v-if="__CONFIRM__" @click="$parent.$emit('edit_result', props)"
                   :icon="props.row.has_result ? 'edit' : 'emoji_events'"
                   :flat="props.row.has_result" :round="props.row.has_result"
                   :outline="!props.row.has_result" :no-caps="!props.row.has_result"
                   size="sm" dense color="primary">
                <template v-if="!props.row.has_result">Record Winner</template>
                <q-tooltip v-else>Change the recorded winner</q-tooltip>
            </q-btn>
        </div>
        <span v-else class="wiz-chip wiz-chip--pending">
            <q-icon name="flag" size="14px" />Awaiting confirmation
            <q-tooltip>Recorded. An admin confirms the result.</q-tooltip>
        </span>
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

# The value the Stage select carries for "streamed, stage not decided yet".
# ``Candidate`` is not a Stage — it is the ``is_stream_candidate`` flag
# wearing a stage's clothes, so that the one question the cell asks ("where is
# this being streamed?") has one control instead of a button, a dialog and a
# checkbox. ``on_set_stage`` maps it back to the flag.
CANDIDATE_STAGE = 'candidate'

# Vue expression for the select's current value: the assigned stage wins, the
# candidate flag stands in when there is none. A staged match stops reading as a
# candidate — the stage is the more specific answer — while the flag itself
# survives underneath, because the coverage reports still count it.
STAGE_VALUE_JS = (
    f"props.row.stage_id || (props.row.is_stream_candidate ? '{CANDIDATE_STAGE}' : null)"
)

# Reads as plain text and becomes a dropdown on click: a bordered select in
# every row of a wide board is nine boxes of chrome around one word each, and the
# board is read far more often than it is edited. The affordance returns on hover
# and focus (see ``.wiz-stage-select`` in styles.css), so the control is still
# discoverable and still keyboard-reachable. ``No Stage`` is an explicit option
# rather than a clear button — "none" is one of the answers, not the absence of
# one, and a clear affordance that only appears once something is chosen cannot
# be found by someone looking for it.
STAGE_ADMIN_SLOT = f'''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <div style="display: flex; align-items: center; gap: 4px;">
        <q-select :model-value="{STAGE_VALUE_JS}" :options="props.row.stage_options || []"
                  @update:model-value="val => $parent.$emit('set_stage', {{ key: props.row.id, stage: val }})"
                  dense options-dense borderless emit-value map-options
                  class="wiz-stage-select" style="min-width: 110px;" />
        <a v-if="props.value && props.row.stage_url" :href="props.row.stage_url"
           target="_blank" rel="noopener noreferrer" style="color: var(--wiz-link);">
            <q-icon name="open_in_new" size="18px" />
            <q-tooltip>Open the stream</q-tooltip>
        </a>
    </div>
</q-td>'''

STAGE_READONLY_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <a v-if="props.value && props.row.stage_url" :href="props.row.stage_url" target="_blank" rel="noopener noreferrer" style="color: var(--wiz-link); text-decoration: underline;">{{ props.value }}</a>
    <span v-else-if="props.value">{{ props.value }}</span>
    <span v-else>-</span>
</q-td>'''


# Read-only seed cell (no Generate button) — the variant the home schedule /
# player dashboards embed via ``extra_slots``. Identical to ``SEED_SLOT`` minus
# the roll button, so a viewer without a roll callback sees the value only.
SEED_SLOT_READONLY = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <span v-if="props.value">
        <template v-if="/^https?:\\/\\//.test(props.value)">
            <a :href="props.value" target="_blank" style="color: var(--wiz-link); text-decoration: underline;" :title="props.value">
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
_STATE_READONLY_HEAD = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
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

# Players: the self-acknowledge button and the Assign-Stations button are
# mutually exclusive across the variants. The station chip is *not* admin-gated —
# a player could not see the seat they had been assigned to, which is the one
# fact about check-in they need and the only place the app holds it. It is a
# venue seat number, not private data, so it renders for every viewer of the
# board; setting it stays behind `__RUN__`.
PLAYERS_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <div style="display: flex; align-items: center; gap: 8px;">
        <div>
            <template v-for="(player, idx) in props.value">
                <div style="display: flex; align-items: center; gap: 4px;">
                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                            name="how_to_reg" class="st-ok" size="xs">
                        <q-tooltip>Confirmed they're playing{{ props.row.acknowledgments[idx].ts ? ' — ' + props.row.acknowledgments[idx].ts : '' }}. Not a check-in.</q-tooltip>
                    </q-icon>
                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                            name="person_outline" class="st-pending" size="xs">
                        <q-tooltip>Hasn't confirmed they're playing</q-tooltip>
                    </q-icon>
                    <span :class="player.finish_rank === 1 ? 'st-ok-strong' : ''">
                        {{ player.name }}
                        <span v-if="player.station" class="wiz-chip wiz-chip--neutral q-ml-xs">
                            <q-icon name="chair" size="12px" />{{ player.station }}</span>
                    </span>
                    <span v-if="player.finish_rank === 1" class="wiz-chip wiz-chip--ok q-ml-xs">
                        <q-icon name="emoji_events" size="12px" />Winner</span>
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
        <!-- Labelled, not icon-only: the proctor reads this board on a tablet,
             where a tooltip never opens, and `switch_access_shortcut` at size xs
             read as an unidentifiable squiggle. `chair` is the same icon the
             station chips above use, so the button and what it sets match. -->
        <q-btn v-if="__RUN__ && !props.row.is_racetime && props.row.players && props.row.players.length"
               @click="$parent.$emit('assign_stations', props)"
               icon="chair" color="primary" size="sm" dense flat no-caps>
            Stations
            <q-tooltip>Set which station each player is sitting at</q-tooltip>
        </q-btn>
    </div>
</q-td>'''

# Crew (commentators/trackers): admins who can crud get an approval toggle plus a
# name that opens the user (the same split players already have — a name reads as
# a name, not as a control that mutates approval); everyone else a plain name.
# Non-admins get signup/undo + self-ack.
CREW_SLOT = '''<q-td :props="props" :class="props.row._flash ? 'wiz-row-flash' : ''">
    <div class="wrap">
        <div v-if="!__IA__" style="margin-bottom: 6px;">
            <q-btn v-if="props.value && props.value.some(item => item.discord_id == __DID__)"
                   icon="undo" color="negative" size="sm" no-caps dense label="Withdraw"
                   @click="$parent.$emit('undo___SING__', props.row)" style="margin-right: 6px;">
                   <q-tooltip>Withdraw my __SING__ signup</q-tooltip>
            </q-btn>
            <q-btn v-if="__WANTED__ && props.row.crew_signup_open && props.value && !props.value.some(item => item.discord_id == __DID__) && !props.row.players.some(p => p.discord_id == __DID__)"
                   icon="assignment_ind" color="primary" size="sm" no-caps dense label="Sign up"
                   @click="$parent.$emit('signup___SING__', props.row)" style="margin-right: 6px;">
                   <q-tooltip>Sign up as __SING__</q-tooltip>
            </q-btn>
        </div>
        <template v-for="(item, idx) in props.value">
            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                <q-btn v-if="__CREW__" dense flat size="xs" class="wiz-crew-approve"
                       :icon="item.approved ? 'check_circle' : 'radio_button_unchecked'"
                       :color="item.approved ? 'positive' : 'grey-7'"
                       @click="$parent.$emit('toggle___SING__', { row: props.row, idx })">
                    <q-tooltip>{{ item.approved ? 'Approved — click to un-approve' : 'Not approved — click to approve' }}</q-tooltip>
                </q-btn>
                <q-icon v-else-if="item.approved && item.acknowledged" name="check_circle" class="st-ok" size="xs">
                    <q-tooltip v-if="item.ack_ts">Acknowledged {{ item.ack_ts }}</q-tooltip>
                </q-icon>
                <q-icon v-else-if="item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                </q-icon>
                <a v-if="__CREW__" href="#" @click="$parent.$emit('view___SING__', { row: props.row, idx })"
                   class="table-link" style="margin-right: 4px;">
                    {{ item.name }}
                </a>
                <span v-else :class="item.approved ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px;">
                    {{ item.name }}
                </span>
                <q-icon v-if="__CREW__ && item.approved && item.acknowledged" name="how_to_reg" class="st-ok" size="xs">
                    <q-tooltip>Acknowledged{{ item.ack_ts ? ' ' + item.ack_ts : '' }}</q-tooltip>
                </q-icon>
                <q-icon v-if="__CREW__ && item.approved && !item.acknowledged" name="schedule" class="st-pending" size="xs">
                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                </q-icon>
                <!-- Labelled, not icon-only: a bare `check` beside a name reads as
                     a status mark rather than a control, and the tooltip that was
                     its only explanation never opens on the tablets this board is
                     read on (the same lesson the Stations button records above). -->
                <q-btn v-if="!__IA__ && item.approved && !item.acknowledged && item.discord_id == __DID__"
                       icon="check" color="primary" size="sm" dense flat no-caps label="Acknowledge"
                       @click="$parent.$emit('acknowledge___SING__', { row: props.row, idx })">
                    <q-tooltip>Confirm you can cover this __SING__ slot</q-tooltip>
                </q-btn>
            </div>
        </template>
    </div>
</q-td>'''


def register_body_slots(table, *, admin_controls: bool, access: MatchBoardAccess, discord_id,
                        extra_slots=None, has_edit: bool = True,
                        want_seed_slot: bool = False,
                        want_seed_readonly: bool = False,
                        want_state_slot: bool = False,
                        want_stage_admin: bool = False,
                        want_stage_readonly: bool = False) -> None:
    """Register every body-cell slot on ``table``.

    ``discord_id`` is the current user's id (or None); the watch and
    stream-volunteer slots are only added for a logged-in user, since both act
    on behalf of that person. ``access`` supplies the capability flags the
    templates branch on. The ``want_*`` flags mirror the caller's callback
    availability so the seed/state/stage slots register as the board needs
    them; ``has_edit`` does the same for the id cell's edit link.

    Two different first cells, because two boards want different things. A board
    that can edit declares an ``edit`` column and gets the pencil; the proctor's
    board declares ``id`` and gets the number read-only, because a proctor calls
    a match out by its number across a stage and that is the one place the id is
    doing a job for a human. Registering both slots is harmless — Quasar only
    uses the ones whose columns exist.

    An operator's board that cannot roll a seed still gets a seed *cell*
    (``want_seed_readonly``): with no slot at all Quasar prints the raw column
    value, which for a seed is an untruncated URL.
    """
    discord_id_js = f"'{discord_id}'" if discord_id else 'null'

    table.add_slot('body-cell-edit', EDIT_SLOT)
    table.add_slot('body-cell-id', ID_SLOT if has_edit else ID_SLOT_READONLY)
    table.add_slot('body-cell-tournament', TOURNAMENT_SLOT)
    table.add_slot('body-cell-scheduled_at', SCHEDULED_AT_SLOT)

    table.add_slot('body-cell-players', _fill(
        PLAYERS_SLOT, admin_controls=admin_controls, access=access, discord_id_js=discord_id_js,
    ))
    for role in ('commentators', 'trackers'):
        table.add_slot(f'body-cell-{role}', _fill(
            CREW_SLOT, admin_controls=admin_controls, access=access,
            discord_id_js=discord_id_js, singular=role[:-1], role=role,
        ))

    if extra_slots:
        for slot_name, slot_template in extra_slots.items():
            table.add_slot(slot_name, slot_template)

    if discord_id:
        table.add_slot('body-cell-watch', WATCH_SLOT)
        table.add_slot('body-cell-stream_volunteer', STREAM_VOLUNTEER_SLOT.replace(
            '__DID__', discord_id_js,
        ))

    if want_seed_slot:
        table.add_slot('body-cell-generated_seed', SEED_SLOT)
    elif want_seed_readonly:
        table.add_slot('body-cell-generated_seed', SEED_SLOT_READONLY)
    if want_state_slot:
        table.add_slot('body-cell-state', _fill(
            STATE_SLOT, admin_controls=admin_controls, access=access,
            discord_id_js=discord_id_js,
        ))
    if want_stage_admin:
        table.add_slot('body-cell-stage', STAGE_ADMIN_SLOT)
    if want_stage_readonly:
        table.add_slot('body-cell-stage', STAGE_READONLY_SLOT)
