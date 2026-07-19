# PR 5 — Platform external-service health page

> Platform observability. Resolves [gap analysis §5](../gap-analysis.md). Can land
> any time after PR 4 (for the racetime probe); other probes are independent.
>
> **Status: implemented (PR 5).** `ServiceHealthService` (probe registry +
> in-memory cache + alert-on-transition) and `service_health_worker`
> (`SERVICE_HEALTH_ENABLED`, off by default); `ServiceStatus` = `healthy /
> degraded / credential_warning / down / unknown`; probes for PostgreSQL, Discord
> bot + OAuth, racetime bots (reads `RacetimeBot.status`), SpeedGaming, Challonge
> (reachability + token expiry across tenants via an unscoped repo read), Twitch
> OAuth, seed-gen upstreams, web-push/VAPID, and Sentry. Alert path publishes
> `EventType.SERVICE_HEALTH_ALERT` + Sentry capture + optional super-admin DM
> (`SERVICE_HEALTH_ALERT_DM`). Full board on `/platform`; tenant STAFF read-only
> subset on the admin **Service Health** tab (`tenant_subset`). No persistence
> model / migration (computed-and-cached). See [current-state.md](../../current-state.md)
> and [services.md](../../reference/services.md).

**Goal:** a SUPER_ADMIN `/platform` board showing the live health of every external
dependency, so an admin learns something is down before it breaks a race day.

**Depends on:** PR 4 (soft — for the racetime-bot probe). **Unblocks:** nothing.

## Deliverables

- **Probe registry**: each dependency registers an async
  `check() → {status, message, checked_at}`; a background worker runs them on a
  cadence; the page can force an on-demand refresh.
- **Computed-and-cached** ([decision](../README.md#decisions-log)): latest result
  per dependency in an **in-memory cache** (safe under one worker); re-probe on
  restart. **No persistence model.** (Exception: `RacetimeBot.status` is already
  persisted on its row — the racetime probe just reads it.)
- **Probes**: PostgreSQL; Discord bot + OAuth; racetime bots (read
  `RacetimeBot.status`); SpeedGaming API; Challonge (reachability **+ token
  validity/expiry**); Twitch OAuth; seed-gen upstreams (alttpr.com,
  ootrandomizer.com, maprando.com); web-push/VAPID config; Sentry.
- **Status model**: `healthy / degraded / down / unknown`, plus a distinct
  **credential-warning** signal (expiring Challonge token, racetime `auth_failed`).
- **Alerting**: transition to `down`/`auth_failed` publishes an event → Sentry +
  webhooks + optional platform-admin DM.
- **Scope**: full board SUPER_ADMIN-only; tenant STAFF get a **read-only subset**
  for services their tenant depends on (authorized racetime bots, their Challonge
  connection).

## Decisions that apply

Computed-and-cached (no persistence); platform-scoped with a per-tenant read-only
subset; alert on down/auth-fail.

## Reference implementations

- **wizzrobe**: the existing `/health` endpoint (DB round-trip) as the Postgres probe
  seed; `application/services/challonge_service.py` (token expiry); Sentry util;
  `pages/platform.py`; `application/events/` for alert publishing.
- **sahabot2**: `RacetimeBot.status` / `is_healthy()` as the racetime probe input.

## Acceptance criteria

- The board renders each dependency with a status; forcing a Challonge outage (or a
  near-expiry token) shows `down`/credential-warning and fires an alert; a tenant
  STAFF sees only their subset. Verify via `ui-validation`.

## Out of scope

Historical trends / charts (would need the persisted model — deferred). Auto-
remediation.
