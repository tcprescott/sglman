# Bracket ↔ Match Integration Plan (design record)

> Status: **proposed, decisions confirmed 2026-07-26.** The native bracket system
> ([features/brackets.md](../features/brackets.md)) and the scheduled-match
> lifecycle are both shipped and correct in isolation; they meet at exactly one
> seam and read, to a user, as two products sharing a database. This plan closes
> that gap. The [Decisions](#decisions-confirmed-2026-07-26) below were fixed
> interactively with the maintainer. **No model changes and no migration** — the
> work is a shared derived vocabulary, two new seam calls, one guard, richer
> renderers, and three notifications.

## Context: one seam, one direction, one instant

The only structural link between a bracket and the schedule is
`BracketMatchGame.match` — a OneToOne onto `Match`. Everything else is inferred
through it. Information crosses that seam in exactly **one direction** (match →
bracket) at exactly **one instant** (confirmation):

```
confirm_match  ─┬─> ChallongeService.push_result_if_linked   (discord_queue)
                └─> BracketService.advance_if_linked         (discord_queue)
                        └─> SeriesMixin.settle_game_if_linked → clinch → advance

RaceRoomService.record_finish ──> settle_game_if_linked      (racetimebot task)
```

Nothing flows bracket → match at runtime, and **nothing at all** flows for the
four match states between "scheduled" and "confirmed". That produces five
distinct symptoms, which are the five units of work below.

### S1 — The bracket never goes live

`theme/brackets/dialog.py:122` renders `match.scheduled_at`; the card renders the
game's `SCHEDULED / COMPLETE / CANCELLED` badge. Checked In, In Progress,
Finished-awaiting-confirmation, the racetime room, and the stream are absent.
Worse, `theme/brackets/live.py:21` subscribes to `BRACKET_*` events **only**, so
even if the data were on the card, nothing would repaint it when a match starts
or finishes. During the hours a bracket is most watched, it is a static document.

### S2 — Three unrelated state vocabularies

| Model | States | Where it comes from |
|---|---|---|
| `Match` | Scheduled / Checked In / In Progress / Finished / Confirmed | **No enum** — derived from five nullable timestamps (`models/match.py:63`, and again in `MatchDisplayService._get_match_state`) |
| `BracketMatch` | `PENDING` / `OPEN` / `COMPLETE` | `BracketMatchState` |
| `BracketMatchGame` | `SCHEDULED` / `COMPLETE` / `CANCELLED` | `BracketMatchGameState` |

Each surface shows whichever vocabulary it happens to hold. A bracket card says
"Scheduled" for a match that is currently being raced; the schedule says
"In Progress" for the same row; the Discord embed says a third thing.

### S3 — Cancel or delete a match and the bracket never finds out

`_remove_match` publishes `MATCH_DELETED`, `_cancel_match` publishes
`MATCH_CANCELLED`, and **nothing on the bracket side subscribes to either.**
`BracketMatchGame.match` goes `SET_NULL`, the game row stays `SCHEDULED`, and its
`game_number` stays consumed — so `_has_free_game_slot` reports the series fully
booked:

```python
# _bracket/scheduling.py:43
return len({g.game_number for g in games}) < best_of
```

**A cancelled best-of-1 leaves its matchup permanently unschedulable** — gone
from `list_open_matches_for_user` (the player dashboard) and from the bracket's
own schedule dialog — until staff notice and manually `unlink_match`. Nothing
surfaces the orphan anywhere. This is the sharpest defect in the seam.

### S4 — The match surfaces carry only a breadcrumb back

`MatchDisplayService._bracket_ref` yields `{id, name, game}`, rendered as
"<stage> · Game N". No round name, no series standing, no seeds, no stakes. In
Discord it is not present at all: `_match_descriptor` and `_match_info_lines`
know about players, time, and stage — a bracket game's DM is indistinguishable
from a casual scheduled match. And **round names live in the presentation layer**
(`theme/brackets/layout.py`), so no service could say "Semifinal" even if it
wanted to.

### S5 — Two doors to a result, and no reconciliation

Staff can settle a matchup with `report_result` on the bracket, or by confirming
the `Match`. The bracket→match direction is handled (`cancel_remaining_games`
tears down a forced 2-0's stranded game 3). The match→bracket direction is not:
`set_match_winner` (`match_service.py:630`) will happily rewrite the ranks of a
match whose game already `COMPLETE`d and advanced the bracket, and nothing
retracts or flags the advancement.

## Decisions (confirmed 2026-07-26)

| # | Decision | Consequence |
|---|---|---|
| **D1** | All four seams are in scope: live state into the bracket, bracket context into match surfaces, lifecycle correctness, one shared status vocabulary. | Five units, U1–U5. |
| **D2** | **The schedule stays the hub; the bracket reflects it.** | The bracket gains no new authority. It is an always-accurate live mirror plus the affordances it already has (schedule a matchup, staff report/override). No re-architecture of where work happens. |
| **D3** | A cancelled or deleted `Match` **frees its game slot automatically.** | Cancelling a Bo1 returns the matchup to schedulable, for players, immediately. No staff step. |
| **D4** | Anonymous bracket viewers see **full live state**, including racetime room and stream links. | The public bracket becomes the link you send viewers. No new data is exposed — the schedule is already anonymous and carries all of it. |
| **D5** | The shared status vocabulary is **derived, with no schema change.** | One pure resolver; the timestamps stay the single source of truth. A persisted column is recorded as [deferred](#deferred). |
| **D6** | Editing the result of a match whose game already settled is **blocked**, pointing staff at the bracket's `override_result`. | One correction path. `override_result` already handles re-advancement; a second one would need an un-advance policy we do not want to own yet. |
| **D7** | Bracket progression gets **player-facing notifications**: matchup-ready (with the schedule link), elimination/advancement, and series context folded into existing match DMs. | The bracket advancing silently is the single loudest "two systems" signal. |

## U1 — One derived status vocabulary

**New:** `application/services/match/match_status.py` — a pure, ORM-free resolver
(a peer of the existing `match_source_guard.py` / `match_request_guard.py` pure
modules). No queries, no imports from NiceGUI, safe for services, API, Discord,
and presentation alike.

```python
class MatchStatus(str, Enum):
    PENDING          = 'pending'           # matchup exists, not yet playable
    UNSCHEDULED      = 'unscheduled'       # playable, no game booked
    SCHEDULED        = 'scheduled'
    CHECKED_IN       = 'checked_in'
    LIVE             = 'live'
    AWAITING_RESULT  = 'awaiting_result'   # finished, not confirmed
    COMPLETE         = 'complete'
    CANCELLED        = 'cancelled'
    NEEDS_RESCHEDULE = 'needs_reschedule'  # game freed by U3; matchup still open


def resolve(
    *,
    match: MatchLike | None,          # duck-typed: the five timestamps
    game_state: BracketMatchGameState | None = None,
    bracket_match_state: BracketMatchState | None = None,
    room_status: RaceRoomStatus | None = None,
) -> MatchStatus
```

Precedence, most-specific first: a settled/cancelled **game** state wins over the
match timestamps (staff can force a result the match never recorded); otherwise
the match timestamps, read newest-first as `MatchDisplayService._get_match_state`
already does; the racetime room is a **tiebreaker only** — an `IN_PROGRESS` room
on a match with no `started_at` still reads `LIVE`, because the room is the
truthier signal for a viewer and the timestamp lags the bot.

Three consumers adapt rather than duplicate:

- `MatchDisplayService._get_match_state` becomes a thin adapter returning the
  existing display strings from `MatchStatus`, so the schedule table's labels
  cannot drift from the bracket's.
- **Colour is defined once**, in the resolver, as a semantic name per status;
  `theme/` maps it to a Quasar colour, `application/utils/discord_embeds.py` maps
  it to its existing `COLOR_*` int. The palette already agrees conceptually
  (`COLOR_STARTED` olive = live, `COLOR_CANCELLED` deep red) — this makes that
  agreement mechanical instead of coincidental.
- `theme/brackets/cards.py`'s `_STATE_CLASS` gains the live statuses, driven by
  the same enum.

**Cost:** none — the resolver is called on data the callers already hold.

## U2 — Live match state into the bracket (S1, D4)

**Data.** `BracketService.list_matches` (the page's existing read, via
`BracketRepository.list_matches`) extends its prefetch to
`games__match__players__user`, plus **one batched query** for racetime rooms keyed by the collected `match_id` set — never a query
per card. This follows the precedent in
[render-cost-plan.md](render-cost-plan.md): a bracket page is a fixed small number
of queries regardless of field size, and the existing
`tests/services/test_bracket_render_layout.py` gains a query-count assertion.

**Render.** `cards.py` and `dialog.py` gain a status pill from U1:

- `LIVE` — accented card border + pulse, and (D4) a **Watch** link resolving to
  the stream room's `stream_url` when present, else the racetime room URL.
- `CHECKED_IN` — amber "starting soon".
- `AWAITING_RESULT` — the card shows the played state without a winner, so a
  viewer understands the bracket is not stuck.
- `NEEDS_RESCHEDULE` — see U3.
- The scheduled time already renders through `match.scheduled_at`, so a
  rescheduled match self-corrects once the card repaints.

**Repaint.** `theme/brackets/live.py` subscribes to the `MATCH_*` events as well:
`MATCH_CREATED`, `MATCH_RESCHEDULED`, `MATCH_UPDATED`, `MATCH_SEATED`,
`MATCH_STARTED`, `MATCH_FINISHED`, `MATCH_CONFIRMED`, `MATCH_RESULT_RECORDED`,
`MATCH_CANCELLED`, `MATCH_DELETED`. The subscriber callback is **sync and
non-blocking** (it runs inside `publish`), so it must filter without a query —
and it can: every `MATCH_*` payload carries `tournament_id`
(`match_schedule_service.py:227`, `match_cancellation.py:54`, and peers), and the
page knows its bracket's tournament. Filtering on `tournament_id` is a slightly
wider net than `bracket_id` — an unrelated match in the same tournament repaints
the view — which the page's existing debounce absorbs. That is the right trade:
the alternative is a query in a sync callback.

**Public.** Both routes are already `@public_page`; live state adds no signed-in
data. `AuthService.is_staff` is `False` for `user is None`, so report/override
affordances stay hidden as they are today. `robots.txt` + `noindex` unchanged.

## U3 — Lifecycle correctness (S3, S5)

### U3a — Free the game slot on cancel/delete (D3)

**New:** `BracketService.release_game_if_linked(match, actor, *, reason)` —
the mirror of `advance_if_linked`, called from `_cancel_match` and
`_remove_match` in `match/match_cancellation.py`.

Three constraints shape it:

1. **It must run before the row is deleted.** `BracketMatchGame.match` is
   `SET_NULL`, so after `_remove_match` the game is unreachable from the match.
   This is the same ordering constraint the cancellation DM fan-out already
   documents ("recipients resolved first, while the match still exists").
2. **Only a `SCHEDULED` game is released.** A `COMPLETE` game keeps its result and
   its consumed slot — `SET_NULL` preserving the recorded outcome is exactly the
   behaviour `models/bracket.py` documents, and the bracket has already advanced
   on it. Deleting the match of a played game is a staff mistake U3b will have
   made hard to reach anyway.
3. **Release means delete the row**, not mark it `CANCELLED`. `next_game_number`
   deliberately treats a cancelled number as consumed, so a `CANCELLED` row would
   not free the slot. This mirrors `unlink_match`, which already deletes a
   `SCHEDULED` game row and audits it — the audit log, not the row, is the record.

New `AuditActions.BRACKET_GAME_RELEASED` + `EventType.BRACKET_GAME_RELEASED`
(additive to `EventType.ALL`; `EventType` is an external contract, so this is a
new member, never a rename), with `{bracket_id, match_id, game_id, game_number,
scheduled_match_id, reason}`.

**The subtle part — re-entrancy with the clinch.** `_clinch` cancels its leftover
games *first* and then calls `_cancel_match` on each (`_teardown_games`), and
`_teardown_games` explicitly documents that the cancel-first ordering is
load-bearing for the auto-open hold. Because `release_game_if_linked` acts only on
`SCHEDULED` games, those already-`CANCELLED` rows are a **no-op**, and a clinched
Bo3 does not have game 3's slot handed back. This falls out of constraint 2 rather
than needing a flag, but it is the case a test must pin.

After release, the matchup returns to `OPEN` with a free slot: it reappears in
`list_open_matches_for_user`, on the player dashboard card, and in the bracket's
schedule dialog. The bracket card shows `NEEDS_RESCHEDULE` — the matchup is open
and unbooked, which is materially different from "never booked" for a reader
mid-event, and (with U5) the entrants are told.

**Pre-existing orphans.** Games stranded by this bug before the fix have
`match_id IS NULL` and `state = SCHEDULED`. `scripts/` gains a small idempotent
repair that releases exactly those, and the admin bracket view surfaces the count
until it is zero.

### U3b — Block result edits on a settled game (D6)

**New:** `application/services/match/bracket_result_guard.py`, modelled directly
on the existing `match_source_guard.py` (the SpeedGaming-ETL read-only guard) —
same shape, same place, same reasoning. `set_match_winner` and the confirm/finish
un-transitions consult it: if the match backs a `COMPLETE` `BracketMatchGame`, the
edit raises a `ValueError` reading

> This match's result is already recorded in <stage name>. Correct it from the
> bracket (Results → Override) so the bracket re-advances with it.

Staff keep a working path — `override_result` — and the bracket cannot silently
disagree with its own games. This is one guard call, not a new subsystem.

### U3c — Scheduled-time duality

`Bracket.config['rounds'][N]['scheduled_at']` is the **planned round time**;
`Match.scheduled_at` is when a specific game actually happens. They are allowed to
differ and today the round header shows one while the dialog shows the other with
no explanation. No code change beyond labelling: the round header reads "Round
time", the card reads the game's real time, and `features/brackets.md` states the
rule.

## U4 — Bracket context into the match surfaces (S4)

**Lift round naming out of presentation.** Round names currently exist only in
`theme/brackets/layout.py`. Move the pure naming function to
`application/services/bracket_engines/round_names.py` (ORM-free, alongside
`standings.py`, which is the established home for shared pure bracket logic) and
have `layout.py` import it. This is what lets a service or a Discord DM say
"Semifinal"; without it, U5's messages cannot be written.

Then:

- **`_bracket_ref` extends** to `{id, name, round_name, game, best_of, standing,
  stakes}` — `standing` being "1-0" from `SeriesMixin._standing_from` (pure, no
  query, on games already prefetched by `match_repository`'s existing
  `bracket_match_game__bracket_match__bracket` chain, widened by one hop),
  `stakes` being "Winner to Semifinal" resolved from `winner_to`.
- **The schedule row** keeps its compact link, now reading
  "Semifinal · Game 2 of 3".
- **`AdminMatchDialog`** gains a matchup panel above the existing link/unlink
  picker (`theme/dialog/_match_bracket_link.py`): seeds, series standing, stakes,
  and a link into the bracket view.

## U5 — Notifications (D7)

Two of the three requested notifications share one trigger, which is worth
stating plainly: a matchup becoming ready to schedule and an entrant advancing
into it are **the same event** seen from two sides. So there are two messages, not
three, both fired from `_settle_match` / `_advance_after_result` in
`_bracket/advancement.py` at the moment a downstream `BracketMatch` reaches `OPEN`
with both entrants linked:

- **To both entrants — "Your <round name> matchup is ready."** Opponent name and
  seed, best-of, and a deep link to the bracket's schedule dialog. Fires **once**,
  keyed on the `PENDING → OPEN` transition, so a matchup whose two slots fill at
  different times does not double-DM.
- **To the eliminated entrant — "Your run has ended."** Final placing where the
  stage has one, and where they were knocked out. In double elimination the
  winners-bracket loser is *not* eliminated — they get the matchup-ready DM for
  their losers-bracket match instead. `loser_to` being non-null is exactly that
  test, so the branch is structural, not a format special-case.
- **Series context in existing DMs** — `_match_descriptor` gains an optional
  `bracket_line` and `_match_info_lines` renders it as
  `Round: Semifinal · Game 2 of 3 · Series 1-0`. Every existing match DM
  (`scheduled_dm`, `rescheduled_dm`, `checked_in_dm`, `cancelled_dm`,
  `state_changed_dm`) and its embed inherits it with no new message types. The
  cancellation DM additionally gains the U3a follow-through: "This game has been
  released — the matchup is open to reschedule."

All of it goes out on `discord_queue`, respects `_dm_opt_ok`, and runs inside
`tenant_scope` like every other queued fan-out. **No feature-flag check is
needed** — these fire from inside bracket code that only runs when a bracket
exists, and `FeatureFlagService.is_enabled` inside a service transaction is
exactly what [feature-flags.md](../features/feature-flags.md) forbids.

## Architecture compliance

- **No model changes, no migration** (D5). `docs/reference/data-model.md` is
  unaffected; the 59-model count is unchanged.
- New pure modules (`match_status.py`, `bracket_result_guard.py`,
  `round_names.py`) sit in the service layer and import no NiceGUI.
- `release_game_if_linked` is a service→service call, the same shape
  `advance_if_linked` already uses from `confirm_match`. No repository reach-through
  from presentation; the bracket dialog keeps calling services only.
- Every new write audits (`BRACKET_GAME_RELEASED`) and publishes its mirror event,
  per the repo's audit/event convention.
- New reads are tenant-scoped through the existing repositories; the batched
  racetime-room lookup in U2 uses `scoped(...)` and gains a leak test.

## Test plan

| Area | Test |
|---|---|
| U1 | Truth table over the resolver: every timestamp combination × game state × room status → expected `MatchStatus`. Pure, no DB. |
| U2 | Query-count assertion on the bracket view (fixed count across field sizes); renderer test that a `LIVE` game produces the watch link and an anonymous context still gets it. |
| U3a | **Cancel a Bo1 → the matchup is schedulable again** (the S3 regression, stated as a test). Delete a match → same. Clinch a Bo3 → game 3's slot stays consumed (the re-entrancy case). `COMPLETE` game's match deleted → result preserved, slot kept. |
| U3b | `set_match_winner` on a settled game raises and names the bracket; `override_result` still works. |
| U4 | `_bracket_ref` payload shape; round names identical between `layout.py` and the lifted module. |
| U5 | Matchup-ready fires once on `PENDING → OPEN`, not twice; the double-elim winners-bracket loser gets matchup-ready, not elimination; DM opt-out respected. |
| Tenancy | Leak test for the new batched room lookup and the release path. |
| REST | `test_api_brackets.py` — match payloads carry the derived status. |
| Live | `/ui-validation` for the bracket card states; `/discord-ux` for the three DM shapes. |

## Dev seed

`scripts/seed_brackets.py` gains states the current fixtures cannot show, since a
state the seed never creates is one no one can review:

- a matchup with a **live** game (`started_at` set, no `finished_at`),
- one **awaiting result** (finished, unconfirmed),
- one **released** matchup (game cancelled, slot free) to exercise
  `NEEDS_RESCHEDULE`,
- a Bo3 **mid-series at 1-0** with game 2 scheduled.

Idempotent (`get_or_create`) and tenant-scoped like the existing rows.

## Docs to update on landing

`features/brackets.md` (live state, the release rule, the correction rule, the new
events), `features/event-system.md` + `features/audit-logging.md`
(`BRACKET_GAME_RELEASED`), `reference/services.md` (the new methods and modules),
`reference/frontend.md` (bracket card statuses), `features/discord-notifications.md`
(the two new DMs and the series line), and this file's status header.

## Deferred (recorded for later)

- **A persisted `MatchState` column.** Worth revisiting when the schedule needs to
  *filter* by state at scale; today the timestamps are authoritative and a second
  source of truth would need reconciling. (D5)
- **Auto-retract and re-advance on a corrected result.** Needs a defined policy for
  downstream matchups that are already scheduled or played. D6's block is the
  deliberate stand-in.
- **Venue / fullscreen live mode** for the bracket — already deferred by
  [bracket-ui-plan.md](bracket-ui-plan.md), and much more compelling once U2
  lands.
- **Bracket-driven crew and restream assignment** (assign commentary to "the
  semifinal" before its game exists).

## Assumptions

Two, stated rather than asked, both cheap to reverse:

1. The `NEEDS_RESCHEDULE` status is shown publicly. It reveals only that a
   scheduled match was called off — already visible by the row vanishing from the
   public schedule.
2. The matchup-ready DM goes to both entrants regardless of who is expected to
   book. `allow_player_match_requests` is off for bracket tournaments, so the
   bracket dialog is the only route either of them has; telling one would be
   arbitrary.
