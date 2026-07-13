# PR 9 — Async Qualifiers core (web-first)

> Feature 1. Roadmap phase 7. A standalone peer aggregate of `Tournament`, web-first.
> The largest single feature; sahabot2 has working scoring/leaderboard code to port.

**Goal:** staff create qualifiers like tournaments; players run self-paced against a
permalink pool inside a window; runs are reviewed and par-scored on a leaderboard.

**Depends on:** PR 1 (presets for pools). **Unblocks:** PR 10 (live races).

## Deliverables

- **Models** (tenant-scoped, all with leak tests): `AsyncQualifier` (typed **window**
  columns `opens_at`/`closes_at`, `runs_per_pool`, `allowed_reattempts`, validated
  JSON `config`; `admins` M2M; `is_active`), `AsyncQualifierPool` (name, `Preset`
  FK), `AsyncQualifierPermalink` (url, notes, `live_race`, `par_time`,
  `par_updated_at`), `AsyncQualifierRun` (FKs → qualifier/user/permalink, nullable
  → live_race; `status` + `review_status` enums; start/end, `runner_vod_url`,
  `reattempted` + `reattempt_reason`, `score`), `AsyncQualifierReviewNote`.
- **Admin surface** mirroring Tournaments (create/edit dialog + tab), gated by
  `QUALIFIER_ADMIN` / per-qualifier `admins`. Pool authoring (paste permalinks or
  roll-N from a preset).
- **Web run execution** (no Discord threads): player selects an eligible pool → an
  **atomic locked draw** assigns a spoiler-safe permalink revealed only at start →
  server-stamped start → live elapsed time → submit finish time + VoD. One active
  run per player; permalink no-repeat; draw fairness (imbalance-forcing).
- **Reviewer queue**: reviewers = the qualifier's `admins`; **self-review blocked**;
  claim-locking so two reviewers don't collide; `pending → approved/rejected`.
- **Par scoring + leaderboard** (port sahabot2): par = mean of N fastest finished;
  score = clamp(0..105, (2 − elapsed/par)·100); per-pool `runs_per_pool` slots,
  unattempted = 0, estimate vs actual. **Active-window information lockdown** — pool,
  par times, and other entrants' runs are staff-only until the qualifier closes
  ([gap §2.1](../gap-analysis.md)).
- **Forfeit/reattempt semantics** ([gap §2.2](../gap-analysis.md)): forfeit is
  irreversible, scores zero, blocks replay unless a reattempt is spent; a reattempt
  voids the prior run, frees the slot, requires a reason, is limited.
- Discord DM notifications only (window open, run reviewed). `async_qualifier.*`
  audit/events.

## Decisions that apply

Peer aggregate, distinct machine, outside the schedule system; web-first (no
threads); reviewers = admins M2M + self-review blocked; `QUALIFIER_ADMIN`; carry
`reattempted`/`reattempt_reason`. Honor gap §2.1–§2.4.

## Reference implementations

- **sahabot2**: `modules/async_qualifier/models/async_qualifier.py`,
  `models/async_tournament.py`, `application/services/async_qualifiers/*` (scoring,
  draw, review), the async web blueprint (visibility gating while active).
- **sglman**: the Tournaments admin tab/dialog + `Tournament.admins` M2M as the
  create/administer template; `AuthService` for review authz.

## Acceptance criteria

- A `QUALIFIER_ADMIN` creates a qualifier with a pool; a player draws (once, atomic),
  submits, and a reviewer (not themselves) approves; the leaderboard par-scores
  correctly; a non-staff player cannot see the pool/leaderboard while it's active.
  Verify via `ui-validation`.

## Out of scope

Live races (PR 10). Discord-thread execution (dropped — not ported).
