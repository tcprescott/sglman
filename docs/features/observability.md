# Observability: Sentry and runtime log levels

_How errors and logs leave the process, what context they carry, and how a
super-admin turns a module's logging up mid-event. Part of the
[documentation index](../README.md). Env vars are in the
[deployment table](../deployment.md#environment-variables)._

## What reaches Sentry

[`application/utils/sentry.py`](../../application/utils/sentry.py) initializes the
SDK once, before the FastAPI app is built, and only when `SENTRY_DSN` is set.

| Signal | How it gets there | Notes |
|---|---|---|
| **Error events** | any `logger.error` / `logger.exception`, plus unhandled exceptions the FastAPI/Starlette integration sees | `LoggingIntegration(event_level=ERROR)`. A `logger.warning` is a breadcrumb only, so a failure someone relied on must log at ERROR. |
| **Breadcrumbs** | every INFO+ record before an event | Attached to the next event in the same scope. |
| **Sentry Logs** | every INFO+ record (`SENTRY_LOGS_LEVEL`) | Searchable alongside events. `uvicorn.access`, `httpx` and `httpcore` are excluded (one line per request). DEBUG/TRACE never ship, whatever a logger is set to. |
| **Traces** | `SENTRY_TRACES_SAMPLE_RATE`, default `0.1` in production and `0` elsewhere | Slow pages, slow DB and outbound HTTP calls. |
| **Health alerts** | `ServiceHealthService._alert` → `capture_message` | Fingerprinted on probe + status, tagged `health_probe` / `health_status`, so one outage is one issue. |

Every event carries `environment`, `release` (`SENTRY_RELEASE`, else
`wizzrobe@<GIT_SHA[:12]>`; `publish.yml` bakes `GIT_SHA` into the image), and
`send_default_pii=False`; `before_send` scrubs auth headers and cookies and drops
the NiceGUI timer-teardown race.

## Context on every event

`before_send` adds two things the SDK can't know:

- **`tenant_id` tag** from `get_current_tenant_id()`. It's set for HTTP requests
  (`TenantMiddleware`), UI handlers (the client stash), and anything inside
  `tenant_scope(...)` — workers, queues, bot handlers. Logs get the same value as
  a `tenant_id` attribute (`before_send_log`).
- **User**, when the event has none. `AuthMiddleware` sets the user on the HTTP
  request's scope, but a button click arrives over the websocket after that
  scope is gone; the hook falls back to `app.storage.user`.

Surfaces that run outside a request add their own tags with
`sentry_tags(**tags)`, a context manager that forks the scope so the tags vanish
on exit (`tag_current_scope` adds one learned mid-block):

| Surface | Tags |
|---|---|
| `BackgroundLoop` (every worker tick) | `worker` |
| `for_each_tenant_scoped` (per item) | `work_item`, plus `tenant_id` (the failure is logged inside the tenant scope) |
| `CoroutineQueue` (Discord DM queue, event dispatch) | `queue`, `queued_call` (the inner call, e.g. `_run_in_tenant_scope(send_dm)`) |
| Discord DM buttons (`discordbot/_ack_common.py`) | `discord_interaction`, `discord_custom_id`, `discord_user_id`, `tenant_id` |
| racetime room handler | `racetime_room`, `racetime_category`, `tenant_id` |
| MCP tools | `mcp_tool`, `tenant_slug` |
| NiceGUI 500 page | `error_id` (the UUID shown to the user) |

## Failures that log at ERROR

These used to log at WARNING or not at all, so Sentry never heard about them.

| Failure | Where |
|---|---|
| Async seed roll failed, abandoned, or finished with no match | `seed_roll_service.py`, `provider_task_service.py` |
| Seed generation failed after retries | `match_schedule_service.py` |
| racetime room refused / not recorded after opening | `race_room_service.py` |
| racetime bot auth failure (bot stops until restart) | `racetimebot/connection.py` |
| SpeedGaming fetch failed | `speedgaming_etl_service.py` |
| Matcherino check-in sync failed | `check_in_sync_worker.py` |
| Challonge post-push re-sync failed | `challonge_service.py` |
| Discord DM not sent because the bot is down, or crashed on our side | `discord_service.send_dm` |
| Discord guild/event op crashed on our side (a Discord refusal stays WARNING) | `discord_guild_ops.log_discord_failure` |
| Series game unresolved with no match | `_bracket/series.py` |
| Invalid `VAPID_PRIVATE_KEY` | `web_push_service.py` |

Deliberately left at WARNING: a DM a user has blocked (`Forbidden`), a seed
provider attempt that will be retried, a racetime reconnect, a community's
webhook endpoint failing (the delivery row is what staff act on), web-push
endpoint errors.

## Runtime log levels (`/platform` → Logging)

A super-admin can set any stdlib logger to `TRACE`, `DEBUG`, `INFO`, `WARNING`,
`ERROR` or `CRITICAL` without a redeploy. The table lists the loggers worth
reaching for (`application`, `application.services.discord`, `racetimebot`,
`discordbot`, `tortoise`, …) with what each covers, the stored level, and the
level it actually runs at (inherited from a parent when unset); **Other logger**
takes any dotted name.

- A change applies to the live process at once and is stored as a
  [`LogLevelOverride`](../reference/data-model.md#logleveloverride) row, which
  `main.py` reapplies at startup, so a restart mid-event keeps it. A row that no
  longer parses is skipped with an ERROR rather than blocking boot.
- **Reset** deletes the row; the logger goes back to inheriting (root goes back
  to `LOG_LEVEL`).
- Each change is audited (`log_level.set` / `log_level.cleared`, platform-level,
  never webhooked) and logged at WARNING so it's visible in Sentry Logs.
- Levels gate what a logger *emits*. DEBUG and TRACE land in the container log
  only; Sentry Logs stays at INFO+. `TRACE` is level 5, registered at startup
  (`register_trace_level`), so `LOG_LEVEL=TRACE` also works.
- Not feature-flagged: it's a platform surface gated on `SUPER_ADMIN`.

Code: [`application/utils/log_levels.py`](../../application/utils/log_levels.py)
(levels, known loggers, applying to the tree),
[`LogLevelService`](../reference/services.md#log_level_servicepy--loglevelservice),
[`pages/platform_logging.py`](../../pages/platform_logging.py).

## During the event

1. Filter Sentry by `release` to see what a deploy changed, and by `tenant_id`
   or `worker` to narrow a spike.
2. For a quiet failure, search Sentry Logs around the time for the tenant; the
   INFO trail is there even when nothing errored.
3. Need more detail from one module? Set it to DEBUG on `/platform`, read the
   container log, then Reset. Don't leave `tortoise` at DEBUG: it logs every
   query.
