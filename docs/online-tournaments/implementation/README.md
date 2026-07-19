# Online Tournaments — Implementation Plan (per-PR briefs)

> Turns the [design plan](../README.md) into **PR-sized work packages**. Each brief
> below is a self-contained kickoff for one agent/one PR: scope, dependencies, the
> decisions that bind it, reference implementations to port from
> ([sahabot2](https://github.com/tcprescott/sahabot2), in this session's scope, and
> existing wizzrobe code), acceptance criteria, and what to leave for later.
>
> The **design** is reconciled and decision-complete (see the
> [decisions log](../README.md#decisions-log) and [gap analysis](../gap-analysis.md)).
> These briefs are the implementation layer on top of it.

## How to use these

Point each agent at one `pr-N-*.md`. Read this map for ordering, then the brief.
Every PR must follow the house rules in [CLAUDE.md](../../../CLAUDE.md): three-layer
boundaries, async everywhere, `ValueError` for user errors, `AuditService` +
`event_bus` after commits, tenant scoping via `application/repositories/_tenant.py`,
a migration per model change (`aerich migrate && aerich upgrade`), a leak test for
each new tenant-scoped model, and doc updates. Verify with the `verify` /
`ui-validation` skills before opening the PR.

## PR map

| PR | Title | Feature | Depends on |
|---|---|---|---|
| [0](pr-0-foundations.md) | Foundations: system user, roles, config substrate | cross-cutting | — |
| [1](pr-1-presets.md) | User-managed presets + seedgen preset selection | F2 | 0 |
| [2](pr-2-racetime-identity.md) | Racetime identity linking (OAuth) | F5 | 0 |
| [3](pr-3-racetime-bots.md) | Racetime bots + authorization + room model | F5 | 0 |
| [4](pr-4-racetime-bot-runtime.md) | `racetimebot/` skeleton + `MOCK_RACETIME` + bot health | F5 | 3 |
| [5](pr-5-service-health.md) | Platform external-service health page | platform | 4 (soft) |
| [6](pr-6-racetime-lifecycle.md) | Racetime room lifecycle for scheduled matches | F5 | 1, 2, 4 |
| [7](pr-7-speedgaming-etl.md) | SpeedGaming schedule ETL + placeholder users | F4 | 0 |
| [8](pr-8-discord-events.md) | Discord Events sync | F3 | 7 (soft), native schedule |
| [9](pr-9-async-qualifiers.md) | Async Qualifiers core (web-first) | F1 | 1 |
| [10](pr-10-qualifier-live-races.md) | Async Qualifier live races | F1+F5 | 4, 6, 9 |
| [11](pr-11-randomizer-coverage.md) | Randomizer coverage expansion | F2 | 1 |

## Dependency graph & parallelism

```
PR 0 (foundations) ──┬─► PR 1 (presets) ──┬─► PR 9 (qualifiers) ─► PR 10 (live races)
                     │                    └─► PR 11 (randomizers)
                     ├─► PR 2 (identity) ──────────────┐
                     ├─► PR 3 (bots) ─► PR 4 (runtime) ─┼─► PR 6 (room lifecycle) ─► PR 10
                     │                        └─► PR 5 (health page)
                     └─► PR 7 (SG ETL) ─► PR 8 (Discord events)
```

Once **PR 0** lands, five tracks run in parallel: presets (1), racetime (2→3→4→6),
SG (7→8), qualifiers (9, after 1), and health (5, after 4). The decided-first focus
(**scheduled restreamed brackets, ALTTPR-first**) is the `0 → 1 → 2 → 3 → 4 → 6`
path.

## Brief template

Each brief has: **Goal**, **Depends on / Unblocks**, **Deliverables** (file-level),
**Decisions that apply**, **Reference implementations**, **Acceptance criteria**,
**Out of scope**. Keep PRs to the stated scope — resist pulling later-PR work
forward.
