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
| [reference/services.md](reference/services.md) | `application/services/` (all 16 modules), `application/utils/` |
| [reference/rest-api.md](reference/rest-api.md) | `api.py`, FastAPI app metadata in `main.py` |
| [reference/authentication.md](reference/authentication.md) | `middleware/auth.py`, `middleware/mock_auth.py`, `AuthService` |
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
| [features/match-acknowledgment.md](features/match-acknowledgment.md) | Player and crew match acknowledgment flows |
| [features/match-watcher.md](features/match-watcher.md) | Watch any match for state-change DMs |
| [features/mock-discord.md](features/mock-discord.md) | `MOCK_DISCORD` development mode |
| [features/postgresql-migration.md](features/postgresql-migration.md) | MySQL→PostgreSQL move, Docker setup, GHCR publishing |
| [features/role-based-auth.md](features/role-based-auth.md) | Role system (staff/proctor/stream_manager) and permission matrix |
| [features/test-coverage.md](features/test-coverage.md) | Test suite scope and known gaps |
| [features/tournament-notifications.md](features/tournament-notifications.md) | Per-tournament notification preference levels |
| [features/triforce-texts.md](features/triforce-texts.md) | Player triforce-text submission and moderation |
| [features/ux-improvements.md](features/ux-improvements.md) | UX fixes shipped from the UX audit |

## Historical / point-in-time

- [design.md](design.md) — original requirements sketch (superseded by [architecture.md](architecture.md))
- [ux-audit.md](ux-audit.md) — full UX audit (point-in-time; fixes tracked in [features/ux-improvements.md](features/ux-improvements.md))

## Coverage map

Every source area of the repository maps to at least one doc. This table is the audit trail for "100% coverage"; if you add a top-level module or directory, add a row here and cover it.

| Source area | Covered by |
|---|---|
| `main.py` | [architecture.md](architecture.md) (startup/lifespan), [reference/rest-api.md](reference/rest-api.md) (app metadata) |
| `frontend.py` | [reference/frontend.md](reference/frontend.md), [architecture.md](architecture.md) |
| `api.py` | [reference/rest-api.md](reference/rest-api.md) |
| `models.py` — 20 models, 2 enums | [reference/data-model.md](reference/data-model.md) |
| `application/services/` — 16 modules | [reference/services.md](reference/services.md); deep dives: [reference/discord-integration.md](reference/discord-integration.md) (discord_service, discord_queue), [reference/seed-generation.md](reference/seed-generation.md) (seedgen_service), [reference/authentication.md](reference/authentication.md) (auth_service) |
| `application/repositories/` — 12 repositories | [reference/data-model.md](reference/data-model.md) |
| `application/utils/` — 4 modules | [reference/services.md](reference/services.md); timezone.py → [timezone-handling.md](timezone-handling.md) |
| `middleware/` — auth.py, mock_auth.py | [reference/authentication.md](reference/authentication.md) |
| `discordbot/` — 4 handler modules | [reference/discord-integration.md](reference/discord-integration.md) |
| `pages/` — 3 pages, home_tabs/, admin_tabs/ (incl. reports/) | [reference/frontend.md](reference/frontend.md) |
| `theme/` — base.py, 12 dialogs, 3 table views | [reference/frontend.md](reference/frontend.md) |
| `static/` | [reference/frontend.md](reference/frontend.md) |
| `presets/` — alttpr/, ootr/, smmap/ | [reference/seed-generation.md](reference/seed-generation.md) |
| `migrations/` | [reference/data-model.md](reference/data-model.md), [deployment.md](deployment.md) |
| `scripts/seed_dev.py` | [development.md](development.md) |
| `tests/` | [development.md](development.md), [features/test-coverage.md](features/test-coverage.md) |
| `start.sh`, `Dockerfile`, `docker-compose.yml` | [deployment.md](deployment.md) |
| `.env.example` — every variable | [deployment.md](deployment.md) |
| `.github/workflows/` — test.yml, publish.yml | [development.md](development.md), [deployment.md](deployment.md) |
| `pyproject.toml`, `poetry.lock` | [architecture.md](architecture.md), [development.md](development.md) |
| `CLAUDE.md`, `README.md`, `.gitignore`, `profile.html` | indexed here; hygiene notes in [development.md](development.md) |
