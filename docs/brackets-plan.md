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

- **`Bracket`** — FK `tournament`; `format` enum (`SINGLE_ELIM`, `DOUBLE_ELIM`,
  `SWISS`, `ROUND_ROBIN`); `state` (`DRAFT` → `ACTIVE` → `COMPLETE`);
  `stage_order` (int, default 0 — lets groups→playoff two-stage chains land
  later without remodeling); `config` JSON validated at the service boundary
  (grand-final reset on/off, Swiss round count, points, tiebreaker order).
- **`BracketEntrant`** — FK `bracket`; `seed`; `display_name`; nullable FK
  `user` (**placeholder entrants**: seed now, link later); `status`
  (`ACTIVE`/`DROPPED` — Swiss withdrawals). Team support later = the entrant
  pointing at a team instead of a user; this indirection is the future-proofing.
- **`BracketMatch`** — FK `bracket`; `round` (negative = losers bracket);
  `position`; nullable `entrant1`/`entrant2`/`winner`; `state`
  (`PENDING`/`OPEN`/`COMPLETE`); self-FKs `winner_to`/`loser_to` + slot; and a
  nullable FK → `Match` (SET_NULL) — the **same seam `ChallongeMatch.match`
  uses today**, which is what keeps the rest of the platform untouched.

Consequences: one aerich migration; **a leak test per model** (three); seed rows
per format in meaningful mid-states (`scripts/seed_brackets.py`, idempotent,
tenant-threaded like `seed_challonge.py`).

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
- **Service** — `BracketService`: lifecycle (create → enroll/seed → start
  (generate) → report/override result → advance → complete + standings);
  `require_found` for lookups; new `AuditActions` + matching `EventType`
  members (+ `ALL`): `bracket.created`, `bracket.started`,
  `bracket.match_completed`, `bracket.advanced`, `bracket.completed`,
  `bracket.entrant_added`, `bracket.entrant_dropped`;
  `AuditService.write_and_publish` for the pairs. Engines in
  `bracket_engines/` are pure (no ORM) — the service owns persistence.
- **UI** — admin **Brackets** tab (bracket CRUD on `admin_crud.py`
  infrastructure, enroll/seed/start, result override) + public bracket page
  (custom rendering: Toornament's positioned-divs+SVG-connectors technique or
  Leaguepedia's CSS-grid approach; Swiss/RR render as native standings + round
  tables, as Lichess does). Every table gets the mobile grid treatment.
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

Plus the standard matrix: service behavior tests; three tenant-isolation files;
API tests covering 401 / 403-role / 403-read-only / 404 + cross-tenant 404 —
factories and hoisted conftest fixtures throughout, no network.

## Seed & docs touchpoints

- `scripts/seed_brackets.py` wired into `seed_dev.py`: one bracket per format
  in a meaningful mid-state (e.g. DE with an open losers-bracket round; Swiss
  mid-round with a dropped entrant), placeholder + linked entrants both
  represented.
- Docs: new `docs/features/brackets.md`; updates to
  [data-model.md](reference/data-model.md), [services.md](reference/services.md),
  [rest-api.md](reference/rest-api.md), [frontend.md](reference/frontend.md),
  [current-state.md](current-state.md), and the feature-flag docs.

## Deferred (explicitly out of v1)

- **Auto-created `Match` rows / full auto-scheduling** of bracket rounds.
- **Team entrants** (the `BracketEntrant` indirection is the prepared hook).
- **Two-stage tournaments** (groups → playoff) — `stage_order` reserves the
  shape; the chaining service logic is future work.
- **Ladders / rating-based formats** (`openskill` noted as the candidate if
  wanted).
- **Challonge retirement**: the integration stays; migration off it is its own
  decision once native brackets are proven in production.
- **Visualization polish**: v1 ships a functional custom bracket view; a
  large-bracket / phone-width rendering spike is budgeted, with
  `brackets-viewer.js` as the drop-in fallback.
