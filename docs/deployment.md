# Deployment & Operations Guide

_The operations reference for deploying and running SGLMan: container topology, the authoritative environment-variable table, startup behavior, and runbook. Part of the [documentation index](README.md)._

SGLMan ships as a single application container plus PostgreSQL, orchestrated by [`docker-compose.yml`](../docker-compose.yml). For how the stack got here (MySQL → PostgreSQL move, original Docker/GHCR PRs), see [features/postgresql-migration.md](features/postgresql-migration.md) — this page documents the current setup going forward.

## Topology

[`docker-compose.yml`](../docker-compose.yml) defines two services and one named volume:

```
                        host :8000
                            │
┌───────────────────────────▼───────────────────────────────┐
│ sglman      build: . → image sglman:latest                │
│             ./start.sh prod → uvicorn main:app --workers 1│
│             FastAPI + NiceGUI + Discord bot + DM queue    │
└───────────────────────────┬───────────────────────────────┘
                            │ DB_HOST=postgres:5432 (compose network only)
┌───────────────────────────▼───────────────────────────────┐
│ postgres    postgres:16-alpine                            │
│             volume postgres_data → /var/lib/postgresql/data│
└────────────────────────────────────────────────────────────┘
```

### `postgres` service

| Setting | Value |
|---|---|
| Image | `postgres:16-alpine` |
| Database | `POSTGRES_DB=${DB_NAME:-sglman}` |
| Credentials | `POSTGRES_USER`/`POSTGRES_PASSWORD` from `DB_USERNAME`/`DB_PASSWORD`; compose fails fast (`:?` interpolation) if either is missing from `.env` |
| Ports | none published — reachable only as `postgres:5432` on the compose network |
| Volume | `postgres_data`, mounted at `/var/lib/postgresql/data` |
| Healthcheck | `pg_isready -U ${DB_USERNAME} -d ${DB_NAME:-sglman}` — interval 5s, timeout 5s, retries 10 |
| Restart | `unless-stopped` |

### `sglman` service

| Setting | Value |
|---|---|
| Image | built from [`Dockerfile`](../Dockerfile) (`build: .`), tagged `sglman:latest` |
| Environment | everything in `.env` via `env_file`, plus `DB_HOST=postgres` and `DB_PORT=5432` injected by compose |
| Ports | `8000:8000` |
| Startup order | `depends_on: postgres: condition: service_healthy` — the app only starts after the DB healthcheck passes |
| Restart | `unless-stopped` |

## Container image

### Dockerfile

[`Dockerfile`](../Dockerfile) is a single stage on `python:3.12-slim`:

1. `apt-get install build-essential libpq-dev` — compiler toolchain and PostgreSQL client headers for native wheels.
2. `COPY pyproject.toml poetry.lock` then `pip install poetry`, `poetry config virtualenvs.create false`, `poetry install --no-interaction --no-ansi`. **No virtualenv** — dependencies go into the system interpreter, so both `poetry run …` and plain `python` work inside the container. Copying only the lockfiles first keeps the dependency layer cached until `poetry.lock` changes.
3. `COPY . .` — application code last, so code changes do not invalidate the dependency layer.
4. `EXPOSE 8000`; `CMD ["./start.sh", "prod"]`.

Note: `poetry install` runs without `--only main`, so dev-group dependencies (pytest, ipython) are included in the image.

### GHCR publishing

[`.github/workflows/publish.yml`](../.github/workflows/publish.yml) builds and pushes the image to GitHub Container Registry:

- **Triggers:** every push to `main`, and tags matching `v*`.
- **Image:** `ghcr.io/tcprescott/sglman` (registry `ghcr.io`, name taken from `github.repository`).
- **Tag scheme** (`docker/metadata-action`):

| Event | Resulting tags |
|---|---|
| Push to `main` | `main`, `latest` |
| Push tag `v1.2.3` | `1.2.3`, `1.2`, `1` |

- Authenticates with the workflow `GITHUB_TOKEN` (`packages: write`); uses the GitHub Actions build cache (`cache-from`/`cache-to: type=gha`). No `platforms` are specified, so the image is built for the runner's platform (linux/amd64).

