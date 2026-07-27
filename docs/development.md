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

   For a local loop you need `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` and `STORAGE_SECRET`, plus `DB_HOST`/`DB_PORT` (e.g. `localhost` / `5432`) when the app runs on your host rather than in the container — compose injects those two only for the app container, and [`migrations/tortoise_config.py`](../migrations/tortoise_config.py) raises at startup without them. The template ships `ENVIRONMENT=production`; change it to `development` or use `./start.sh mock`, which forces the whole mock set for you. Everything else — including which variables are safe to leave unset — is in the [deployment guide's environment table](deployment.md#environment-variables).

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
   ./start.sh mock   # or: ./start.sh dev
   ```

   [`start.sh`](../start.sh) changes to the repo root and sources `.env` with `set -a` (values with spaces survive), then runs uvicorn on port 8000. `dev` binds to localhost with `--reload`; `mock` adds the offline flags (see below); `prod` is the production variant. Full mode table: [deployment.md](deployment.md#startsh-modes).

5. **First boot:** the FastAPI lifespan in [`main.py`](../main.py) runs Aerich `upgrade()` before initializing Tortoise, so all pending migrations apply automatically and the schema is created on an empty database. No manual `aerich upgrade` is needed just to boot.

6. Open `http://localhost:8000`. API docs: `http://localhost:8000/api/docs` (Swagger) and `/api/redoc`.

After first-time setup, the daily loop is just:

```bash
docker-compose up -d postgres   # if not already running
./start.sh mock                 # app with auto-reload on :8000, no external credentials
poetry run pytest               # before pushing
```

## Local development without Discord (MOCK_DISCORD)

The recommended dev loop — `./start.sh mock` sets `MOCK_DISCORD`, `MOCK_CHALLONGE`, `MOCK_SEEDGEN` and `ENVIRONMENT=development` in one command. With `MOCK_DISCORD`:

- `/login` renders a **user picker** instead of redirecting to Discord OAuth — pick any user in the database or use "Create test user". Picked and created users are real rows that persist across restarts.
- All `DiscordService` calls (DMs, guild member lookups, …) are stubbed no-ops, and the **bot does not start**, so `DISCORD_TOKEN` is not required.
- Discord *button* interactions (acknowledgment, crew signup, watch) need a live bot connection and cannot be exercised. Mock mode is a full auth bypass, so the app refuses to start while `ENVIRONMENT=production`.

Details: [features/discord.md](features/discord.md#mock-mode). Auth internals: [reference/authentication.md](reference/authentication.md).

## Dev data

[`scripts/seed_dev.py`](../scripts/seed_dev.py) populates a freshly migrated database with fixtures. The schema must already exist (boot the app once, or run `poetry run aerich upgrade`), then:

```bash
poetry run python scripts/seed_dev.py
```

The script loads `.env` itself and connects using the same Tortoise config as the app. Because the app is multitenant, it seeds **two tenants** so leak tests and manual dev checks have cross-tenant data from day one:

- **Tenant A** reuses the migration's `default` slug (on a fresh DB the additive backfill creates it empty and the script adopts it); **Tenant B** is a second community. Each gets a different feature tier (A → Full Access with one feature switched off; B → Online Tournaments with one force-granted exception) so the [feature-flag](features/feature-flags.md) states are visible.
- **Global (tenant-agnostic):** users, the feature-flag groups (Default / Online Tournaments / Full Access), and the racetime bots. Exactly one user — **`super_admin`** ("Platform Owner") — holds the global `SUPER_ADMIN` role and **no tenant role anywhere**, the fixture for `/platform` and for a platform admin acting inside a community they have no grants in.
- **Per tenant (everything else is tenant-scoped):** stream rooms, system config, an on-site tournament with matches across every lifecycle state + crew, volunteers and shifts, player availability, equipment, an API token (the printed **dev bearer** the `api-validation` skill uses), feedback, triforce texts, Discord role mappings, webhooks, and seeded audit-log + telemetry rows — plus the online-tournament fixtures (presets, race rooms, async qualifiers, Challonge) from `seed_online.py` / `seed_challonge.py`.

Every scoped create threads `tenant` through an explicit `tenant_scope`, mirroring production.

**Idempotency:** everything uses `get_or_create`, so re-running leaves existing records unchanged. The exception is fixtures whose whole point is a *specific* state a migration also creates — the demo feature-flag groups and the two per-tenant overrides use `update_or_create`, so the seed's tier definition wins over the migration's older one. Match timestamps are therefore *not* refreshed on re-run (matches match by title + tournament); delete the fixture matches or reset the database to regenerate relative scheduled times.

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
poetry run pytest                                        # whole suite (parallel)
poetry run pytest tests/services/test_match_service.py   # one suite
poetry run pytest -k acknowledg                          # by keyword
poetry run pytest -n0 tests/services/test_match_service.py   # serial, for -s / pdb
```

Pytest is configured in [`pyproject.toml`](../pyproject.toml) with `asyncio_mode = "auto"` (async test functions need no `@pytest.mark.asyncio`) and `testpaths = ["tests"]`. No PostgreSQL or Discord connection is required.

**The suite runs in parallel by default** — `addopts = "-n auto --dist loadfile"` (pytest-xdist). `loadfile` keeps every test in a module on one worker, so module-level state stays as contained as it is in a serial run. Pass `-n0` to go serial when you need `-s`, a debugger, or readable live output from a single file.

### Keeping it fast

Wall time is dominated by **per-test fixture setup**, not by assertions — test *count* is close to free, so do not thin out parametrized cases to save time. Two rules:

- **Never make an expensive, immutable object a function-scoped fixture.** `build_api_app()` is cached with `functools.cache` in [`tests/api_helpers.py`](../tests/api_helpers.py); use the shared `app` fixture from `tests/conftest.py` rather than re-pasting a local one.
- **Ask whether a test needs the `db` fixture at all.** Pure-function logic — bracket engines, timezone helpers, schema validation — should be tested without it.

Both are enforced mechanically, and the guard's error message explains the case it caught: [`tests/test_fixture_performance.py`](../tests/test_fixture_performance.py) (structural, never timing-based, runs in CI) and [`.claude/scripts/check_fixture_cost.py`](../.claude/scripts/check_fixture_cost.py) (same shapes, blocked at write time).

Layout:

| Path | Covers |
|---|---|
| `tests/api/` | REST API suites, one module per router family, plus cross-router read/write and error-path suites. Each mounts the API router on a minimal FastAPI app and calls it through an httpx `ASGITransport` client; `tests/api_helpers.py` holds the shared token/client setup |
| `tests/mcp/` | MCP server: tool catalogue, its OAuth authorization server, and consent |
| `tests/services/` | One suite per service, plus DB-backed gap-fill suites that exercise the async DB methods and error/notification branches the pure-function suites skip |
| `tests/tenancy/` | Tenant context, middleware, URLs and session, plus every `*isolation*.py` leak test and the `test_leak_test_coverage.py` ratchet that keeps that set complete |
| `tests/theme/` | Presentation logic that is pure Python (bracket layout maths) rather than Vue/Quasar markup |
| `tests/*.py` | Cross-cutting utility suites: timezone, CSV export, repositories, infra plumbing, error handlers, rate limiting, security hardening, schema bounds, seed coverage, … |

Fixtures from the conftests:

- [`tests/conftest.py`](../tests/conftest.py) — a function-scoped `db` fixture that spins up an **in-memory SQLite** database via `Tortoise.init` and replays the CREATE TABLE script rendered once by `_schema_sql()`. Each test gets a fresh schema; closing the connection discards all rows. (SQLite catches logic errors but not PostgreSQL-specific query behavior.)
- `tests/services/conftest.py` — an autouse `stub_discord_queue` fixture that monkeypatches `discord_queue.enqueue` to capture (and later close) enqueued coroutines, so tests can assert that notifications were sent without a bot connection or "never awaited" warnings.

### Known gaps

Still not covered (intentionally — each needs live infra the SQLite suite can't provide):

- Discord bot interaction handlers (`discordbot/`) — require a live Discord connection.
- NiceGUI UI rendering (`pages/`, `theme/`) — no headless browser tests (see the `ui-validation` skill for driving these in a real browser).
- OAuth flow (`middleware/auth.py`) — requires live Discord OAuth.
- The network-backed clients — `application/utils/clients/challonge_client.py`, `twitch_client.py`, and the HTTP randomizer paths in `seedgen_service.py` (`_generate_alttpr`/`_generate_smmap`/`_generate_ootr`) — hit real external APIs; only their local/mocked paths are covered.
- Most of `discord_service.py` — the parts that talk to a live bot connection.
- `application/utils/sentry.py` — instrumentation wiring, run only at process start.

**Coverage tooling:** `pytest-cov` is a dev dependency. Generate a report with:

```bash
poetry run pytest --cov=application --cov=api --cov=middleware --cov-report=term-missing
```

One known quirk is pinned by a test rather than fixed, so a future fix is flagged: `UserRepository.update_discord_info` silently drops its non-field `discriminator`/`avatar` arguments (`tests/test_repositories_coverage.py`).

## Continuous integration

[`.github/workflows/test.yml`](../.github/workflows/test.yml) runs four jobs on pushes to `main` and pull requests targeting it, all on `ubuntu-latest` / Python 3.12:

| Job | What it runs |
|---|---|
| `lint` | `ruff check .` (**blocking**) then `mypy application api middleware main.py frontend.py` (informational) |
| `pytest` | `pytest -q` with coverage over `application`, `api`, `middleware`; Poetry virtualenv cached on `poetry.lock` |
| `swiss-crossvalidation` | builds bbpPairings and runs `tests/services/test_bracket_swiss_crossvalidation.py` against it; the suite skips itself unless `BBPPAIRINGS_BIN` points at the executable, so it is opt-in locally |
| `migrations` | applies the full migration chain to a fresh database |

Container image publishing is handled separately by `.github/workflows/publish.yml` (see [deployment.md](deployment.md)).

## Conventions & adding a feature

[../CLAUDE.md](../CLAUDE.md) is canonical for coding conventions and carries the step-by-step checklist for a new feature (feature-flag decision → model + migration → repository → service → exports → UI → dev seed). [refactoring-guide.md](refactoring-guide.md) shows the three-layer pattern with code examples. Read both before writing code.

Two steps that land after that checklist:

- Add tests under `tests/services/` (and `tests/api/` or `tests/` for API and utility code).
- Write or extend a feature doc in `docs/features/` and link it from the [documentation index](README.md).

## Claude Code hooks

`.claude/settings.json` wires two sets of hooks:

| Where | What |
|---|---|
| `.claude/hooks/` | Shell hooks for documentation discipline — `install-deps.sh` and `session-start.sh` (`SessionStart`: install deps, audit source dirs against their reference docs), `doc-reminder.sh` (`PostToolUse` Write/Edit: names the reference doc a changed source file needs), `doc-check.sh` (`Stop`: diffs `git HEAD` into a documentation checklist) |
| `.claude/scripts/` | Python guardrails run on `PreToolUse`/`PostToolUse` — architecture, async and datetime safety, migration safety, tenant scoping, audit/event conventions, feature-flag gating, fixture cost, table grids, and more |

Every hook sources `_repo.sh` for `$REPO` rather than deriving it from the working directory, because hooks inherit the session's shell cwd, which moves whenever a Bash call `cd`s elsewhere. The executable bit lives in the git index, so a normal checkout preserves it. Full contract, the complete inventory, and the test that enforces both: [`.claude/README.md`](../.claude/README.md).

## Repository hygiene notes

- `poetry.lock` is committed; keep it in sync with `pyproject.toml` when changing dependencies (the CI cache is keyed on its hash).
- `.gitignore` covers `.env*` (with an exception for `.env.example`), so local secrets stay out of version control. It also ignores `.nicegui/`, `test_data/`, and the usual Python build/cache artifacts.
