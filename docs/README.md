# Wizzrobe Documentation

Wizzrobe is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for tournament events, with Discord OAuth login, an in-process Discord bot for notifications and signups, randomizer seed generation, and PostgreSQL storage.

For a quick start (install, run, Docker) see the [root README](../README.md). This page is the index for all developer documentation.

## Start here

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | System overview: tech stack, process model, startup sequence, three-layer pattern, component diagram, directory map, key design decisions |
| [current-state.md](current-state.md) | Living status snapshot: what works, feature status, known issues |

## For new developers

- [development.md](development.md) — environment setup, the `MOCK_DISCORD` local workflow, dev fixtures, migrations, running tests, CI
- [refactoring-guide.md](refactoring-guide.md) — the three-layer architecture rules with code examples
- [timezone-handling.md](timezone-handling.md) — UTC storage / US-Eastern display rules and utilities
- [../CLAUDE.md](../CLAUDE.md) — coding conventions, audit-log action naming, NiceGUI patterns and anti-patterns

## For operators

- [deployment.md](deployment.md) — Docker/compose topology, the authoritative environment-variable table, GHCR images, startup behavior, backups and upgrades

## Code reference (`docs/reference/`)

Method-level reference for each layer of the codebase.

| Doc | Source area |
|---|---|
| [reference/data-model.md](reference/data-model.md) | `models/` package (all models, enums, match lifecycle), `application/repositories/`, `migrations/` |
| [reference/services.md](reference/services.md) | `application/services/` (all modules), `application/utils/` |
| [reference/rest-api.md](reference/rest-api.md) | `api/` (routers, schemas, auth, rate limiting), FastAPI app metadata in `main.py` |
| [reference/authentication.md](reference/authentication.md) | `pages/auth.py`, `middleware/auth.py`, `AuthService` |
| [reference/discord-integration.md](reference/discord-integration.md) | `discordbot/`, `discord_service.py`, `discord_queue.py` |
| [reference/seed-generation.md](reference/seed-generation.md) | `seedgen_service.py`, `presets/` |
| [reference/frontend.md](reference/frontend.md) | `frontend.py`, `pages/`, `theme/`, `static/` |

## Feature reference (`docs/features/`)

Implementation notes for each shipped feature.

| Doc | Feature |
|---|---|
| [features/admin-reports.md](features/admin-reports.md) | Admin reports: crew hours, match export, audit log viewer |
| [features/audit-logging.md](features/audit-logging.md) | Audit trail for admin actions (`AuditService`, action conventions) |
| [features/brackets.md](features/brackets.md) | Native tournament brackets: four formats + multi-stage chains, generate-then-persist engine architecture, scheduling seam, `BRACKETS` flag |
| [features/crew-management.md](features/crew-management.md) | Commentator/tracker signup, approval, acknowledgment |
| [features/discord-notifications.md](features/discord-notifications.md) | Match lifecycle DM notifications and fan-out |
| [features/event-system.md](features/event-system.md) | In-process event bus: publish/subscribe, sync vs async subscribers, `EventType` registry |
| [features/feature-flags.md](features/feature-flags.md) | Per-tenant feature flags: two-tier (super-admin availability + tenant enable), page/tab/API/worker gating |
| [features/webhooks.md](features/webhooks.md) | Staff-managed outbound webhooks: signing, retries, delivery log, config UI |
| [features/telemetry.md](features/telemetry.md) | Engagement telemetry: page views, interactions, domain-event mirror, Staff-only report |
| [features/web-push.md](features/web-push.md) | Device notifications: Declarative Web Push (iOS/Android/desktop) mirroring Discord DMs |
| [features/discord-role-sync.md](features/discord-role-sync.md) | Map Discord guild roles to app roles at login |
| [features/match-acknowledgment.md](features/match-acknowledgment.md) | Player and crew match acknowledgment flows |
| [features/match-watcher.md](features/match-watcher.md) | Watch any match for state-change DMs |
| [features/mock-discord.md](features/mock-discord.md) | `MOCK_DISCORD` development mode |
| [features/multitenancy.md](features/multitenancy.md) | Logical multitenancy: `/t/<slug>` addressing, tenant context, query scoping, per-tenant roles, `/platform` surface |
| [features/role-based-auth.md](features/role-based-auth.md) | Role system (staff/proctor/stream_manager) and permission matrix |
| [features/tournament-notifications.md](features/tournament-notifications.md) | Per-tournament notification preference levels |
| [features/triforce-texts.md](features/triforce-texts.md) | Player triforce-text submission and moderation |