The compose file builds locally. To deploy a published image instead, replace `build: .` / `image: sglman:latest` in the `sglman` service with `image: ghcr.io/tcprescott/sglman:<tag>`.

## Environment variables

Template: [`.env.example`](../.env.example). Three loading paths:

- **Docker:** compose passes `.env` to the app via `env_file` and uses it for its own `${…}` interpolation.
- **`./start.sh`:** exports `.env` itself with `export $(grep -v '^#' .env | xargs)` — values containing spaces will not survive this parse; keep `.env` values space-free.
- **Aerich CLI / scripts:** [`migrations/tortoise_config.py`](../migrations/tortoise_config.py) calls `load_dotenv()`, so `poetry run aerich …` picks up `.env` without exporting.

Every variable the application reads:

| Variable | Required | Default | Consumed by | Notes |
|---|---|---|---|---|
| `DB_HOST` | yes | — | `migrations/tortoise_config.py` | Set to `postgres` by compose. Missing → `ValueError` at import; the process never starts. |
| `DB_PORT` | yes | — | `migrations/tortoise_config.py` | Set to `5432` by compose. Same import-time check. |
| `DB_NAME` | yes | — | `migrations/tortoise_config.py`, `docker-compose.yml` | Compose defaults the server-side `POSTGRES_DB` to `sglman`, but the app itself fails without `DB_NAME` in `.env`. |
| `DB_USERNAME` | production: yes | `''` | `migrations/tortoise_config.py`, `application/utils/environment.py`, `docker-compose.yml` | Compose refuses to start when unset (`:?`). With `ENVIRONMENT=production`, blank value aborts startup (see enforcement below). |
| `DB_PASSWORD` | production: yes | `''` | same as `DB_USERNAME` | Same enforcement. URL-encoded into the DSN, so special characters are safe. |
| `ENVIRONMENT` | no | `development` | `application/utils/environment.py`, `frontend.py`, `migrations/tortoise_config.py` | `production` (case-insensitive, after strip) enables the strict checks below. Static assets get no-cache headers only when the value is exactly `development`. |
| `STORAGE_SECRET` | **yes, always** | — | `application/utils/environment.py`, `frontend.py`, `middleware/auth.py` | Signs the NiceGUI session that holds auth state. Blank value aborts startup in *any* environment. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `DISCORD_TOKEN` | yes, unless mock | — | `main.py`, `middleware/auth.py` | Bot token, also used by the OAuth API client. When unset, the bot is skipped with `Warning: DISCORD_TOKEN not set.` and Discord features are dead. Not needed with `MOCK_DISCORD`. |
| `DISCORD_CLIENT_ID` | yes, for real OAuth | — | `middleware/auth.py` | Discord application client ID; used to derive `OAUTH_URL`. |
| `DISCORD_CLIENT_SECRET` | yes, for real OAuth | — | `middleware/auth.py` | OAuth authorization-code exchange. |
| `BASE_URL` | no | `http://localhost:8000` | `middleware/auth.py` | Public base URL of the app (trailing `/` stripped); used to derive `REDIRECT_URL`. Set this in production. |
| `REDIRECT_URL` | no | `{BASE_URL}/oauth/callback` | `middleware/auth.py` | Override only for non-standard callbacks. Must match the redirect URI registered in the Discord Developer Portal. |
| `OAUTH_URL` | no | derived | `middleware/auth.py` | Defaults to the Discord authorize URL built from `DISCORD_CLIENT_ID` and `REDIRECT_URL` with `scope=identify`. |
| `MOCK_DISCORD` | no | off | `application/utils/mock_discord.py` | Truthy values: `1`, `true`, `yes` (case-insensitive). Bypasses OAuth and stubs `DiscordService` — see [features/mock-discord.md](features/mock-discord.md). **Refused when `ENVIRONMENT=production`** (see below). |
| `OOTR_API_KEY` | no | — | `application/services/seedgen_service.py` | Only needed for Ocarina of Time Randomizer seed generation. Missing key raises `ValueError` at generation time, not at startup. |
| `SMMAP_SPOILER_TOKEN` | no | built-in token | `application/services/seedgen_service.py` | Overrides the default spoiler token sent to maprando.com for Super Metroid Map Rando seeds. |
| `SENTRY_DSN` | no | `''` | `application/utils/sentry.py` | When set, enables Sentry error reporting; events are tagged with `ENVIRONMENT` and carry the logged-in user's Discord ID/username. No-op when blank. |
| `SENTRY_TRACES_SAMPLE_RATE` | no | `0` | `application/utils/sentry.py` | Fraction (`0`–`1`) of requests traced for performance. Errors-only by default; only read when `SENTRY_DSN` is set. |
| `CHALLONGE_CLIENT_ID` | no | — | `application/services/challonge_service.py` | Challonge OAuth application client ID. The Challonge integration is considered configured only when both this and `CHALLONGE_CLIENT_SECRET` are set; otherwise the admin Challonge tab reports it as unconfigured. |
| `CHALLONGE_CLIENT_SECRET` | no | — | `application/services/challonge_service.py` | Challonge OAuth client secret; used for the service-account and per-player authorization-code exchanges. |
| `CHALLONGE_REDIRECT_URI` | no | `{BASE_URL}/challonge/oauth/callback` | `application/services/challonge_service.py` | Override only for non-standard callbacks. Must match the redirect URI registered with the Challonge OAuth app. |
| `CHALLONGE_SCOPES` | no | `me tournaments:read matches:read matches:write participants:read` | `application/services/challonge_service.py` | Scopes requested for the shared **service-account** connection. Per-player identity linking always uses scope `me` only. |
| `MOCK_CHALLONGE` | no | off | `application/utils/mock_challonge.py` | Truthy values: `1`, `true`, `yes` (case-insensitive). Swaps in a stub Challonge client/connection for local dev. **Refused when `ENVIRONMENT=production`** (raises `RuntimeError`). |
| `MOCK_CHALLONGE_IDENTITY` | no | `1` | `application/utils/challonge_client.py` | Which canned mock identity the mock player-OAuth flow returns. Only read under `MOCK_CHALLONGE`. |
| `API_RATE_LIMIT_PER_MIN` | no | `120` | `api/rate_limit.py` | Per-client request budget per minute for the REST API, keyed by token (or client IP for unauthenticated requests). |
| `TRUST_PROXY_FORWARDED_FOR` | no | off | `api/rate_limit.py` | Truthy values: `1`, `true`, `yes`, `on`. When set, the rate limiter trusts the `X-Forwarded-For` header for the real client IP — enable only behind a trusted reverse proxy. |

