# Development Guide

_Local setup, the mock-Discord dev loop, fixtures, migrations, tests, and CI. Part of the [documentation index](README.md)._

## Prerequisites

- **Python 3.12+** — [`pyproject.toml`](../pyproject.toml) declares `python = "^3.12"`
- **Poetry** — dependency management and virtualenv
- **Docker + docker-compose** — for PostgreSQL 16 (and optionally the full containerized stack)
- **A Discord application** (bot token + OAuth client) — *optional*; local development works without one via [`MOCK_DISCORD`](#local-development-without-discord-mock_discord)

## First-time setup

1. Clone the repository and install dependencies:

   ```bash
   git clone <repo-url> wizzrobe
   cd wizzrobe
   poetry install
   ```

2. Create your `.env` from the template:

   ```bash
   cp .env.example .env
   ```

   Every variable in [`.env.example`](../.env.example), with its dev relevance:

   | Variable | Local dev | Notes |
   |---|---|---|
   | `DB_NAME` | required | Database name (template ships `wizzrobe`; compose also defaults to `wizzrobe`). |
   | `DB_USERNAME` | required | docker-compose refuses to start without it. The app itself only enforces credentials when `ENVIRONMENT=production`. |
   | `DB_PASSWORD` | required | Same enforcement as `DB_USERNAME`. |
   | `DB_HOST`, `DB_PORT` | required for a host-run app | Not in `.env.example`. Auto-set by compose for the **app container** (`postgres` / `5432`). When running the app on your host, add them to `.env` yourself (e.g. `DB_HOST=localhost`, `DB_PORT=5432`) — [`migrations/tortoise_config.py`](../migrations/tortoise_config.py) raises at startup if they are unset. |
   | `STORAGE_SECRET` | required | Signs the NiceGUI session that holds auth state. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `ENVIRONMENT` | set to `development` | The template ships `production` — change it. Production mode requires DB credentials and **refuses to start** with `MOCK_DISCORD`. Unset defaults to `development`. |
   | `MOCK_DISCORD` | recommended: `true` | Bypasses Discord OAuth and stubs all Discord calls. See [below](#local-development-without-discord-mock_discord). |
   | `DISCORD_TOKEN` | optional in mock mode | Bot token. In mock mode the bot never starts; without mock mode a missing token prints a warning and Discord features don't work. |
   | `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` | optional in mock mode | OAuth app credentials from the Discord Developer Portal; only needed for real login. |
   | `BASE_URL` | leave unset | Defaults to `http://localhost:8000` for local dev; used to derive the OAuth redirect URI. |
   | `REDIRECT_URL`, `OAUTH_URL` | leave unset | Derived automatically from `BASE_URL` and `DISCORD_CLIENT_ID`; override only for non-standard values. |
   | `OOTR_API_KEY` | optional | Only for OOTR seed generation. |
   | `SMMAP_SPOILER_TOKEN` | optional | Overrides the built-in Super Metroid Map Rando spoiler token. |

3. Start PostgreSQL. Two options, both driven by [`docker-compose.yml`](../docker-compose.yml) (service names: `postgres`, `wizzrobe`):

   **Database only** — app runs on your host (the usual dev loop):

   ```bash
   docker-compose up -d postgres
   ```

   > **Note:** as written, the `postgres` service does not publish a port to the host. To reach it from a host-run app, add a `ports: ["5432:5432"]` mapping to the `postgres` service (or point `DB_HOST`/`DB_PORT` at any other PostgreSQL you have running), then set `DB_HOST=localhost` and `DB_PORT=5432` in `.env`.

   **Full stack** — app and database both in containers:

   ```bash
   docker-compose up
   ```

   This builds the image, waits for the postgres healthcheck, injects `DB_HOST=postgres` / `DB_PORT=5432` into the app container, and serves on port 8000. Data persists in the `postgres_data` volume.

4. Start the app on your host:

   ```bash
   ./start.sh dev
   ```

   [`start.sh`](../start.sh) changes to the repo root, exports every non-comment line of `.env`, then runs `poetry run uvicorn main:app --reload --log-level info --port 8000`. Dev mode binds to localhost with auto-reload; `./start.sh prod` is the production variant (`--workers 1 --host 0.0.0.0`).

5. **First boot:** the FastAPI lifespan in [`main.py`](../main.py) runs Aerich `upgrade()` before initializing Tortoise, so all pending migrations apply automatically and the schema is created on an empty database. No manual `aerich upgrade` is needed just to boot.

6. Open `http://localhost:8000`. API docs: `http://localhost:8000/api/docs` (Swagger) and `/api/redoc`.

After first-time setup, the daily loop is just:

```bash
docker-compose up -d postgres   # if not already running
./start.sh dev                  # app with auto-reload on :8000
poetry run pytest               # before pushing
```

## Local development without Discord (MOCK_DISCORD)

The recommended dev loop. With `MOCK_DISCORD=true` (and `ENVIRONMENT` not `production`):

- `/login` renders a **user picker** instead of redirecting to Discord OAuth — select any user in the database, or use the "Create test user" shortcut. Picked/created users are real database rows and persist across restarts.
- All `DiscordService` calls (DMs, guild member lookups, etc.) are **stubbed** no-ops.
- The **Discord bot does not start**, so `DISCORD_TOKEN` is not required.

```bash
MOCK_DISCORD=true ./start.sh dev
```

Limits: Discord button interactions (acknowledgment, crew signup, watch) need a real bot connection and cannot be exercised in mock mode. Mock mode is a full auth bypass, so the app refuses to start if it is enabled while `ENVIRONMENT=production`.

Details: [features/mock-discord.md](features/mock-discord.md). Auth internals: [reference/authentication.md](reference/authentication.md).

## Dev data

[`scripts/seed_dev.py`](../scripts/seed_dev.py) populates a freshly migrated database with fixtures. The schema must already exist (boot the app once, or run `poetry run aerich upgrade`), then:

```bash
poetry run python scripts/seed_dev.py
```

The script loads `.env` itself and connects using the same Tortoise config as the app. Because the app is multitenant, it seeds **two tenants** so leak tests and manual dev checks have cross-tenant data from day one:

- **Tenant A** reuses the migration's `default` slug (on a fresh DB the additive backfill creates it empty and the script adopts it); **Tenant B** is a second community. Each gets a different feature tier (A → Full Access with one feature switched off; B → Online Tournaments with one force-granted exception) so the [feature-flag](features/feature-flags.md) states are visible.
- **Global (tenant-agnostic):** users (people log in everywhere and hold per-tenant roles), the feature-flag groups (Default / Online Tournaments / Full Access), and the racetime bots.
- **Per tenant (everything else is tenant-scoped):** stream rooms, system config, an on-site tournament with matches across every lifecycle state + crew, volunteers and shifts, player availability, equipment, an API token (the printed **dev bearer** the `api-validation` skill uses), feedback, triforce texts, Discord role mappings, webhooks, and seeded audit-log + telemetry rows — plus the online-tournament fixtures (presets, race rooms, async qualifiers, Challonge) from `seed_online.py` / `seed_challonge.py`.

Every scoped create threads `tenant` through an explicit `tenant_scope`, mirroring production.

**Idempotency:** everything uses `get_or_create`, so the script is safe to re-run — existing records are left unchanged. That also means match timestamps are *not* refreshed on re-run (matches are matched by title + tournament); to regenerate the relative scheduled times, delete the fixture matches (or reset the database) first.

## Database migrations

```bash
poetry run aerich migrate    # generate a migration from model changes
poetry run aerich upgrade    # apply pending migrations
```

- Models live in the `models/` package (per-domain submodules, re-exported from `models/__init__.py`); migration files live in `migrations/models/`.
- Aerich is configured in the `[tool.aerich]` section of [`pyproject.toml`](../pyproject.toml), pointing at [`migrations/tortoise_config.py`](../migrations/tortoise_config.py).
- **Auto-upgrade caveat:** booting the app applies all pending migrations to whatever database `.env` points at (`main.py:init_db()`). Keep `.env` pointed at a dev database while working on schema changes — and note that anyone who pulls your branch applies your migration on their next boot.

## Running tests

```bash
poetry run pytest                                        # whole suite
poetry run pytest tests/services/test_match_service.py   # one suite
poetry run pytest -k acknowledg                          # by keyword
```

Pytest is configured in [`pyproject.toml`](../pyproject.toml) with `asyncio_mode = "auto"` (async test functions need no `@pytest.mark.asyncio`) and `testpaths = ["tests"]`. No PostgreSQL or Discord connection is required.

Layout:

| Path | Covers |
|---|---|
| `tests/test_api_matches.py` | `GET /matches` integration tests — mounts only the API router on a minimal FastAPI app and calls it through an httpx `ASGITransport` client |
| `tests/test_api_reads.py`, `test_api_match_writes.py`, `test_api_admin_writes.py`, `test_api_phase5_writes.py`, `test_api_coverage_gaps.py` | REST API read/write endpoint suites (via the same `ASGITransport` client; `tests/api_helpers.py` holds shared setup) |
| `tests/test_api_tokens.py` | API-token auth on REST endpoints |
| `tests/test_csv_export.py` | CSV export |
| `tests/test_timezone.py` | Eastern↔UTC utilities |
| `tests/test_error_handlers.py`, `test_rate_limit.py`, `test_security_hardening.py` | Error-handler responses, rate limiting, security hardening |
| `tests/test_repositories_coverage.py` | Direct unit tests for the repository (data-access) layer — CRUD/query/filter/ordering/prefetch behavior in isolation |
| `tests/test_infra_coverage.py` | In-process infra plumbing: event bus, async dispatch queue, `match_events` wiring, and `middleware/error_handlers` responses |
| `tests/test_utils_coverage.py` | Standalone utilities: `environment`, `discord_messages` builders, `easter_eggs`, `qrcode_util` |
| `tests/test_api_volunteers.py`, `test_api_router_gaps.py` | Full REST coverage of the volunteers router and remaining branches across the users/tournament-actions/match-actions/stream-rooms/health/audit routers |
| `tests/services/` | Service-layer suites: `test_api_token_service.py`, `test_audit_service.py`, `test_auth_service.py`, `test_challonge_service.py`, `test_crew_service.py`, `test_discord_member_sync.py`, `test_discord_queue.py`, `test_discord_role_mapping_service.py`, `test_discord_service.py`, `test_equipment_service.py`, `test_feedback_service.py`, `test_match_schedule_service.py`, `test_match_service.py`, `test_match_suggestion_service.py`, `test_match_watcher_service.py`, `test_player_availability_service.py`, `test_reports_service.py`, `test_seedgen_service.py`, `test_stream_room_service.py`, `test_system_config_service.py`, `test_tournament_notification_service.py`, `test_tournament_service.py`, `test_triforce_text_service.py`, `test_user_service.py`, the volunteer suites (`test_volunteer_autoschedule_service.py`, `test_volunteer_availability_service.py`, `test_volunteer_position_service.py`, `test_volunteer_profile_service.py`, `test_volunteer_qualification_service.py`, `test_volunteer_reminder.py`, `test_volunteer_schedule_service.py`, `test_volunteer_scheduling.py`), plus DB-backed gap-fill suites (`test_reports_service_db.py`, `test_match_service_coverage.py`, `test_match_schedule_coverage.py`, `test_equipment_coverage.py`, `test_config_feedback_coverage.py`, `test_notifications_coverage.py`, `test_match_reads_coverage.py`, `test_volunteer_services_coverage.py`, `test_challonge_service_coverage.py`) that exercise the async DB methods and error/notification branches the older pure-function suites skipped |

Fixtures from the conftests:

- [`tests/conftest.py`](../tests/conftest.py) — a function-scoped `db` fixture that spins up an **in-memory SQLite** database via `Tortoise.init` + `generate_schemas`. Each test gets a fresh schema; closing the connection discards all rows. (SQLite catches logic errors but not PostgreSQL-specific query behavior.)
- `tests/services/conftest.py` — an autouse `stub_discord_queue` fixture that monkeypatches `discord_queue.enqueue` to capture (and later close) enqueued coroutines, so tests can assert that notifications were sent without a bot connection or "never awaited" warnings.

### Coverage & known gaps

What the main suites assert, for orientation:

- **Timezone** — Eastern↔UTC parse/format, DST boundaries.
- **CSV export** — formula-injection escaping, filename generation.
- **API** — endpoint filters, limits, approved-crew filtering, and read/write coverage including API-token auth.
- **Audit / Auth** — write/list/filter audit logs; role checks and permission helpers.
- **Crew / Match / Match schedule** — approval and acknowledgment flow, match CRUD, crew signup, lifecycle transitions (seat/start/finish/confirm) and their notifications.
- **Match watcher** — watch/unwatch and watched-match queries.
- **Reports / Stream room / System config** — report aggregation, stream-room CRUD, config get/set and typed accessors.
- **Tournament / Tournament notification** — tournament CRUD, admin/coordinator management, notification-preference upserts.
- **Triforce text / User** — submission and moderation; profile updates, roles, enrollments.

- **Repositories** — the data-access layer is now unit-tested directly (`test_repositories_coverage.py`) in addition to indirect service-test exercise.
- **Infra / utils** — event bus + dispatch queue, `match_events`, error handlers, and the standalone utility helpers.

Line coverage sits at ~92% across `application/`, `api/`, and `middleware/` (measure with the command below).

Still not covered (intentionally — each needs live infra the SQLite suite can't provide):

- Discord bot interaction handlers (`discordbot/`) — require a live Discord connection.
- NiceGUI UI rendering (`pages/`, `theme/`) — no headless browser tests (see the `ui-validation` skill for driving these in a real browser).
- OAuth flow (`middleware/auth.py`) — requires live Discord OAuth.
- The network-backed clients — `application/utils/challonge_client.py`, `twitch_client.py`, and the HTTP randomizer paths in `seedgen_service.py` (`_generate_alttpr`/`_generate_smmap`/`_generate_ootr`) — hit real external APIs; only their local/mocked paths are covered.
- Most of `discord_service.py` — the parts that talk to a live bot connection.
- `application/utils/sentry.py` — instrumentation wiring, run only at process start.

**Coverage tooling:** `pytest-cov` is a dev dependency. Generate a report with:

```bash
poetry run pytest --cov=application --cov=api --cov=middleware --cov-report=term-missing
```

One documented, unused repository quirk is pinned by a test so a future fix is flagged: `UserRepository.update_discord_info` (drops the non-field `discriminator`/`avatar` args). See [reference/data-model.md](reference/data-model.md).

## Continuous integration

[`.github/workflows/test.yml`](../.github/workflows/test.yml) runs on pushes to `main` and on pull requests targeting `main`. The single `pytest` job runs on `ubuntu-latest` across a Python matrix of **3.12 only** (matching the `python = "^3.12"` requirement in `pyproject.toml`), with these steps: checkout, set up Python, `pipx install poetry`, cache the Poetry virtualenv (keyed on `poetry.lock`), `poetry install --no-interaction`, `poetry run pytest -q`.

Container image publishing is handled separately by `.github/workflows/publish.yml` (see [deployment.md](deployment.md)).

## Conventions & adding a feature

[../CLAUDE.md](../CLAUDE.md) is canonical for coding conventions — async-everywhere, the no-direct-ORM-writes-from-UI rule, `ValueError` for user-facing service errors, audit action naming (`verb.object` via `AuditActions`), and the NiceGUI rules (`background_tasks.create`, capturing `context.client` — not the nonexistent `Client.current` — for background UI work, `@ui.refreshable`). [refactoring-guide.md](refactoring-guide.md) documents the three-layer architecture (presentation → service → repository) with code examples. Read both before writing code.

Standard checklist for a new feature:

1. Add or change the model in the `models/` package (per-domain submodule; re-export from `models/__init__.py`), then `poetry run aerich migrate` and `poetry run aerich upgrade`
2. Add or extend a repository in `application/repositories/` (export it from `application/repositories/__init__.py`)
3. Add or extend a service in `application/services/` (export it from `application/services/__init__.py`); write audit logs for important actions
4. Build the UI in `pages/` or `theme/dialog/`, calling only service methods
5. Add tests under `tests/services/` (and `tests/` for API or utility code)
6. Write a feature doc in `docs/features/` and link it from the [documentation index](README.md)

## Claude Code hooks

`.claude/hooks/` contains three shell scripts wired up in `.claude/settings.json` that enforce documentation discipline:

| Hook | Event | What it does |
|---|---|---|
| `session-start.sh` | `SessionStart` | Audits source directories against their reference docs; reports undocumented modules and missing `__init__.py` exports |
| `doc-reminder.sh` | `PostToolUse` Write/Edit | Fires immediately when a tracked Python source file changes; emits the specific reference doc that needs updating |
| `doc-check.sh` | `Stop` | After every Claude turn, diffs `git HEAD` and outputs a documentation checklist for anything that changed |

**After cloning**, the executable bit must be set on all three scripts. It is stored in the git index, so a normal checkout preserves it — but if you ever re-add the files manually, re-run:

```bash
git update-index --chmod=+x .claude/hooks/session-start.sh
git update-index --chmod=+x .claude/hooks/doc-reminder.sh
git update-index --chmod=+x .claude/hooks/doc-check.sh
```

## Repository hygiene notes

- `poetry.lock` is committed; keep it in sync with `pyproject.toml` when changing dependencies (the CI cache is keyed on its hash).
- `.gitignore` covers `.env*` (with an exception for `.env.example`), so local secrets stay out of version control. It also ignores `.nicegui/`, `test_data/`, and the usual Python build/cache artifacts.