Some newer subsystems do not yet have a dedicated feature doc; they are covered at the reference level instead:

- **Volunteering** (opt-in, positions, shifts, assignments, availability, auto-scheduling) — model layer in [reference/data-model.md](reference/data-model.md), services in [reference/services.md](reference/services.md), UI in [reference/frontend.md](reference/frontend.md), endpoints in [reference/rest-api.md](reference/rest-api.md).
- **Equipment lending** (assets, checkout/check-in, QR codes) — same four reference docs.
- **Challonge integration** (service-account OAuth, bracket mirroring, scheduling, per-player identity linking) — same four reference docs.
- **API tokens** and **in-app feedback** — see [reference/rest-api.md](reference/rest-api.md), [reference/services.md](reference/services.md), and [reference/data-model.md](reference/data-model.md).

## Reviews (`docs/reviews/`)

Point-in-time codebase audits — each report names the audited commit, labels findings [new]/[pre-existing] with `file:line` citations, and records an adversarial reconciliation pass. Remediation is delegated to follow-up work; recurring mechanical bug classes feed the `.claude/` guardrail hooks.

- [reviews/2026-07-code-quality-audit.md](reviews/2026-07-code-quality-audit.md) — DRY & engineering-practices audit (whole codebase); remediated in waves, extractions listed in §4.

## Design records (`docs/online-tournaments/`, plan docs)

