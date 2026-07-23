# Native Tournament Brackets Plan (design record)

> Status: **approved design — not yet implemented.** This is the agreed plan for
> Wizzrobe managing tournament brackets natively (generation, progression,
> standings) instead of mirroring them from the Challonge API. It was produced
> and signed off 2026-07-23; implementation follows the `/add-feature` flow.
> Once shipped, this doc is retained as the design rationale and the library
> research record.

## Context

Bracket structure currently comes from the **Challonge integration**
([services.md → ChallongeService](reference/services.md)): a per-tenant OAuth
service account mirrors participants/matches into `ChallongeParticipant` /
`ChallongeMatch`, players schedule open matchups into local `Match` rows, and
confirmed results are pushed back so Challonge opens the next round. Two costs
drive this plan:

1. **The Challonge API is expensive and quota-bound** — `ChallongeApiUsage`
   exists precisely to ration a monthly request quota per tenant.
2. **Validating the integration needs multiple Challonge accounts**, making
   dev/test friction structural rather than incidental.

Native bracketing removes the external dependency from the core loop the
[online-tournaments plan](online-tournaments/README.md) already delivers
(scheduled restreamed brackets: schedule matchup → race room → result →
advance).

### Requirements

- Formats: **single elimination, double elimination, Swiss, round robin /
  groups** — all four in v1 (decided; no phased fast-follow).
- **Multi-stage tournaments** (group stage → single-elimination playoff,
  Swiss → top cut, …): stages chain within one tournament with rank-based
  advancement between them.
- **1v1 now; team tournaments must remain possible later** without remodeling.
- **Full web UI** (admin management + public bracket view) and **automatic
  bracket management** (results advance the bracket without staff bookkeeping).
- **Prefer existing Python libraries for the correctness-critical logic** —
  pairing/progression must work correctly out of the box; visualization is
  explicitly secondary and may be built (and iterated) in-house.

## Decisions log

| Date | Decision |
|---|---|
| 2026-07-23 | **Engine composition**: port the MIT `double_elimination`/`single_elimination` (smwa) code in-house for elimination; **`swisspair`** as a dependency for Swiss pairing; round robin written in-house (circle method); all behind one strategy interface |
| 2026-07-23 | **`FeatureFlag.BRACKETS`** gates the subsystem per tenant (parallel to `CHALLONGE`, which it is expected to eventually obsolete) |
| 2026-07-23 | **All four formats ship in v1** |
| 2026-07-23 | **Multi-stage tournaments are in scope** (group → SE, Swiss → top cut): `Bracket` is the *stage* aggregate; a tournament-level entrant roster with per-stage entries carries identity across stages; advancement is rank-based via each completed stage's `final_rank`; the next stage is staff-triggered |
| 2026-07-23 | **Placeholder entrants supported** (nullable `user` FK + `display_name`, linkable later) — same pattern as `ChallongeParticipant` / SpeedGaming placeholders |
| 2026-07-23 | **Automation depth = Challonge parity**: confirm auto-advances the bracket and opens next matchups; humans schedule open matchups into `Match` rows (auto-created matches / full auto-scheduling deferred) |
| 2026-07-23 | **One bracket source per tournament**: a tournament uses a native `Bracket` or a Challonge link, never both; the two features coexist per tenant |
| 2026-07-23 | **Visualization built in-house** (custom HTML/SVG or CSS grid); `brackets-viewer.js` (MIT) kept as a fallback since our JSON can match its `brackets-model` shape |

## Library research record (2026-07)

Researched so it is not re-researched. Headline: **no single Python library
covers SE+DE+Swiss+RR at production quality, and no Python port of
`brackets-manager.js` exists** (verified on PyPI and GitHub).

### Adopted

