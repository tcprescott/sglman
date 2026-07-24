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
[`pages/brackets.py`](../../pages/brackets.py) (public).

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
  `winner_to` / `loser_to` progression pointers and a nullable `match` FK (the
  scheduling seam).

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

`BracketMatch.match` is the same nullable FK seam `ChallongeMatch.match` uses, so a
native bracket match schedules into a real `Match` exactly like a Challonge one.
`BracketService` mirrors the Challonge integration method-for-method:

| Bracket (native) | Challonge (mirror) |
|---|---|
| `list_open_matches_for_user` | `list_unscheduled_matches_for_user` |
| `schedule_bracket_match` (→ `MatchService.create_match`, link `match`) | `schedule_challonge_match` |
| `advance_if_linked` (confirmed `Match` → `report_result`) | `push_result_if_linked` |

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
