# Wizzrobe Documentation

Wizzrobe runs tournament events — on-site restream events and online tournaments —
with match scheduling, crew and volunteer coordination, brackets, randomizer seed
generation, and Discord integration. FastAPI + NiceGUI on PostgreSQL, logically
multitenant, one deployment serving many communities.

Quick start (install, run, Docker) is in the [root README](../README.md).
Coding conventions and the rules to follow while writing code are in
[CLAUDE.md](../CLAUDE.md) — that file is canonical for anything behavioural.

## Start here

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | Tech stack, process model, startup sequence, three-layer pattern, component diagram, directory map, key design decisions |
| [current-state.md](current-state.md) | Status snapshot: what works, known issues, what is deliberately deferred |
| [development.md](development.md) | Local setup, the `MOCK_DISCORD` loop, dev fixtures, migrations, tests, CI |
| [deployment.md](deployment.md) | Docker topology, the authoritative environment-variable table, GHCR, operations, backups |
| [refactoring-guide.md](refactoring-guide.md) | The three-layer pattern with worked examples from current code |
| [timezone-handling.md](timezone-handling.md) | UTC storage, US/Eastern display, and the utilities that convert |
| [scaling-roadmap.md](scaling-roadmap.md) | Measured capacity, why `--workers N` is unreachable, remaining phases |

## Code reference (`reference/`)

Layer-by-layer detail, kept in step with the source.

| Doc | Source area |
|---|---|
| [reference/data-model.md](reference/data-model.md) | `models/` (models, enums, ERD, match lifecycle), `application/repositories/`, `migrations/` |
| [reference/services.md](reference/services.md) | `application/services/`, `application/utils/` |
| [reference/rest-api.md](reference/rest-api.md) | `api/` — routers, schemas, token auth, rate limiting |
| [reference/authentication.md](reference/authentication.md) | Discord OAuth, `AuthMiddleware`, `protected_page` / `public_page`, `AuthService`, the role matrix |
| [reference/discord-integration.md](reference/discord-integration.md) | `discordbot/`, `application/services/discord/`, the DM queue, `racetimebot/` |
| [reference/seed-generation.md](reference/seed-generation.md) | Randomizer backends, `presets/`, per-tenant credentials |
| [reference/frontend.md](reference/frontend.md) | `frontend.py`, `pages/`, `theme/`, `static/` |

## Features (`features/`)

How each shipped subsystem behaves.

| Doc | Feature |
|---|---|
| [features/brackets.md](features/brackets.md) | Native brackets: four formats, multi-stage chains, best-of-N series, the scheduling seam. Behind `FeatureFlag.BRACKETS` |
| [features/match-participation.md](features/match-participation.md) | Crew signup and approval, player and crew acknowledgment, match watching |
| [features/discord.md](features/discord.md) | Match DMs and fan-out, guild-role → app-role sync, notification preferences, `MOCK_DISCORD` |
| [features/online-tournaments.md](features/online-tournaments.md) | SahasrahBot succession, user-definable tournament config, racetime/SpeedGaming/Discord-Events design rules |
| [features/multitenancy.md](features/multitenancy.md) | `/t/<slug>` and custom-domain addressing, tenant context, query scoping, per-tenant roles, `/platform` |
| [features/feature-flags.md](features/feature-flags.md) | Two-tier per-tenant flags: super-admin availability + tenant enable, and how to gate a subsystem |
| [features/mcp-server.md](features/mcp-server.md) | Remote MCP server at `/mcp`: read-only typed tools, OAuth 2.1 only |
| [features/webhooks.md](features/webhooks.md) | Staff-managed outbound webhooks: signing, retries, delivery log |
| [features/event-system.md](features/event-system.md) | In-process event bus: publish/subscribe, `EventType` registry, `match_live` |
| [features/audit-logging.md](features/audit-logging.md) | `AuditService`, `AuditActions` naming, `write_and_publish` |
| [features/telemetry.md](features/telemetry.md) | Page views, curated interactions, domain-event mirror, Staff-only report |
| [features/web-push.md](features/web-push.md) | Declarative Web Push device notifications mirroring Discord DMs |
| [features/admin-reports.md](features/admin-reports.md) | Crew hours, match export, audit viewer, trended insights |
| [features/triforce-texts.md](features/triforce-texts.md) | Player submission and admin moderation |

Some subsystems have no dedicated feature doc and are covered at the reference level
instead — **volunteering**, **equipment lending**, **Challonge**, **API tokens** and
**in-app feedback** all live across
[data-model](reference/data-model.md), [services](reference/services.md),
[frontend](reference/frontend.md) and [rest-api](reference/rest-api.md).

## Work in flight (`plans/`, `reviews/`)

Transient by the convention below — each is deleted once its work ships, and the
feature docs become the truth.

| Doc | What it is |
|---|---|
| [plans/match-runner/](plans/match-runner/README.md) | Making "how a match is run" a first-class type instead of a scattered `is_racetime` boolean, so a third race-management system can be added without touching sixteen call sites |

## Conventions for this directory

- **CLAUDE.md is canonical for rules.** A doc here explains mechanism and gives examples; it should not restate a rule CLAUDE.md already states — that is how the two drift apart.
- **No hand-maintained counts.** Doc-stated totals of models, routers, services or repositories go stale within weeks — every such number in this tree was wrong before this was written, and two of them contradicted each other because the same count was maintained in two files. Say "every model", not a number, unless the number is the point and stable (the eleven roles, the four bracket formats).
- **Design records are not kept after they ship.** Once a plan is implemented, the feature doc is the truth and the plan is deleted — git history holds the rationale. The same goes for point-in-time audit reports.
- **Prose that restates code is what rots.** Prefer a table of names and one-line purposes over paragraphs describing what a function does.
- `.claude/` hooks nag on edits to `models/`, `application/`, `api/`, `pages/`, `theme/`, `discordbot/` and `mcpserver/` — see [`.claude/README.md`](../.claude/README.md).