| Piece | Source | License | Notes |
|---|---|---|---|
| SE/DE generation + progression semantics | [`smwa/python-tournaments`](https://github.com/smwa/python-tournaments) (`double_elimination` 1.4.1, `single_elimination` 1.2.0) | **MIT** (LICENSE verified per package in the monorepo; the PyPI metadata merely omits it) | Ported, not depended on: zero-dep ~200-LOC engines with verified seeding, auto-BYEs to next power of two, loser-bracket routing, and grand-final bracket reset (`bracket_reset_finals`, auto-skipped when the WB winner wins GF1). Porting removes their two defects for our use — no stable match IDs and in-memory-only state. Keep the MIT notice with the ported module. |
| Swiss pairing | [`swisspair`](https://github.com/karlosss/swisspair) 0.2.1 | MIT | Stateless per-round `create_matches(players)` — caller supplies points/rank/no-rematch sets/bye eligibility, gets pairings back. Min-cost perfect matching (DFS above ~200 players, tested to 20k). C++ extension with bundled GMP; manylinux/macOS wheels only (fine: Docker deploy). Game-tournament semantics (no chess color baggage). |
| Swiss correctness oracle (CI only) | [`bbpPairings`](https://github.com/BieremaBoyzProgramming/bbpPairings) | Apache-2.0 (verified; forum claims of GPL are wrong) | FIDE's reference Dutch implementation; what Lichess runs. Used only to cross-validate our pairings in CI via TRF files — never a runtime dependency. |
| Round robin | in-house | — | ~30-line circle-method scheduler; not worth a dependency. |
| Standings / tiebreakers | in-house | — | No library provides these generically for a game context. Win points + configurable tiebreakers (Buchholz / opponent-win-% with floor, à la MTG OMW%; `pypair` is the reference implementation). |

### Evaluated and not adopted

| Option | Why not |
|---|---|
| [`evroon/bracket`](https://github.com/evroon/bracket) (~1.7k★, FastAPI) | The only substantial Python tournament system — but **AGPL-3.0** (code must never be copied in) and **no double elimination**. Design reference only. |
| [`brackets-manager.js`](https://github.com/Drarig29/brackets-manager.js) as a Node sidecar | MIT, battle-tested SE/DE/RR (v1.11.0, 2026-05) — but adds a Node runtime to the single-container deploy and has **no Swiss** ("not planned"). Its MIT [`brackets-model`](https://github.com/Drarig29/brackets-model) schema (Stage/Group/Round/Match, opponent slots) informed our model shape; [`brackets-viewer.js`](https://github.com/Drarig29/brackets-viewer.js) (MIT, renders hand-built JSON officially) is the visualization fallback. |
| `caissify-pairings` (Apache-2.0, pure-Python FIDE Dutch) | Strong pure-Python Swiss alternative, but brand new (2026-04, 0★). `swisspair` chosen as more battle-tested; this is the swap-in if swisspair's binary wheel ever becomes a problem. |
| `py4swiss` (MIT, bbpPairings re-implementation) | Verified-identical Dutch pairings, but the TRF-shaped programmatic API is clunky for a non-chess app. |
| `pypair` (MTG Swiss, networkx) | Unmaintained since 2021, not on PyPI, stateful/pickle-oriented. Mined for the OMW% tiebreaker algorithm only. |
| `tournament-organizer` / `tournament-pairings` (MIT, TypeScript) | Full format coverage incl. Swiss + Buchholz/Sonneborn-Berger — the port-source fallback if a ported engine fails validation, but JS. |
| `bracketool`, `no-teg`, `Tourneyket`, `pytournament`, `competitions-scheduler`, `swissdutch`, `tomachess` | Generation-only, student-grade, LGPL-dormant, abandoned, or embryonic. |
| PyPI names `tournaments`, `tournament`, `swiss-pairing(s)`, `brackets-manager`, `mwmatching`, … | Do not exist or are unrelated packages (`brackets` = syntax preprocessor, `pypair` on PyPI = statistics, `matchmaker` = test matchers, `tourney` = AI benchmarking). |

## Architecture

### Engine layer: generate-then-persist, DB as source of truth

Engines live in `application/services/bracket_engines/` and register through the
existing [`tournament_strategies`](reference/services.md) registry
(`register_strategy('bracket_format', 'double_elim')`, …). The engine is invoked
at exactly **two moments**; at all other times the database is authoritative:

1. **Generation** (bracket start): the ported elimination engine builds the full
   match graph — winners bracket, losers bracket, finals (+ conditional reset
   match) — which is walked once and persisted as `BracketMatch` rows carrying
   explicit `winner_to` / `loser_to` self-FKs (+ destination slot). After this,
   **elimination advancement is plain DB logic**: follow the persisted pointer,
   fill the slot, flip states. No engine state, no replay, no ID mapping.
2. **Round pairing** (Swiss / round robin): a stateless per-round call —
   standings, no-rematch sets, and bye eligibility are computed from our own
   rows and handed to `swisspair` (or the RR scheduler); returned pairings are
   persisted as the next round's `BracketMatch` rows.

Conventions: **negative `round` numbers denote the losers bracket** (start.gg's
convention); the grand-final reset match is persisted up front and skipped when
the WB winner wins the first grand final (matching the ported engine's
semantics).

### Models (all tenant-scoped)

- **`Bracket`** — one *stage* of a tournament. FK `tournament`; `format` enum
  (`SINGLE_ELIM`, `DOUBLE_ELIM`, `SWISS`, `ROUND_ROBIN`); `state`
  (`DRAFT` → `ACTIVE` → `COMPLETE`); `stage_order` (0-based position in the
  chain; a single-stage tournament has one row at 0); `config` JSON validated
  at the service boundary (grand-final reset on/off, Swiss round count, group
  count + points, tiebreaker order, and — on non-first stages — the
  **advancement rule**: how many advance from the previous stage, overall or
  per group, plus the seeding policy).
- **`BracketEntrant`** — the tournament-level roster row carrying identity
  across stages. FK `tournament`; `display_name`; nullable FK `user`
  (**placeholder entrants**: seed now, link later — one link fixes every
  stage); `status` (`ACTIVE`/`DROPPED`). Team support later = the entrant
  pointing at a team instead of a user; this indirection is the
  future-proofing.
- **`BracketEntry`** — an entrant's participation in one stage. FK `bracket`;
  FK `entrant`; `seed` (per-stage — stage 2's seeds derive from stage 1's
  ranks); nullable `group_number` (group-stage formats only; "Group A" is
  derived display, not a model); `final_rank` (written when the stage
  completes, after tiebreakers — this is what advancement consumes); `status`
  (`ACTIVE`/`DROPPED`/`ELIMINATED`).
- **`BracketMatch`** — FK `bracket`; `round` (negative = losers bracket);
  `position`; nullable `group_number`; nullable `entry1`/`entry2`/`winner`
  (→ `BracketEntry`); `state` (`PENDING`/`OPEN`/`COMPLETE`); self-FKs
  `winner_to`/`loser_to` + slot; and a nullable FK → `Match` (SET_NULL) — the
  **same seam `ChallongeMatch.match` uses today**, which is what keeps the
  rest of the platform untouched.

Consequences: one aerich migration; **a leak test per model** (four); seed rows
per format in meaningful mid-states (`scripts/seed_brackets.py`, idempotent,
tenant-threaded like `seed_challonge.py`).

### Multi-stage chaining & groups

A tournament's stages are `Bracket` rows ordered by `stage_order`; groups are
partitions *within* a round-robin stage (`group_number` on entries and matches
— the RR scheduler runs once per group; standings are computed per group).
Chaining is **format-agnostic by construction**: every format's completion
writes `final_rank` onto its entries (points + configured tiebreakers, with a
staff override for genuinely unresolvable ties), and a later stage's
generation consumes the previous stage's ranked entries through its
advancement config ("top 2 per group", "top 8 overall"). Group → SE and
Swiss → top cut are therefore the same mechanism, and any format can feed any
other. Cross-group playoff seeding uses standard snake seeding with best-effort
same-group avoidance in the earliest rounds (verified in tests). Consistent
with the Challonge-parity automation depth, the next stage is
**staff-triggered**: when a stage completes, staff review the standings (and
any tie decisions) and press "start next stage" — nothing advances silently.

### The scheduling seam (deliberately identical to Challonge's)

`BracketService` exposes the same shape `ChallongeService` proved out:
list open matchups for a user → schedule one into a `Match` via `MatchService`
→ on result confirm, a native `advance_if_linked(match, actor)` (the analogue of
`push_result_if_linked`) records the winner, follows the progression pointers or
triggers round pairing, and opens next matchups. Because the seam is identical,
**racetime rooms, crew signup, stream rooms, notifications, and restreams work
unchanged** for native-bracket tournaments.

### Gating (`FeatureFlag.BRACKETS`)

Registry entry in `application/feature_flags.py` (+ enum member, keeping
`tests/test_feature_flags.py` parity); `@protected_page(feature=…)` on the
public bracket page; `and FeatureFlag.BRACKETS in live` on the admin tab;
`require_feature(…)` on the REST routers; the advance path is invoked from
match-confirm flows, which are themselves reachable only for tournaments that
have a bracket — no separate worker in v1 (Challonge-parity automation only).

### Layer touchpoints

- **Repository** — `BracketRepository` subclassing `TenantScopedRepository`
  (scoped reads, stamped writes), exported from `__init__.py`.
- **Service** — `BracketService`: lifecycle (create stages → enroll/seed →
  start stage (generate) → report/override result → advance → complete stage
  + standings → advance entrants into the next stage, staff-triggered);
  `require_found` for lookups; new `AuditActions` + matching `EventType`
  members (+ `ALL`): `bracket.created`, `bracket.started`,
  `bracket.match_completed`, `bracket.advanced`, `bracket.completed`,
  `bracket.stage_advanced`, `bracket.entrant_added`, `bracket.entrant_dropped`;
  `AuditService.write_and_publish` for the pairs. Engines in
  `bracket_engines/` are pure (no ORM) — the service owns persistence.
- **UI** — admin **Brackets** tab (bracket CRUD on `admin_crud.py`
  infrastructure, enroll/seed/start, result override) + public bracket page
  (custom rendering: Toornament's positioned-divs+SVG-connectors technique or
  Leaguepedia's CSS-grid approach; Swiss/RR render as native standings + round
  tables, as Lichess does; a multi-stage tournament renders one section/tab per
  stage with per-group standings). Every table gets the mobile grid treatment.
- **API** — CRUD + standings + open-matchups routers under `api/`, thin over
  the service (`NotFoundError` → 404 via `ServiceErrorRoute`, no router
  preloads), `require_feature(FeatureFlag.BRACKETS)`.
- **Bot** — nothing new in v1; existing match-lifecycle DMs cover it.

## Correctness harness (first-class deliverable)

The engines are ported/adopted from small-community code, so correctness is
proven, not assumed:

- **Invariant simulation tests** (`tests/services/test_bracket_engine_invariants.py`):
  for every format × entrant counts 2–64 × randomized results — every
  non-winner is eliminated exactly per format (double elim = exactly two
  losses), BYEs valid and minimal, loser-bracket routing never pairs a player
  against themself, grand-final reset fires iff the LB winner wins GF1, Swiss
  never rematches while a legal pairing exists, byes go to eligible
  lowest-standing players, round robin schedules each pair exactly once.
- **Swiss cross-validation**: our `swisspair`-driven pairings checked against
  `bbpPairings` (TRF in/out) across generated tournaments in CI.
- **Determinism**: same entrants + seeds + results ⇒ identical persisted graph.
- **Multi-stage invariants**: exactly the configured number of entrants
  advance, and they are the correct ones given final ranks; snake seeding
  places them correctly; same-group opponents do not meet in playoff round 1
  when avoidable; a stage cannot start before its predecessor completes.

Plus the standard matrix: service behavior tests; three tenant-isolation files;
API tests covering 401 / 403-role / 403-read-only / 404 + cross-tenant 404 —
factories and hoisted conftest fixtures throughout, no network.

## Seed & docs touchpoints

- `scripts/seed_brackets.py` wired into `seed_dev.py`: one bracket per format
  in a meaningful mid-state (e.g. DE with an open losers-bracket round; Swiss
  mid-round with a dropped entrant), plus one **two-stage tournament**
  (groups feeding an SE playoff) mid-chain; placeholder + linked entrants both
  represented.
- Docs: new `docs/features/brackets.md`; updates to
  [data-model.md](reference/data-model.md), [services.md](reference/services.md),
  [rest-api.md](reference/rest-api.md), [frontend.md](reference/frontend.md),
  [current-state.md](current-state.md), and the feature-flag docs.

## Implementation breakdown

One PR per unit (adjacent small units may merge when a reviewer would prefer
it). Ordering follows dependencies; units marked ∥ can proceed in parallel once
their dependency lands. Sizes: S (&lt; ~300 lines), M, L. Every model-touching
unit runs the standard gauntlet: aerich migration + drift hook, leak-test
coverage, seed coverage, doc-reminder hooks.

### Phase A — substrate

- **B0 — Flag, enums, models, migration (M).** `FeatureFlag.BRACKETS` enum
  member + `FeatureFlagSpec` registry entry (ships dark — nothing consumes it
  yet); `BracketFormat` / `BracketState` / `BracketMatchState` / entry-status
  enums; the four models (`Bracket`, `BracketEntrant`, `BracketEntry`,
  `BracketMatch`); one migration; **four leak tests**; minimal
  `scripts/seed_brackets.py` rows (one per model — the seed-coverage test
  demands them from day one). No service, no UI.

### Phase B — engines (pure functions, no ORM; ∥ with each other after B1)

- **B1 — Engine interface + single elimination (M).**
  `application/services/bracket_engines/` package: the engine protocol
  (`generate(entries, config) → match-graph description` with rounds,
  positions, BYEs, `winner_to`/`loser_to` pointers), strategy registration
  (`register_strategy('bracket_format', …)`), and the ported MIT
  single-elimination engine (license notice retained). Invariant-harness
  scaffold (`tests/services/test_bracket_engine_invariants.py`): SE invariants
  + determinism, entrant counts 2–64.
- **B2 — Double elimination (M, ∥).** Ported DE engine: losers-bracket
  routing, negative-round convention, conditional grand-final reset. DE
  invariants (exactly-two-losses, no self-pairing, reset fires iff LB winner
  wins GF1).
- **B3 — Round robin + standings/tiebreakers (M, ∥).** Circle-method
  scheduler with `group_number` partitioning; the shared standings module
  (points config, Buchholz, opponent-win-% with floor, head-to-head) used by
  both RR and Swiss `final_rank` computation. RR invariants (each pair exactly
  once per group).
- **B4 — Swiss via `swisspair` (M, ∥).** Dependency + adapter (standings →
  `Player` inputs: points/rank/no-rematch sets/bye eligibility/drops);
  Swiss invariants (no rematch while legal, byes to eligible lowest).
- **B5 — Swiss cross-validation CI (S).** TRF serialization + `bbpPairings`
  binary in the CI job only; generated-tournament pairing comparison. Separate
  unit because it is CI plumbing, not runtime code.

### Phase C — service layer

- **B6 — Repository + lifecycle core (L).** `BracketRepository`
  (TenantScopedRepository); `BracketService` part 1: stage/entrant/entry CRUD,
  config validation, enroll/seed (incl. placeholders), `start` =
  generate-then-persist through an engine. Audit + events for the covered
  actions. Service tests.
- **B7 — Results, advancement, completion (M).** `BracketService` part 2:
  report/override result, pointer-following elimination advancement,
  Swiss/RR next-round pairing, stage completion + `final_rank` write (with
  staff tie override). Remaining audit/events.
- **B8 — Multi-stage chaining (M).** Advancement-rule config validation,
  predecessor-complete gate, rank-based entrant advancement, snake seeding
  with same-group avoidance, staff-triggered `advance_stage`. Multi-stage
  invariants.
- **B9 — Scheduling seam + Challonge exclusivity (M).** Open-matchups-for-user
  query, `schedule_bracket_match` → `MatchService`, `advance_if_linked` wired
  into the match-confirm flow (peer of `push_result_if_linked`), and the
  one-bracket-source-per-tournament guard (native bracket ⊕ Challonge link).
  Tests cover the confirm path both ways.

### Phase D — surfaces (∥ with each other after B7/B9)

- **B10 — Admin Brackets tab (L).** `admin_crud.py`-based stage management:
  CRUD, enroll/seed, start stage, report/override, tie resolution, start next
  stage; flag-gated tab. `/ui-validation` pass.
- **B11 — Public bracket page (L).** Flag-gated page: custom SE/DE rendering
  (the budgeted large-bracket/mobile spike lives here), Swiss/RR standings +
  rounds tables, stage sections, per-group standings. `/ui-validation` pass.
- **B12 — REST API (M).** Routers + schemas under `api/` with
  `require_feature(FeatureFlag.BRACKETS)`; `tests/test_api_brackets.py`
  covering 401 / 403-role / 403-read-only / 404 + cross-tenant 404;
  `/api-validation` pass.

### Phase E — finish

- **B13 — Rich seed + docs (S).** `seed_brackets.py` grown to the meaningful
  mid-states (per format + two-stage chain); `docs/features/brackets.md`;
  reference-doc and [current-state.md](current-state.md) updates.

Critical path: B0 → B1 → B6 → B7 → B9; everything else hangs off it in
parallel. The engines (B1–B5) have no ORM dependency and can be built and
validated against the harness before any service code exists.

## Deferred (explicitly out of v1)

- **Auto-created `Match` rows / full auto-scheduling** of bracket rounds.
- **Team entrants** (the `BracketEntrant` indirection is the prepared hook).
- **Ladders / rating-based formats** (`openskill` noted as the candidate if
  wanted).
- **Challonge retirement**: the integration stays; migration off it is its own
  decision once native brackets are proven in production.
- **Visualization polish**: v1 ships a functional custom bracket view; a
  large-bracket / phone-width rendering spike is budgeted, with
  `brackets-viewer.js` as the drop-in fallback.