These capture the design rationale behind now-shipped subsystems. The features themselves are documented in the [feature](#feature-reference-docsfeatures) and [reference](#code-reference-docsreference) docs and their status in [current-state.md](current-state.md); these are kept as the "why it's built this way" record.

- [online-tournaments/](online-tournaments/README.md) — the design for Wizzrobe **succeeding [SahasrahBot](https://github.com/tcprescott/sahasrahbot)** as the online-tournament platform, **now implemented**. An [overview](online-tournaments/README.md) hub (scope, decisions log, succession) plus one doc per feature: [Async Qualifiers](online-tournaments/async-qualifiers.md), [seed rolling](online-tournaments/seed-rolling.md), [Discord Events sync](online-tournaments/discord-events-sync.md), [SpeedGaming ETL](online-tournaments/speedgaming-etl.md), and [racetime race-room lifecycle](online-tournaments/racetime-room-lifecycle.md). Core principle: tournament logic is **user-definable**, not code-per-tournament.
- [multitenancy-plan.md](multitenancy-plan.md) — the original design for making Wizzrobe logically multitenant (`/t/<slug>` + custom-domain addressing, platform super-admin surface, one-bot-many-guilds Discord). **Implemented** — see [features/multitenancy.md](features/multitenancy.md) for the shipped system; this is the design record.
- [brackets-plan.md](brackets-plan.md) — native tournament bracket management (single/double elimination, Swiss, round robin, multi-stage chains e.g. groups → playoff) replacing Challonge-mirrored brackets: engine composition (ported MIT smwa elimination code + `swisspair` + in-house RR behind one strategy interface), generate-then-persist architecture, correctness harness, and the 2026-07 library research record. **Implemented** — see [features/brackets.md](features/brackets.md) for the shipped system; this is retained as the design record.
- [host-based-routing-plan.md](host-based-routing-plan.md) — custom-`Host` tenant resolution and how login survives per-host session cookies (the host-local-OAuth vs signed-handoff fork). **Phase 1 and Phase 2 are implemented** (see [features/multitenancy.md](features/multitenancy.md)), including host-native secondary-provider identity-link OAuth via the same signed handoff; retained as the design record. Only the privileged token-holding flows (Challonge STAFF service-connect, Discord server-connect) remain main-site-only.

## Coverage map

Every source area of the repository maps to at least one doc. This table is the audit trail for "100% coverage"; if you add a top-level module or directory, add a row here and cover it.

| Source area | Covered by |
|---|---|
| `main.py` | [architecture.md](architecture.md) (startup/lifespan), [reference/rest-api.md](reference/rest-api.md) (app metadata) |
| `frontend.py` | [reference/frontend.md](reference/frontend.md), [architecture.md](architecture.md) |
| `api/` — routers, schemas, dependencies, rate_limit | [reference/rest-api.md](reference/rest-api.md) |
| `models/` package — 58 models, 22 enums (per-domain submodules; re-exported from `models/__init__.py`) | [reference/data-model.md](reference/data-model.md) |
| `application/services/` — 76 modules (incl. `bracket_engines/`, `tournament_strategies/`, and the `_bracket/` mixin subpackage composing `BracketService`) | [reference/services.md](reference/services.md); deep dives: [reference/discord-integration.md](reference/discord-integration.md) (discord_service, discord_queue), [reference/seed-generation.md](reference/seed-generation.md) (seed_generation_service), [reference/authentication.md](reference/authentication.md) (auth_service), [features/telemetry.md](features/telemetry.md) (telemetry_service) |
| `application/events/` — event bus (`bus.py`, `event.py`, `event_types.py`, `dispatch_queue.py`) | [features/event-system.md](features/event-system.md) |
| `application/repositories/` — 44 repositories | [reference/data-model.md](reference/data-model.md) |
| `application/utils/` — 30 modules | [reference/services.md](reference/services.md); timezone.py → [timezone-handling.md](timezone-handling.md) |
| `application/tenant_context.py`, `application/feature_flags.py` | [features/multitenancy.md](features/multitenancy.md), [features/feature-flags.md](features/feature-flags.md) |
| `middleware/` — auth.py (`protected_page` + `AuthMiddleware`, page-view telemetry), tenant.py (`TenantMiddleware` + `TransportPrefixMiddleware`) | [reference/authentication.md](reference/authentication.md), [features/multitenancy.md](features/multitenancy.md), [features/telemetry.md](features/telemetry.md) |
| `pages/auth.py`, `pages/challonge_oauth.py`, `pages/twitch_oauth.py`, `pages/racetime_oauth.py` — the OAuth `@ui.page` routes | [reference/authentication.md](reference/authentication.md); the identity-link callbacks → [reference/services.md](reference/services.md) |
| `middleware/security_headers.py` | [deployment.md](deployment.md) |
| `middleware/error_handlers.py` | [reference/rest-api.md](reference/rest-api.md) |
| `discordbot/` — 7 modules (crew signup/acknowledgment, match & volunteer acknowledgment, watch buttons, shared ack/tenant helpers) | [reference/discord-integration.md](reference/discord-integration.md) |
| `racetimebot/` — racetime bot runtime (connection, handler, manager, mock, transport) | [reference/discord-integration.md](reference/discord-integration.md), [reference/services.md](reference/services.md) |
| `pages/` — 13 page modules (incl. `platform.py`, `qualifiers.py`, `brackets.py`), home_tabs/, volunteer_tabs/, admin_tabs/ (incl. reports/) | [reference/frontend.md](reference/frontend.md) |
| `theme/` — base.py, dialogs, table views, realtime.py | [reference/frontend.md](reference/frontend.md) |
| `static/` | [reference/frontend.md](reference/frontend.md) |
| `presets/` — alttpr/, dk64r/, ootr/, smmap/ | [reference/seed-generation.md](reference/seed-generation.md) |
| `migrations/` | [reference/data-model.md](reference/data-model.md), [deployment.md](deployment.md) |
| `scripts/seed_dev.py` | [development.md](development.md) |
| `scripts/generate_vapid_keys.py` | [features/web-push.md](features/web-push.md), [deployment.md](deployment.md) |
| `tests/` | [development.md](development.md) |
| `start.sh`, `Dockerfile`, `docker-compose.yml` | [deployment.md](deployment.md) |
| `.env.example` — every variable | [deployment.md](deployment.md) |
| `.github/workflows/` — test.yml, publish.yml | [development.md](development.md), [deployment.md](deployment.md) |
| `pyproject.toml`, `poetry.lock` | [architecture.md](architecture.md), [development.md](development.md) |
| `CLAUDE.md`, `AGENTS.md`, `README.md`, `.gitignore` | indexed here; hygiene notes in [development.md](development.md) |
