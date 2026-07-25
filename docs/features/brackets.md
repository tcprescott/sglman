# Native Brackets

Wizzrobe manages tournament brackets **natively** — generating, progressing, and
standing tournaments in-house — instead of mirroring them from the Challonge API.
It removes the external, quota-bound dependency from the core scheduled-restream
loop (schedule matchup → race room → result → advance) that the
[online-tournaments](../online-tournaments/README.md) system already delivers.

This is the shipped system; the design rationale and 2026-07 library-research
record live in [brackets-plan.md](../plans/brackets-plan.md).

Scope: **Staff-managed, tenant-scoped, feature-gated.** A tournament uses a native
bracket **or** a Challonge link, never both. Ships behind
[`FeatureFlag.BRACKETS`](feature-flags.md) — dark by default.

Source:
[`models/bracket.py`](../../models/bracket.py) (four models),
[`application/services/bracket_service.py`](../../application/services/bracket_service.py) (`BracketService`),
[`application/services/bracket_config.py`](../../application/services/bracket_config.py) (config schema),
[`application/services/bracket_engines/`](../../application/services/bracket_engines/) (engines + standings),
[`application/repositories/bracket_repository.py`](../../application/repositories/bracket_repository.py),
[`api/routers/brackets.py`](../../api/routers/brackets.py),
[`pages/admin_tabs/admin_brackets.py`](../../pages/admin_tabs/admin_brackets.py) (admin),
[`pages/brackets.py`](../../pages/brackets.py) (public),
[`theme/brackets/`](../../theme/brackets/) (shared renderer),
[`static/css/brackets.css`](../../static/css/brackets.css).

## Data model

