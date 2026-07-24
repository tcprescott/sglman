# Native Brackets

Wizzrobe manages tournament brackets **natively** — generating, progressing, and
standing tournaments in-house — instead of mirroring them from the Challonge API.
It removes the external, quota-bound dependency from the core scheduled-restream
loop (schedule matchup → race room → result → advance) that the
[online-tournaments](../online-tournaments/README.md) system already delivers.

This is the shipped system; the design rationale and 2026-07 library-research
record live in [brackets-plan.md](../brackets-plan.md).

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
| `schedule_bracket_match` (→ `MatchService.create_match`, write a `BracketMatchGame`) | `schedule_challonge_match` |
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
`BRACKET_ENTRANT_DROPPED`. Method-level detail:
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
[bracket-ui-plan.md](../bracket-ui-plan.md)), that draws the canonical
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
  accordion.
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
zoom toolbar, and live auto-refresh. Below `lt.md` elimination brackets degrade
to a per-round accordion. Staff set per-round best-of/time through a per-round
editor in the admin Manage dialog (`BracketService.set_round_metadata`), and
report results by clicking cards in the bracket embedded in the admin Results
dialog. Styling lives in [`static/css/brackets.css`](../../static/css/brackets.css).

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
  **REST** — `test_api_brackets.py`.

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
