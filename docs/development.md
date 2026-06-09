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
   git clone <repo-url> sglman
   cd sglman
   poetry install
   ```

2. Create your `.env` from the template:

   ```bash
   cp .env.example .env
   ```

   Every variable in [`.env.example`](../.env.example), with its dev relevance:

   | Variable | Local dev | Notes |
   |---|---|---|
   | `DB_NAME` | required | Database name (template ships `sglman`; compose also defaults to `sglman`). |
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

3. Start PostgreSQL. Two options, both driven by [`docker-compose.yml`](../docker-compose.yml) (service names: `postgres`, `sglman`):

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

The script loads `.env` itself and connects using the same Tortoise config as the app. It creates:

- **Stream rooms** — Stage 1/2/3, active, with `twitch.tv/sglive`, `sglive2`, `sglive3` URLs
- **System configuration** — `event_start_date` (today, Eastern), `event_end_date` (today + 2 days), `max_concurrent_players=12`, `max_concurrent_stages=3`
- **Seven users** with sequential fake Discord IDs (`100000000000000001`–`…07`):

  | Username | Role |
  |---|---|
  | `staff_user` | `STAFF` |
  | `proctor_user` | `PROCTOR` |
  | `sm_user` | `STREAM_MANAGER` |
  | `player_one` … `player_four` | (none) |

- **One tournament** — "SGL Dev Tournament" (alttpr seed generator, 2 players per match, active), with `staff_user` as both admin and crew coordinator and the four players enrolled
- **Four matches**, one per lifecycle state: "Scheduled Match" (+2 h), "Checked-In Match" (now, Stage 1), "In-Progress Match" (−1 h, Stage 2), and "Finished Match" (−3 h, Stage 1, with finish ranks and confirmation)

**Idempotency:** everything uses `get_or_create`, so the script is safe to re-run — existing records are left unchanged. That also means match timestamps are *not* refreshed on re-run (matches are matched by title + tournament); to regenerate the relative scheduled times, delete the fixture matches (or reset the database) first.

## Database migrations

```bash
poetry run aerich migrate    # generate a migration from model changes
poetry run aerich upgrade    # apply pending migrations
```

- Models live in `models.py`; migration files live in `migrations/models/`.
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
| `tests/test_csv_export.py` | CSV export |
| `tests/test_timezone.py` | Eastern↔UTC utilities |
| `tests/services/` | Service-layer suites: `test_audit_service.py`, `test_auth_service.py`, `test_crew_service.py`, `test_match_schedule_service.py`, `test_match_service.py`, `test_match_watcher_service.py`, `test_reports_service.py`, `test_stream_room_service.py`, `test_system_config_service.py`, `test_tournament_notification_service.py`, `test_tournament_service.py`, `test_triforce_text_service.py`, `test_user_service.py` |

Fixtures from the conftests:

- [`tests/conftest.py`](../tests/conftest.py) — a function-scoped `db` fixture that spins up an **in-memory SQLite** database via `Tortoise.init` + `generate_schemas`. Each test gets a fresh schema; closing the connection discards all rows. (SQLite catches logic errors but not PostgreSQL-specific query behavior.)
- `tests/services/conftest.py` — an autouse `stub_discord_queue` fixture that monkeypatches `discord_queue.enqueue` to capture (and later close) enqueued coroutines, so tests can assert that notifications were sent without a bot connection or "never awaited" warnings.

For the coverage inventory and known gaps, see [features/test-coverage.md](features/test-coverage.md).

## Continuous integration

[`.github/workflows/test.yml`](../.github/workflows/test.yml) runs on pushes to `main` and on pull requests targeting `main`. The single `pytest` job runs on `ubuntu-latest` across a Python matrix of **3.10, 3.11, and 3.12**, with these steps: checkout, set up Python, `pipx install poetry`, cache the Poetry virtualenv (keyed on `poetry.lock`), `poetry install --no-interaction`, `poetry run pytest -q`.

> **Known inconsistency:** the workflow matrix includes Python 3.10 and 3.11, while `pyproject.toml` requires `python = "^3.12"`. Both facts are as found in the repository; the sub-3.12 matrix entries conflict with the declared requirement.

Container image publishing is handled separately by `.github/workflows/publish.yml` (see [deployment.md](deployment.md)).

## Conventions & adding a feature

[../CLAUDE.md](../CLAUDE.md) is canonical for coding conventions — async-everywhere, the no-direct-ORM-writes-from-UI rule, `ValueError` for user-facing service errors, audit action naming (`verb.object` via `AuditActions`), and the NiceGUI rules (`background_tasks.create`, capturing `Client.current`, `@ui.refreshable`). [refactoring-guide.md](refactoring-guide.md) documents the three-layer architecture (presentation → service → repository) with code examples. Read both before writing code.

Standard checklist for a new feature:

1. Add or change the model in `models.py`, then `poetry run aerich migrate` and `poetry run aerich upgrade`
2. Add or extend a repository in `application/repositories/` (export it from `application/repositories/__init__.py`)
3. Add or extend a service in `application/services/` (export it from `application/services/__init__.py`); write audit logs for important actions
4. Build the UI in `pages/` or `theme/dialog/`, calling only service methods
5. Add tests under `tests/services/` (and `tests/` for API or utility code)
6. Write a feature doc in `docs/features/` and link it from the [documentation index](README.md)

## Repository hygiene notes

- `profile.html` at the repo root is a ~5.7 MB profiling artifact, not source code — don't read, edit, or ship it.
- `poetry.lock` is committed; keep it in sync with `pyproject.toml` when changing dependencies (the CI cache is keyed on its hash).
- `.gitignore` covers `.env*` (with an exception for `.env.example`), so local secrets stay out of version control. It also ignores `.nicegui/`, `test_data/`, and the usual Python build/cache artifacts.