Four tenant-scoped models form one aggregate the lifecycle drives together (full
field tables in [data-model.md](../reference/data-model.md#native-brackets)):

- **`Bracket`** — one **stage** of a tournament. A single-stage tournament has one
  row; a multi-stage tournament has several, ordered by `stage_order`. Carries the
  `format`, the `state` (`DRAFT` → `ACTIVE` → `COMPLETE`), and a schema-validated
  `config` blob.
- **`BracketEntrant`** — the tournament-level roster row that carries an entrant's
  identity across every stage. Placeholder-friendly: a `display_name` now, a
  linked `user` later (one link fixes the entrant in every stage). The indirection
  future-proofs team support.
- **`BracketEntry`** — an entrant's participation within one stage (its `seed`,
  `group_number`, and — once the stage completes — `final_rank`).
- **`BracketMatch`** — one slot in a stage's persisted match graph, carrying the
  `winner_to` / `loser_to` progression pointers, a nullable `best_of` override,
  and optional reported **set scores** (`entry1_score` /
  `entry2_score`, nullable) plus a **`forfeit`** flag. `report_result` /
  `override_result` accept the scores and forfeit flag; the reported winner must
  carry the strictly-higher score **unless** `forfeit` marks a DQ / walkover
  (win-only reporting, with null scores, stays valid). Per-round display chrome
  (scheduled time, and the default `best_of`) lives in `Bracket.config['rounds']` keyed by round
  number, not on the match.

## Formats and multi-stage chaining

Four formats, all in v1, selected per stage via `Bracket.format`
([`BracketFormat`](../reference/data-model.md#bracketformat)):

- **Single elimination** — standard seeded bracket with structural byes.
- **Double elimination** — winners bracket (positive rounds) + losers bracket
  (negative rounds, start.gg's convention), a grand final, and a **conditional
  reset** match persisted but activated only when the losers-bracket entrant wins
  the first grand final.
- **Swiss** — per-round pairing from live standings; no elimination.
- **Round robin** — every within-group pair meets once; the field is optionally
  split into balanced groups.

**Multi-stage tournaments** chain stages within one tournament (e.g. round-robin
groups → single-elimination playoff). Stage 0 runs to completion, writing each
entry's `final_rank`; a later stage carries an `advancement` rule in its config
and is seeded from the prior stage's ranks by `advance_stage` — drawing the top
`count` (per source group or overall), skipping dropped entries, and laying out
seeds by the `snake` (default) or `preserve` policy. Advancement enrolls **fresh
`BracketEntry` rows pointing at the same `BracketEntrant`**, so identity carries
across stages.

## Architecture: generate-then-persist

The pairing/progression **engines are pure structural code** (no ORM, no async):
they turn a seeded field + validated config into a description of a match graph.
`BracketService` maps that onto `BracketMatch` rows and persists it. The engine is
invoked only at two moments:

1. **`start`** — generate the whole graph (elimination / round robin) or pair
   Swiss round 1.
2. **Per Swiss round** — pair the next round from current standings.

At all other times **the persisted `BracketMatch` rows are the source of truth.**
After `start`, elimination advancement is plain **pointer-following**: recording a
result completes the match, then pushes the winner into `winner_to` (and the loser
into `loser_to`) at the recorded `*_to_slot`, settling downstream walkovers and
auto-completing the stage when the final resolves. This makes advancement a graph
walk over stored rows rather than a re-run of the engine — the engine never has to
reproduce prior state.

### Engine composition

Engines register with the shared `tournament_strategies` registry under the
`bracket_format` kind (`@register_strategy('bracket_format', …)`); importing
[`bracket_engines/`](../../application/services/bracket_engines/) auto-imports every
sibling and each self-registers, so `get_bracket_engine(fmt)` resolves one by
`BracketFormat` value. Two engine shapes ([`base.py`](../../application/services/bracket_engines/base.py)):

| Format | Module | Shape | Source |
|---|---|---|---|
| Single elimination | `single_elimination.py` | generative (`generate`) | in-house (`standard_seeding` / `next_power_of_two`) |
| Double elimination | `double_elimination.py` | generative | structure ported in spirit from the MIT `smwa/python-tournaments` |
| Round robin | `round_robin.py` | generative (circle method, snake groups; no progression pointers) | in-house |
| Swiss | `swiss.py` | pairing (`pair_round`, per round) | thin adapter over the MIT **`swisspair`** library |

Round robin, Swiss re-pairing, stage-completion ranking, and the public page's
live display all share one ORM-free standings pass
([`standings.py`](../../application/services/bracket_engines/standings.py)):
`compute_standings(refs, results, config)` over opaque `int` refs, computing match
points and a configurable tiebreaker chain (`buchholz`, `omw`, `head_to_head`)
into 1-based competition ranks (unresolved ties share a rank and list each other
in `tied_with` for a staff override).

The **Swiss adapter is made deterministic** despite `swisspair`'s internal
tie-break RNG by encoding a rank tiebreak into the integer points, so the min-cost
no-rematch matching is unique and reproducible.

## Scheduling seam and Challonge exclusivity

A bracket match spans `best_of` games, and **every game is its own scheduled
`Match`** — that link is `BracketMatchGame.match`, a OneToOne, so a `Match` never
backs more than one game. A best-of-1 is simply a series with a single game, which
is why there is one code path rather than a special case (it replaced the old
one-shot `BracketMatch.match` FK in migration 35). Game rows are created lazily,
at schedule time, and `game_number` is assigned by the service — never by a
caller. `BracketService` still mirrors the Challonge integration method-for-method:

| Bracket (native) | Challonge (mirror) |
|---|---|
| `list_open_matches_for_user` | `list_unscheduled_matches_for_user` |
| `schedule_bracket_match` (→ `create_match` / `submit_match_request`, write a `BracketMatchGame`) | `schedule_challonge_match` |
| `link_match_to_bracket_match` / `unlink_match` (staff attach an existing `Match`) | — |
| `advance_if_linked` (confirmed `Match` → settle the game) | `push_result_if_linked` |

### Best-of-N series

`best_of` resolves **per matchup**: `BracketMatch.best_of` → the round's
`Bracket.config['rounds'][N]['best_of']` → `1`. It is semantic, not chrome —
the scheduler and the clinch both read it. Set it before scheduling; it is
rejected once games exist, because each game's title carries "Game 2 of 3".

The bracket match stays **OPEN for the whole series** and completes only on the
clinch, which delegates to `_record_result`. Pointer-following, the grand-final
reset, walkover settling, and stage completion are therefore reused unchanged —
`entry1_score`/`entry2_score` simply become games won.

Two paths settle a game, so settling is a **compare-and-swap** on the game row:
`RaceRoomService.record_finish` (a racetime finish never *confirms* a match, so
`advance_if_linked` alone would never fire on an auto-room tournament) and
`advance_if_linked` on the serial `discord_queue`. Counting one game twice would
clinch a Bo3 off a single game.

On the clinch, unplayed games are cancelled and their `Match` rows go through
`MatchService.cancel_match`, so players and crew are told. `report_result` /
`override_result` reconcile the same way — a staff-forced 2-0 must not strand a
pre-scheduled game 3.

### Holding the next game's race room

Game N's room must not auto-open while game N-1 is still being raced. The hold is
`BracketService.held_match_ids`, applied in `race_room_worker._tick` over the
whole candidate set (two queries, not one per match) — and it keys on
**`Match.finished_at`, not game state**, because a double forfeit never produces
a COMPLETE game row and would deadlock the series silently.

Holding alone is not enough: the poll's scan starts at `now - 15min`, so a game
whose slot slipped further while the previous game ran long has dropped out of it
for good. `release_next_game` pushes at game-end, reusing
`RaceRoomService.auto_open_if_eligible` (which keeps the lead-window guard, so it
is a no-op when the next game is still legitimately far out). A wider
`SERIES_GRACE_MINUTES` scan backstops a process that died in between.

A prior game whose `Match` was deleted **fails open** — the next game is
released, with a warning. Failing closed produces a room that never opens, with
nothing surfaced anywhere, which is the worse failure. Seed generation needs no
separate hold: it hangs off room creation.

Only OPEN matches whose **both** entrants resolve to a linked `user` are
schedulable. When a linked match is confirmed, `advance_if_linked` maps its winner
back to the winning `BracketEntry` and reports it — advancing the native bracket
the same way `push_result_if_linked` advances Challonge.

### Who may schedule, and the manual-request lockout

A bracket-run tournament schedules **only the matchups the bracket produced**.
That is one toggle plus two authorized callers:

- **`Tournament.allow_player_match_requests`** (default `True`) is turned off
  automatically by `BracketService.create_bracket` (stage 0 only, so a later stage
  cannot undo a staff re-open) and by `ChallongeService.link_tournament`. While it
  is off, `MatchService.submit_match_request` refuses the tournament —
  `assert_player_requests_allowed` in
  [`match_request_guard.py`](../../application/services/match/match_request_guard.py)
  is the enforcement, and `UserMatchDialog` filters those tournaments out of its
  dropdown so the choice is never offered. Staff can turn it back on per
  tournament from the tournament editor.
- **`schedule_bracket_match` gates for itself** and routes by actor: Staff and the
  tournament's admins go through `MatchService.create_match` (and may set a stage
  and crew); the matchup's **own two entrants** go through
  `submit_match_request` with `from_bracket=True`, which is what bypasses the
  toggle — scheduling through the bracket is the path the toggle exists to force.
  A non-privileged caller passing staff-only fields is rejected rather than having
  them silently dropped. `ChallongeService.schedule_challonge_match` passes the
  same flag.

Players see their pending matchups on their dashboard
([`pages/home_tabs/player.py`](../../pages/home_tabs/player.py)), in a card
modelled on the Challonge one, and book them through the shared
[`BracketScheduleDialog`](../../theme/dialog/bracket_schedule_dialog.py) — the same
dialog the staff bracket view opens, in its player mode.

Going the other way, staff who scheduled a match in the ordinary editor can
attach it to the matchup it settles: `link_match_to_bracket_match` writes the
`BracketMatchGame` for an existing `Match`, and `unlink_match` detaches one that
has not been played. The link validates that the match's **player set equals the
two entrants' users** — `_winner_from_ranks` maps the winner by `user_id`, so a
mismatched link would settle nothing and strand the series with no visible cause.
The picker lives in the admin match dialog
([`theme/dialog/_match_bracket_link.py`](../../theme/dialog/_match_bracket_link.py)),
on both create and edit.

A tournament uses a native bracket **or** a Challonge link, never both:
`BracketService._ensure_no_challonge_link` rejects a native bracket on a
Challonge-linked tournament, and the symmetric guard lives in
`ChallongeService.link_tournament`.

## Lifecycle, audit & events

Every write is Staff-gated (`AuthService.is_staff`), audits an
`AuditActions.BRACKET_*` action, and publishes the mirror `EventType.BRACKET_*` on
the [event bus](event-system.md): `BRACKET_CREATED`, `BRACKET_STARTED`,
`BRACKET_MATCH_COMPLETED`, `BRACKET_ADVANCED` (next Swiss round),
`BRACKET_COMPLETED`, `BRACKET_STAGE_ADVANCED`, `BRACKET_ENTRANT_ADDED`,
`BRACKET_ENTRANT_DROPPED`, and the per-game `BRACKET_GAME_SCHEDULED` /
`BRACKET_GAME_COMPLETED` / `BRACKET_GAME_CANCELLED` plus
`BRACKET_GAME_LINKED` / `BRACKET_GAME_UNLINKED` for the staff link/unlink of an
existing `Match`. Scheduling is the one write that is **not** Staff-only — see
[Who may schedule](#who-may-schedule-and-the-manual-request-lockout). Method-level detail:
[services.md → BracketService](../reference/services.md#bracket_servicepy--bracketservice).

## Gating

`BRACKETS` gates every entry surface — never a DB read inside a service
transaction:

- **Public pages** — `@protected_page(..., feature=FeatureFlag.BRACKETS)` on both
  bracket routes (404 when off).
- **Admin tab** — `is_staff and FeatureFlag.BRACKETS in live` in `pages/admin.py`.
- **REST** — `require_feature(FeatureFlag.BRACKETS)` on the `/brackets` router
  mount (whole router 404s when off).

## Presentation — the redesigned bracket view

The public and admin surfaces share one in-house renderer,
[`theme/brackets/`](../../theme/brackets/) (design record:
[bracket-ui-plan.md](../plans/bracket-ui-plan.md)), that draws the canonical
Challonge/start.gg/Liquipedia grammar — connector-lined match cards with seeds,
initial-letter avatar discs, a right-aligned score cell (winner accented via the
app `--q-primary` through `--bracket-*` CSS variables, loser dimmed, "FF" for a
forfeit), sticky round headers with best-of/time chrome, and byes / "Winner of 7"
placeholder hints. The pieces:

- `layout.py` — a **pure, ORM-free layout walker**: a depth-first pass over the
  winner-link tree assigns leaves sequential vertical slots and centers every
  parent on its children (Toornament's algorithm), mapping round → column and
  slot → absolute pixels. Robust to byes and the irregular double-elim losers
  bracket. Also computes elbow connectors, stable match numbers, and round names.
  Unit-tested in [`tests/theme/test_bracket_layout.py`](../../tests/theme/) and
  against real engine graphs in `tests/services/test_bracket_render_layout.py`.
- `cards.py` — the absolute-positioned match card + section renderer (sticky
  headers, connectors); `render_mobile_card` is the flow variant for the phone
  accordion (positioned `relative`, so its match-number badge gets a containing
  block instead of stacking with every other round's).
- `tables.py` — Swiss / group data tables (standings with the tiebreaker chain +
  advancement tint + cut line, per-round pairings, per-group crosstable), built
  from NiceGUI elements (never `ui.html` — entrant names are user-controlled).
- `render.py` — whole-bracket helpers (`render_elimination`,
  `render_elimination_mobile`, `build_context`, `detect_finals`) shared by the
  public page and the admin embed; `dialog.py` — the shared match detail +
  staff report/override dialog; `live.py` — an event-bus subscription that
  refreshes the view on `BRACKET_*` events.

Interactions: click a match → detail dialog (staff get inline report/override
with scores + forfeit), hover-run highlight across a participant's matches, a
zoom toolbar, and live auto-refresh. Staff set per-round best-of/time through a
per-round editor in the admin Manage dialog (`BracketService.set_round_metadata`),
and report results by clicking cards in the bracket embedded in the admin Results
dialog. Styling lives in [`static/css/brackets.css`](../../static/css/brackets.css).

**Responsive rule — exactly one view renders at a time.** The 2-D bracket and the
per-round accordion draw the same graph, so the CSS shows one or the other, never
both: at `lt.md` and up the 2-D view; below it the accordion, with a **List /
Bracket toggle** in the toolbar opting into the horizontally-scrolling 2-D view
(plan decision 6). The toggle is CSS-hidden on desktop, the zoom controls hide in
list mode (they scale the 2-D canvas only), and the chosen view is held per client
outside the `@ui.refreshable` so a live `BRACKET_*` rebuild does not snap the
reader back to the list. The accordion carries the round's best-of/scheduled time
in its panel, standing in for the 2-D sticky round header. The admin Results
dialog embeds the same pair and so inherits the rule — its scroll box is
`.bracket-embed-scroll`, whose `flex: 0 0 auto` is load-bearing (a bare
`overflow: auto` flex item collapses to zero height and the bracket vanishes).

The `--bracket-*` custom properties are declared on **`body`**, not `:root`:
`theme/base.py`'s `ui.colors()` writes the tenant palette's `--q-primary` onto
`body` while Quasar's stock blue sits on `:root`, so a `:root` declaration would
resolve the winner accent against the stock colour and ignore tenant theming.

### Admin dialogs

Every bracket dialog — Create, Manage, Results, Advance, and the shared match
report/override — goes through the house dialog chrome
([`theme/dialog/_helpers.py`](../../theme/dialog/_helpers.py)): `form_dialog`
(or `mobile_sheet` + a `.dialog-header` row) for a full-screen sheet with a
sticky title on phones, and `dialog_actions()` for the sticky bottom bar.
Hand-rolled `ui.dialog()` + `ui.card()` is what left **Start bracket** and
**Close** 1,200–4,400px below the fold on a phone. Two further rules follow from
the same surfaces:

- In the Results dialog the flat **Open / Completed** lists are a *fallback*
  wherever the visual bracket embed renders (elimination formats), so they sit in
  default-closed expansions — a 32-match stage otherwise buried the dialog's own
  actions under ~3,000px of scroll. Swiss and round robin have no embed, so there
  the lists stay open: they are the only surface.
- **`complete_stage` asks first.** It writes every entry's `final_rank` and locks
  the stage with no un-complete, and it fires from one of four adjacent 44px icon
  buttons on a phone card, so it routes through
  [`ConfirmationDialog`](../../theme/dialog/confirmation_dialog.py).

## Correctness harness

Because pairing/progression is correctness-critical, the engines carry a dedicated
test harness under [`tests/services/`](../../tests/services/):

- **`_bracket_sim.py`** — a reusable, engine-agnostic simulation harness (not a
  test module): `validate_graph` asserts a generated graph is internally
  consistent (unique `(round, position)`, every pointer targets an existing match
  with a valid slot, no seed in both slots), and `simulate_*` helpers play a graph
  to a champion.
- **Engine invariants** — `test_bracket_engine_invariants.py`,
  `test_bracket_engine_double_elim.py`, `test_bracket_engine_round_robin.py` check
  structural invariants across field sizes.
- **Swiss cross-validation** — `test_bracket_swiss_crossvalidation.py`
  cross-validates the Swiss engine against **bbpPairings** (a FIDE-grade Dutch
  engine) at the level of hard constraints (no rematch, ≤1 bye, everyone paired):
  each scenario is serialized to TRF(x) and, when `BBPPAIRINGS_BIN` points at a
  built binary, fed to the real parser.
- **Standings, advancement, multi-stage** — `test_bracket_standings.py`,
  `test_bracket_advancement.py`, `test_bracket_multistage.py`.
- **Tenant isolation** — `test_bracket_tenant_isolation.py` (leak test);
  **REST** — `test_api_brackets.py` (lifecycle happy path + auth matrix) and
  `test_api_brackets_management.py` (editing, seeds, drop, result override,
  standings, advance dry run).

## Dev seed

[`scripts/seed_brackets.py`](../../scripts/seed_brackets.py) creates, per tenant, a
dedicated **"Bracket Demo"** tournament per format in a mid-play state (some
matches complete, some open, standings partially formed; the double-elim demo has
an open losers-bracket round; the Swiss demo a mid-round state with a dropped
entrant; the round-robin demo two groups partway) plus a two-stage
groups→playoff tournament mid-chain (stage 0 complete with `final_rank`, stage 1
seeded by advancement and started). It drives the real `BracketService` so the
persisted graph is internally consistent, and both placeholder and linked entrants
are represented. Demos live on their own tournaments, never the Challonge-mirrored
one (the exclusivity guard forbids it).
