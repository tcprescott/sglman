# SGLMan Documentation

SGLMan (Speedgaming Live Manager) is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for Speedgaming Live events, with Discord OAuth login, an in-process Discord bot for notifications and signups, randomizer seed generation, and PostgreSQL storage.

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
| [reference/data-model.md](reference/data-model.md) | `models.py` (all models, enums, match lifecycle), `application/repositories/`, `migrations/` |
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
| [features/crew-management.md](features/crew-management.md) | Commentator/tracker signup, approval, acknowledgment |
| [features/discord-notifications.md](features/discord-notifications.md) | Match lifecycle DM notifications and fan-out |
| [features/event-system.md](features/event-system.md) | In-process event bus: publish/subscribe, sync vs async subscribers, `EventType` registry |
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

## Proposals (not yet implemented)

- [multitenancy-plan.md](multitenancy-plan.md) — phased plan to make SGLMan logically multitenant (dual path-based `/t/<slug>` + custom-domain tenant addressing, platform super-admin surface, one-bot-many-guilds Discord). Design only; no code shipped.
- [online-tournaments-plan.md](online-tournaments-plan.md) — phased plan for SGLMan to **succeed [SahasrahBot](https://github.com/tcprescott/sahasrahbot)** as the online tournament/racing platform: racetime.gg race rooms, async tournaments, presets, racetime identity linking, plus a per-community succession/cutover track. Core principle: tournament logic is **user-definable** (declarative config + strategy engine), not code-per-tournament. Design only; no code shipped.

## Coverage map

Every source area of the repository maps to at least one doc. This table is the audit trail for "100% coverage"; if you add a top-level module or directory, add a row here and cover it.

| Source area | Covered by |
|---|---|
| `main.py` | [architecture.md](architecture.md) (startup/lifespan), [reference/rest-api.md](reference/rest-api.md) (app metadata) |
| `frontend.py` | [reference/frontend.md](reference/frontend.md), [architecture.md](architecture.md) |
| `api/` — routers, schemas, dependencies, rate_limit | [reference/rest-api.md](reference/rest-api.md) |
| `models.py` — 36 models, 9 enums | [reference/data-model.md](reference/data-model.md) |
| `application/services/` — 34 modules | [reference/services.md](reference/services.md); deep dives: [reference/discord-integration.md](reference/discord-integration.md) (discord_service, discord_queue), [reference/seed-generation.md](reference/seed-generation.md) (seedgen_service), [reference/authentication.md](reference/authentication.md) (auth_service), [features/telemetry.md](features/telemetry.md) (telemetry_service) |
| `application/events/` — event bus (`bus.py`, `event.py`, `event_types.py`, `dispatch_queue.py`) | [features/event-system.md](features/event-system.md) |
| `application/repositories/` — 29 repositories | [reference/data-model.md](reference/data-model.md) |
| `application/utils/` — 11 modules | [reference/services.md](reference/services.md); timezone.py → [timezone-handling.md](timezone-handling.md) |
| `middleware/` — auth.py (`protected_page` + `AuthMiddleware`, page-view telemetry) | [reference/authentication.md](reference/authentication.md), [features/telemetry.md](features/telemetry.md) |
| `pages/auth.py`, `pages/challonge_oauth.py` — the OAuth `@ui.page` routes | [reference/authentication.md](reference/authentication.md); challonge_oauth → [reference/services.md](reference/services.md) (challonge_service) |
| `middleware/security_headers.py` | [deployment.md](deployment.md) |
| `middleware/error_handlers.py` | [reference/rest-api.md](reference/rest-api.md) |
| `discordbot/` — 6 handler modules (incl. crew/volunteer acknowledgment, watch buttons) | [reference/discord-integration.md](reference/discord-integration.md) |
| `pages/` — 4 pages, home_tabs/, volunteer_tabs/, admin_tabs/ (incl. reports/) | [reference/frontend.md](reference/frontend.md) |
| `theme/` — base.py, dialogs, table views, realtime.py | [reference/frontend.md](reference/frontend.md) |
| `static/` | [reference/frontend.md](reference/frontend.md) |
| `presets/` — alttpr/, ootr/, smmap/ | [reference/seed-generation.md](reference/seed-generation.md) |
| `migrations/` | [reference/data-model.md](reference/data-model.md), [deployment.md](deployment.md) |
| `scripts/seed_dev.py` | [development.md](development.md) |
| `scripts/generate_vapid_keys.py` | [features/web-push.md](features/web-push.md), [deployment.md](deployment.md) |
| `tests/` | [development.md](development.md) |
| `start.sh`, `Dockerfile`, `docker-compose.yml` | [deployment.md](deployment.md) |
| `.env.example` — every variable | [deployment.md](deployment.md) |
| `.github/workflows/` — test.yml, publish.yml | [development.md](development.md), [deployment.md](deployment.md) |
| `pyproject.toml`, `poetry.lock` | [architecture.md](architecture.md), [development.md](development.md) |
| `CLAUDE.md`, `README.md`, `.gitignore`, `profile.html` | indexed here; hygiene notes in [development.md](development.md) |