See [reference/authentication.md](reference/authentication.md) for how the OAuth variables are wired into the login flow.

### Startup refusals (fail-fast)

Three independent checks abort the process before it serves a request:

1. **[`migrations/tortoise_config.py`](../migrations/tortoise_config.py)** (import time): `DB_HOST`, `DB_PORT`, `DB_NAME` are always required; when `ENVIRONMENT=production`, blank `DB_USERNAME` or `DB_PASSWORD` raises `ValueError`.
2. **`validate_security_config()`** in `application/utils/environment.py` (called from `frontend.init()`): blank `STORAGE_SECRET` raises `RuntimeError` in every environment; in production, blank `DB_USERNAME` or `DB_PASSWORD` also raises.
3. **`is_mock_discord()`** in `application/utils/mock_discord.py` (evaluated at import of `middleware/auth.py`): `MOCK_DISCORD` truthy while `ENVIRONMENT=production` raises `RuntimeError` — the mock layer is a complete authentication bypass and must never run in production.

## Startup behavior

Boot sequence (`main.py` lifespan, after the import-time checks above):

1. **Migrations auto-apply** — `init_db()` runs Aerich `upgrade()` against `./migrations`, then `Tortoise.init()`. Every boot applies any pending migrations; deploys need no manual `aerich upgrade` step.
2. **Discord bot** — `init_discord_bot()` starts the bot with `DISCORD_TOKEN` as a background task on the shared event loop. Skipped entirely under `MOCK_DISCORD`; without a token it logs a warning and continues.
3. **DM queue** — `discord_queue.start()` launches a single in-process worker that drains queued Discord notification coroutines sequentially.

