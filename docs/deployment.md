# Deployment & Operations Guide

_The operations reference for deploying and running Wizzrobe: container topology, the authoritative environment-variable table, startup behavior, and runbook. Part of the [documentation index](README.md)._

Wizzrobe ships as a single application container plus PostgreSQL, orchestrated by [`docker-compose.yml`](../docker-compose.yml). This page documents the current setup and operations.

## Topology

[`docker-compose.yml`](../docker-compose.yml) defines two services and one named volume:

```
                        host :8000
                            │
┌───────────────────────────▼───────────────────────────────┐
│ wizzrobe      build: . → image wizzrobe:latest                │
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
| Database | `POSTGRES_DB=${DB_NAME:-wizzrobe}` |
| Credentials | `POSTGRES_USER`/`POSTGRES_PASSWORD` from `DB_USERNAME`/`DB_PASSWORD`; compose fails fast (`:?` interpolation) if either is missing from `.env` |
| Ports | none published — reachable only as `postgres:5432` on the compose network |
| Volume | `postgres_data`, mounted at `/var/lib/postgresql/data` |
| Healthcheck | `pg_isready -U ${DB_USERNAME} -d ${DB_NAME:-wizzrobe}` — interval 5s, timeout 5s, retries 10 |
| Restart | `unless-stopped` |

### `wizzrobe` service

| Setting | Value |
|---|---|
| Image | built from [`Dockerfile`](../Dockerfile) (`build: .`), tagged `wizzrobe:latest` |
| Environment | everything in `.env` via `env_file`, plus `DB_HOST=postgres` and `DB_PORT=5432` injected by compose |
| Ports | `8000:8000` |
| Startup order | `depends_on: postgres: condition: service_healthy` — the app only starts after the DB healthcheck passes |
| Restart | `unless-stopped` |

## Container image

### Dockerfile

[`Dockerfile`](../Dockerfile) is a single stage on `python:3.12-slim`:

1. `apt-get install build-essential libpq-dev` — compiler toolchain and PostgreSQL client headers for native wheels.
2. `COPY pyproject.toml poetry.lock` then `pip install poetry`, `poetry config virtualenvs.create false`, `poetry install --only main --no-interaction --no-ansi`. **No virtualenv** (both `poetry run …` and plain `python` work in the container) and `--only main` (no pytest/ipython in the runtime image). Lockfiles are copied first so the dependency layer stays cached until `poetry.lock` changes.
3. `COPY . .` — application code last, so code changes do not invalidate the dependency layer.
4. `EXPOSE 8000`; `CMD ["./start.sh", "prod"]`.

### GHCR publishing

[`.github/workflows/publish.yml`](../.github/workflows/publish.yml) builds and pushes the image to GitHub Container Registry:

- **Triggers:** every push to `main`, and tags matching `v*`.
- **Image:** `ghcr.io/tcprescott/wizzrobe` (registry `ghcr.io`, name taken from `github.repository`).
- **Tag scheme** (`docker/metadata-action`):

| Event | Resulting tags |
|---|---|
| Push to `main` | `main`, `latest` |
| Push tag `v1.2.3` | `1.2.3`, `1.2`, `1` |

- Authenticates with the workflow `GITHUB_TOKEN` (`packages: write`); uses the GitHub Actions build cache (`cache-from`/`cache-to: type=gha`). No `platforms` are specified, so the image is built for the runner's platform (linux/amd64).

The compose file builds locally. To deploy a published image instead, replace `build: .` / `image: wizzrobe:latest` in the `wizzrobe` service with `image: ghcr.io/tcprescott/wizzrobe:<tag>`.

## Environment variables

Template: [`.env.example`](../.env.example). Three loading paths:

- **Docker:** compose passes `.env` to the app via `env_file` and uses it for its own `${…}` interpolation.
- **`./start.sh`:** sources `.env` with `set -a` ([`start.sh`](../start.sh)), so values containing spaces are preserved.
- **Aerich CLI / scripts:** [`migrations/tortoise_config.py`](../migrations/tortoise_config.py) calls `load_dotenv()`, so `poetry run aerich …` picks up `.env` without exporting.

Every boolean variable below uses one grammar (`env_flag` in `application/utils/environment.py`): true iff the stripped, lowercased value is `1`, `true`, `yes` or `on`. Every variable the application reads:

| Variable | Required | Default | Consumed by | Notes |
|---|---|---|---|---|
| `DB_HOST` | yes | — | `migrations/tortoise_config.py` | Set to `postgres` by compose. Missing → `ValueError` at import. |
| `DB_PORT` | yes | — | `migrations/tortoise_config.py` | Set to `5432` by compose. Same import-time check. |
| `DB_NAME` | yes | — | `migrations/tortoise_config.py`, `docker-compose.yml` | Compose defaults server-side `POSTGRES_DB` to `wizzrobe`; the app still needs `DB_NAME`. |
| `DB_USERNAME` | production: yes | `''` | `migrations/tortoise_config.py`, `application/utils/environment.py`, `docker-compose.yml` | Compose refuses to start when unset (`:?`); blank aborts a production boot. |
| `DB_PASSWORD` | production: yes | `''` | same as `DB_USERNAME` | Same enforcement. URL-encoded into the DSN, so special characters are safe. |
| `ENVIRONMENT` | no | `development` | `application/utils/environment.py`, `frontend.py`, `migrations/tortoise_config.py` | `production` (stripped, lowercased) enables the strict checks below. `./start.sh prod` force-exports `production` and `./start.sh mock` forces `development`, overriding `.env`. No-cache static headers only when exactly `development`. |
| `STORAGE_SECRET` | **yes, always** | — | `application/utils/environment.py`, `frontend.py`, `middleware/auth.py` | Signs the NiceGUI session holding auth state. Blank aborts startup in any environment; production also requires ≥32 characters. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `LOG_LEVEL` | no | `INFO` | `main.py` | Root level for the application logger; separate from uvicorn's `--log-level`, which `start.sh` pins to `info`. |
| `DISCORD_TOKEN` | yes, unless mock | — | `main.py`, `middleware/auth.py` | Bot token, also used by the OAuth API client. Unset → bot skipped with a warning and Discord features dead. |
| `DISCORD_CLIENT_ID` | yes, for real OAuth | — | `pages/auth.py` | Discord application client ID; derives `OAUTH_URL`. |
| `DISCORD_CLIENT_SECRET` | yes, for real OAuth | — | `pages/auth.py` | OAuth authorization-code exchange. |
| `BASE_URL` | no | `http://localhost:8000` | `application/utils/environment.py` | Public base URL (trailing `/` stripped) for deep links, and the fallback for `PLATFORM_HOST`. **Not** the source of the OAuth callback. Set it in production — a stale value bakes an unreachable host into printed equipment QR labels, which is why the label sheet names the host it encodes and warns when that is not the host you are browsing ([frontend.md](reference/frontend.md#encoded-host-check)). |
| `PLATFORM_HOST` | no | host of `BASE_URL` | `application/utils/environment.py`, `middleware/tenant.py` | Bare `host[:port]` serving the landing page, `/platform`, path-mode tenants and the shared OAuth callbacks; logged at startup. See [multitenancy.md](features/multitenancy.md#addressing-path-mode). |
| `HOST_OAUTH_MODE` | no | `local` | `application/utils/environment.py`, `pages/auth.py`, `application/services/oauth_handoff_service.py` | Custom-domain login strategy: `local` (a redirect URI per domain) or `handoff` (one platform URI plus a signed session handoff). See [authentication.md](reference/authentication.md#custom-domain-login-design-a-vs-design-b). |
| `TRUST_FORWARDED_HOST` | no | off | `application/utils/hostname.py` | Honor `X-Forwarded-Host`/`-Proto` for host/scheme resolution — **only** behind a trusted proxy. Required for host-mode routing when the proxy rewrites `Host`. |
| `REDIRECT_URL` | no | `{scheme}://{PLATFORM_HOST}/oauth/callback` | `pages/auth.py` | Discord callback, built per request from `PLATFORM_HOST` (not `BASE_URL`) with `https` forced off localhost. Host mode additionally needs each custom domain registered. Override only for non-standard callbacks. |
| `OAUTH_URL` | no | derived | `pages/auth.py` | Discord authorize URL built per request from `DISCORD_CLIENT_ID` + `REDIRECT_URL`, `scope=identify`. |
| `DISCORD_BOT_PERMISSIONS` | no | `268435456` (Manage Roles) | `application/services/discord/discord_link_service.py` | Permissions integer requested by the "Connect Discord server" flow; widen if the bot needs more than role application. |
| `DISCORD_CONNECT_REDIRECT_URL` | no | `{BASE_URL}/oauth/discord/connect/callback` | `application/services/discord/discord_link_service.py` | Bot-authorization callback, built per request. One URI serves every tenant; register it in the Discord Developer Portal. |
| `MOCK_DISCORD` | no | off | `application/utils/mocks/mock_discord.py` | Bypasses OAuth and stubs `DiscordService` — see [discord.md](features/discord.md#mock-mode). **Refused when `ENVIRONMENT=production`.** |
| _(randomizer API keys)_ | — | — | `application/services/seedgen_service.py` | **Not environment variables.** Each community supplies its own on Admin → Randomizer Keys. See [seed-generation.md](reference/seed-generation.md#per-tenant-credentials). |
| `MOCK_SEEDGEN` | no | off | `application/utils/mocks/mock_seedgen.py` | Short-circuits `SeedGenerationService.generate_seed` to a fake `mock.seedgen.local` permalink — **except `dk64r`**, which simulates its task queue instead (below). **Refused in production.** |
| `MOCK_DK64_SECONDS` | no | `20` | `application/utils/mocks/mock_dk64.py` | Wall-clock seconds a simulated DK64 roll takes, so the waiting UI can be exercised. Only read when `MOCK_SEEDGEN` is on; the test suite pins it to `0`. |
| `MOCK_DK64_OUTCOME` | no | `finished` | `application/utils/mocks/mock_dk64.py` | Ending the simulated DK64 task reaches: `finished`, `failed`, `http_error`, or `stuck` (never finishes, for the generation-timeout branch). |
| `MOCK_DK64_BROKEN_STAGE` | no | unset | `application/utils/mocks/mock_dk64.py` | Fails a pre-poll DK64 call instead: `convert` or `submit`. |
| `SENTRY_DSN` | no | `''` | `application/utils/sentry.py` | Enables Sentry error reporting; events tagged with `ENVIRONMENT` and the logged-in user. No-op when blank. |
| `SENTRY_TRACES_SAMPLE_RATE` | no | `0` | `application/utils/sentry.py` | Fraction (`0`–`1`) of requests traced for performance. Only read when `SENTRY_DSN` is set. |
| `TELEMETRY_ENABLED` | no | `true` | `application/utils/environment.py` | Runtime kill-switch for telemetry **capture**; reads and reports are unaffected. See [telemetry.md](features/telemetry.md). |
| `CHALLONGE_CLIENT_ID` | no | — | `application/services/challonge_service.py` | Challonge OAuth client ID. The integration counts as configured only when this and the secret are both set. |
| `CHALLONGE_CLIENT_SECRET` | no | — | `application/services/challonge_service.py` | Used for the service-account and per-player authorization-code exchanges. |
| `CHALLONGE_REDIRECT_URI` | no | `{BASE_URL}/challonge/oauth/callback` | `application/services/challonge_service.py` | Must match the URI registered with the Challonge OAuth app. Override only for non-standard callbacks. |
| `CHALLONGE_SCOPES` | no | `me tournaments:read matches:read matches:write participants:read` | `application/services/challonge_service.py` | Scopes for the shared **service-account** connection. Per-player linking always uses `me` only. |
| `MOCK_CHALLONGE` | no | off | `application/utils/mocks/mock_challonge.py` | Swaps in a stub Challonge client/connection for local dev. **Refused in production.** |
| `MOCK_CHALLONGE_IDENTITY` | no | `1` | `application/utils/clients/challonge_client.py` | Which canned mock identity the mock player-OAuth flow returns. Only read under `MOCK_CHALLONGE`. |
| `RACETIME_CLIENT_ID` | no | — | `application/services/racetime_service.py` | racetime.gg **identity-link** OAuth client ID (read scope). Distinct from the per-category race-room bot credentials on `RacetimeBot` rows. |
| `RACETIME_CLIENT_SECRET` | no | — | `application/services/racetime_service.py` | Used once per link for the code exchange, then discarded (no token stored). |
| `RACETIME_REDIRECT_URI` | no | `{BASE_URL}/racetime/oauth/callback` | `application/services/racetime_service.py` | Must match the URI registered with the racetime OAuth app. |
| `MOCK_RACETIME` | no | off | `application/utils/mocks/mock_racetime.py` | Fakes a verified racetime identity **and** drives the bot runtime against a scripted event-emitting fake. **Refused in production.** |
| `RACETIME_BOT_ENABLED` | no | off | `application/utils/environment.py` | Master switch for the racetime bot runtime (`racetimebot/`). Off → lifespan skips it, no outbound connections. On → one connection per active `RacetimeBot` category. |
| `MOCK_RACETIME_IDENTITY` | no | `1` | `application/utils/clients/racetime_client.py` | Which canned mock identity the mock link flow returns. Only read under `MOCK_RACETIME`. |
| `TWITCH_CLIENT_ID` | no | — | `application/services/twitch_service.py`, `application/services/service_health_service.py` | Twitch OAuth client ID. The account-link feature counts as configured only when this and the secret are both set. |
| `TWITCH_CLIENT_SECRET` | no | — | `application/services/twitch_service.py`, `application/services/service_health_service.py` | Used once per link for the code exchange, then discarded (no token stored). |
| `TWITCH_REDIRECT_URI` | no | `{BASE_URL}/twitch/oauth/callback` | `application/services/twitch_service.py` | Must match the URI registered with the Twitch app. |
| `MOCK_TWITCH` | no | off | `application/utils/mocks/mock_twitch.py` | Records a fake verified Twitch identity so link/unlink works without a real OAuth app. **Refused in production.** |
| `MOCK_TWITCH_IDENTITY` | no | `1` | `application/utils/clients/twitch_client.py` | Which canned mock identity the mock link flow returns. Only read under `MOCK_TWITCH`. |
| `SPEEDGAMING_SYNC_ENABLED` | no | off | `application/utils/environment.py` | Master switch for the SpeedGaming ETL sync worker. Off → no outbound polls. On → each active `SpeedGamingEventLink` is polled on its cadence and materialized into `Match` rows. |
| `MOCK_SPEEDGAMING` | no | off | `application/utils/clients/speedgaming_client.py` | Scripted fake returning canned episodes, so the ETL is exercisable without speedgaming.org. **Refused in production.** |
| `DISCORD_EVENTS_SYNC_ENABLED` | no | off | `application/utils/environment.py` | Master switch for the Discord Scheduled Events reconciler worker. Off → nothing runs on a timer; the admin **Discord Events** tab still reconciles on demand. |
| `SERVICE_HEALTH_ENABLED` | no | off | `application/utils/environment.py` | Master switch for the platform service-health probe loop (~2 min cadence, some probes reach external hosts). Off → `/platform` still probes on demand. |
| `SERVICE_HEALTH_ALERT_DM` | no | off | `application/utils/environment.py` | Opt in to DMing every super-admin on an unhealthy transition. Transitions always publish a `service_health.alert` event and capture to Sentry regardless. |
| `VAPID_PRIVATE_KEY` | no | — | `application/services/web_push_service.py` | Enables web push. Base64url raw 32-byte P-256 key from `scripts/generate_vapid_keys.py`. **Keep secret and stable** — rotating it invalidates every subscription. See [web-push.md](features/web-push.md). |
| `VAPID_SUBJECT` | no | `BASE_URL` when https | `application/services/web_push_service.py` | `mailto:` or `https:` contact sent to push services (RFC 8292). Without a usable value web push stays off even with a key. |
| `API_RATE_LIMIT_PER_MIN` | no | `120` | `api/rate_limit.py` | Per-client budget per minute, keyed by token (or client IP). Shared by the REST API and MCP, so one credential gets one budget. |
| `MCP_ENABLED` | no | on | `mcpserver/__init__.py` | Kill switch for the remote MCP server: off removes `/mcp`, its OAuth and discovery routes, and the lifespan hook. See [mcp-server.md](features/mcp-server.md). |
| `TRUST_PROXY_FORWARDED_FOR` | no | off | `api/rate_limit.py` | Rate limiter trusts `X-Forwarded-For` for the client IP — only behind a trusted proxy. |

See [reference/authentication.md](reference/authentication.md) for how the OAuth variables are wired into the login flow.

**Reverse proxy:** `/mcp` and `/.well-known/*` must be passed through unrewritten.
`BASE_URL` must be the public URL — it is the MCP resource identifier and the
OAuth issuer, both of which clients compare against what they requested.
MCP's DNS-rebinding protection is deliberately disabled because `Host` and TLS
terminate at the proxy; see [features/mcp-server.md](features/mcp-server.md).

### Startup refusals (fail-fast)

Three independent checks abort the process before it serves a request:

1. **[`migrations/tortoise_config.py`](../migrations/tortoise_config.py)** (import time): `DB_HOST`, `DB_PORT`, `DB_NAME` are always required; when `ENVIRONMENT=production`, blank `DB_USERNAME` or `DB_PASSWORD` raises `ValueError`.
2. **`validate_security_config()`** in `application/utils/environment.py` (called from `frontend.init()`): blank `STORAGE_SECRET` raises `RuntimeError` in every environment; in production a `STORAGE_SECRET` shorter than 32 characters, or a blank `DB_USERNAME`/`DB_PASSWORD`, also raises.
3. **`is_mock_discord()`** in `application/utils/mocks/mock_discord.py` (evaluated at import of `middleware/auth.py`): `MOCK_DISCORD` truthy while `ENVIRONMENT=production` raises `RuntimeError` — the mock layer is a complete authentication bypass and must never run in production.

## Startup behavior

Boot sequence (`main.py` lifespan, after the import-time checks above):

1. **Migrations auto-apply** — `init_db()` runs Aerich `upgrade()` against `./migrations`, then `Tortoise.init()`. Every boot applies any pending migrations; deploys need no manual `aerich upgrade` step.
2. **Discord bot** — `init_discord_bot()` starts the bot with `DISCORD_TOKEN` as a background task on the shared event loop. Skipped entirely under `MOCK_DISCORD`; without a token it logs a warning and continues.
3. **DM queue** — `discord_queue.start()` launches a single in-process worker that drains queued Discord notification coroutines sequentially.

Shutdown reverses this: the queue worker is cancelled (any still-queued DMs are counted, logged, and dropped), the bot connection closes, then DB connections close. See [architecture.md](architecture.md) for the full process model.

### Single worker — required

`start.sh prod` runs `uvicorn main:app --workers 1`. **Do not raise the worker count** — bots, queues, background loops, NiceGUI client state, the OAuth handoff nonce store and the per-match seed lock are all in-process singletons, and Aerich runs `upgrade()` at boot. Scale vertically; the full inventory and the phased `web`/`worker` split that would lift the constraint are in [scaling-roadmap.md](scaling-roadmap.md).

### `start.sh` modes

| | `./start.sh dev` | `./start.sh mock` | `./start.sh prod` |
|---|---|---|---|
| Reload | `--reload` | `--reload` | off |
| Host binding | uvicorn default (`127.0.0.1`) | uvicorn default (`127.0.0.1`) | `0.0.0.0` (required in a container) |
| Workers | n/a (reload implies one process) | n/a | `--workers 1` |
| Port | 8000 | 8000 | 8000 |
| Forced env | — | `ENVIRONMENT=development`, `MOCK_DISCORD`, `MOCK_CHALLONGE`, `MOCK_SEEDGEN` | `ENVIRONMENT=production` |

`mock` is the one-command offline dev loop — no Discord, Challonge or randomizer credentials needed. Any other argument prints an error and exits 1; the script `cd`s to its own directory first, so it can be started from anywhere.

## Operations

First deploy:

```bash
cp .env.example .env            # fill in credentials (see table above)
docker compose up -d
docker compose logs -f wizzrobe   # watch migrations apply and uvicorn start
```

- **Logs:** `docker compose logs -f wizzrobe` (uvicorn, bot, and queue output) and `docker compose logs -f postgres`.
- **Restart app only:** `docker compose restart wizzrobe` — the database keeps running.
- **Upgrade:**

  ```bash
  git pull
  docker compose build wizzrobe     # or: docker compose pull wizzrobe, if deploying a GHCR image
  docker compose up -d wizzrobe     # recreates the container; pending migrations apply on boot
  ```

- **psql access:** the DB is not published to the host; use `docker compose exec postgres psql -U wizzrobe -d wizzrobe` (names from your `.env`).
- **Manual migration commands** (rarely needed — boot does this automatically):

  ```bash
  docker compose exec wizzrobe poetry run aerich upgrade
  ```

  Schema and migration details: [reference/data-model.md](reference/data-model.md).

### Tenant and role bootstrap

The [multitenancy migration](reference/data-model.md#migrations) is additive: it backfills a `default` tenant and moves existing rows into it, so no manual step is needed at upgrade time. These scripts stand up the platform layer afterwards — all idempotent, and each target user must have logged in at least once so their `User` row exists:

```bash
# Grant yourself the global SUPER_ADMIN role (manages tenants at /platform):
docker compose exec wizzrobe poetry run python scripts/grant_super_admin.py <discord_id>

# Create additional communities going forward (also bootstraps their first admin):
docker compose exec wizzrobe poetry run python scripts/seed_tenant.py \
    --name "Wizzrobe Live" --slug wizzrobe [--guild-id <discord_guild_id>] \
    [--operator-discord-id <discord_id>]

# Grant STAFF within a specific tenant (defaults to the `default` tenant):
docker compose exec wizzrobe poetry run python scripts/grant_staff.py <discord_id> [tenant_slug]
```

`scripts/seed_dev.py` seeds two tenants of fixtures for local dev. See [features/multitenancy.md](features/multitenancy.md) for the addressing model and how a request resolves to a tenant.

### Backup and restore

Logical dumps are the recommended backup. `POSTGRES_USER`/`POSTGRES_DB` are already set inside the container, so these are copy-pasteable as-is:

```bash
# Backup (custom format)
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c' > wizzrobe-$(date +%F).dump

# Restore
docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < wizzrobe-YYYY-MM-DD.dump
```

A filesystem-level alternative is archiving the `postgres_data` volume (named `<project>_postgres_data`, e.g. `wizzrobe_postgres_data`) — only with the stack stopped (`docker compose stop`), never while postgres is running.

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