Shutdown reverses this: the queue worker is cancelled (any still-queued DMs are counted, logged, and dropped), the bot connection closes, then DB connections close. See [architecture.md](architecture.md) for the full process model.

### Single worker — required

`start.sh prod` runs `uvicorn main:app --workers 1`. **Do not raise the worker count.** Three singletons live in process memory:

- the Discord bot — N workers would open N gateway sessions and send duplicate notifications;
- the DM queue — a plain `asyncio.Queue` with no cross-process coordination;
- NiceGUI UI state — per-client element trees and websockets are bound to the process.

Scale vertically; horizontal scaling would require moving the bot and queue out of process first.

### dev vs prod ([`start.sh`](../start.sh))

| | `./start.sh dev` | `./start.sh prod` |
|---|---|---|
| Reload | `--reload` (restart on file change) | off |
| Host binding | uvicorn default (`127.0.0.1`, localhost only) | `0.0.0.0` (required inside a container) |
| Workers | n/a (reload implies a single process) | `--workers 1` |
| Port | 8000 | 8000 |

Any other argument prints an error and exits 1. The script `cd`s to its own directory first, so it can be started from anywhere.

## Operations

First deploy:

```bash
cp .env.example .env            # fill in credentials (see table above)
docker compose up -d
docker compose logs -f sglman   # watch migrations apply and uvicorn start
```

- **Logs:** `docker compose logs -f sglman` (uvicorn, bot, and queue output) and `docker compose logs -f postgres`.
- **Restart app only:** `docker compose restart sglman` — the database keeps running.
- **Upgrade:**

  ```bash
  git pull
  docker compose build sglman     # or: docker compose pull sglman, if deploying a GHCR image
  docker compose up -d sglman     # recreates the container; pending migrations apply on boot
  ```

- **psql access:** the DB is not published to the host; use `docker compose exec postgres psql -U sglman -d sglman` (names from your `.env`).
- **Manual migration commands** (rarely needed — boot does this automatically):

  ```bash
  docker compose exec sglman poetry run aerich upgrade
  ```

  Schema and migration details: [reference/data-model.md](reference/data-model.md).

### Backup and restore

Logical dumps are the recommended backup. `POSTGRES_USER`/`POSTGRES_DB` are already set inside the container, so these are copy-pasteable as-is:

```bash
# Backup (custom format)
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c' > sglman-$(date +%F).dump

# Restore
docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < sglman-YYYY-MM-DD.dump
```

A filesystem-level alternative is archiving the `postgres_data` volume (named `<project>_postgres_data`, e.g. `sglman_postgres_data`) — only with the stack stopped (`docker compose stop`), never while postgres is running.

### Rollback caveat

Migrations are **forward-applied at every boot**. Rolling back to an older image does **not** undo schema changes: the old code will run against the newer schema, and any image you boot will still auto-upgrade to the newest migration present in its `migrations/` directory. To truly revert a schema change, restore the database from a dump taken before the upgrade. **Take a backup before deploying any release that contains migrations.**

## Health & monitoring

There is no dedicated `/health` endpoint. Useful probes:

| Probe | What it proves |
|---|---|
| `GET /` | UI is up (NiceGUI page render, no login required) |
| `GET /api/docs` | FastAPI is serving (no DB involved) |
| `GET /api/matches?limit=1` | Full read-only DB round-trip via the public REST API (see [reference/rest-api.md](reference/rest-api.md)) |

```bash
curl -fsS http://localhost:8000/api/matches?limit=1 > /dev/null && echo OK
```

- **DB liveness** inside compose is covered by the `pg_isready` healthcheck (5s interval, 10 retries); `docker compose ps` shows the `healthy` state.
- **Crash recovery:** both services use `restart: unless-stopped`, so crashed containers come back automatically.
- **Logs to watch:** everything goes to stdout/stderr at `--log-level info`. Notable lines: `Warning: DISCORD_TOKEN not set.` (app runs but Discord features are dead), `[discord_queue] worker error: …` (a queued Discord notification failed), and `[discord_queue] stopping with N item(s) still queued` at shutdown (those DMs were dropped).
