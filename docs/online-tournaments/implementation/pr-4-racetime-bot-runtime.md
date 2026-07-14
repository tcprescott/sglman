# PR 4 — `racetimebot/` skeleton + `MOCK_RACETIME` + bot health

> Feature 5. Roadmap phase 3 (runtime half). Stand up the connection and prove the
> single-worker / long-lived-websocket architecture **before** wiring business logic.
>
> **Status: implemented.** `racetimebot/` package (peer of `discordbot/`,
> presentation layer): `RacetimeBotManager` (lifespan-managed singleton, one
> `CategoryConnection` per active bot, re-adopts open rooms on boot, `/platform`
> restart), `CategoryConnection` (health writes via `RacetimeBotService` acting as
> the system user — connect→`connected`, auth-reject→`error`+stop, transient→`error`
> +exponential backoff capped 5 min, liveness heartbeat → `last_checked_at`),
> `RaceHandler` (tenant routing via unscoped slug lookup + `tenant_scope`, crash
> containment) with a status-only `RoomStatusLifecycle` (the room-lifecycle PR
> injects the richer service). Transport seam: `RealRacetimeTransport` (real
> `client_credentials` OAuth token fetch + liveness loop) and a scripted
> `MockRacetimeTransport`. `RACETIME_BOT_ENABLED` master switch; `MOCK_RACETIME`
> drives the scripted fake (production-refused). Health audit actions
> (`racetime_bot.connected/disconnected/error/restarted`, tenant=NULL, audit-only).
> `/platform` shows per-bot health + a Restart button. Runtime tests cover
> connect/auth-fail/transient+reconnect/heartbeat, scripted lifecycle, tenant
> routing, re-adoption, and crash containment.

**Goal:** a lifespan-managed racetime connection per authorized category that
tracks room state and its own health, fully mockable.

**Depends on:** PR 3 (models). **Unblocks:** PR 5 (health page), PR 6 (lifecycle).

## Deliverables

- **`racetimebot/` package** (peer of `discordbot/`; handlers are presentation —
  call services, never import repositories). `init_racetime_bot()` started in
  `main.py` lifespan; one connection per active `RacetimeBot` category; a
  `RaceHandler` per room that reacts to state transitions.
- **`MOCK_RACETIME`**: a **scripted event-emitting fake** (not a no-op skip) that
  drives the full room lifecycle for dev/tests; **refused under
  `ENVIRONMENT=production`** (it can fabricate finishes). Env-gated by the
  `RacetimeBot` rows; a `RACETIME_BOT_ENABLED` master switch.
- **Bot health monitoring** ([decision](../README.md#decisions-log)): the connection
  loop writes `RacetimeBot.status` — success → `connected` (+`last_connected_at`);
  **auth error (401) → `auth_failed`, stop retrying**; transient → `connection_error`
  with **exponential backoff capped ~5 min**; manual stop → `disconnected`. A
  **liveness heartbeat** refreshes `last_checked_at` so a wedged-without-error task
  is detectable. Publish `racetime_bot.*` events on transitions.
- **Reconnect/re-attach**: on boot/reconnect, re-adopt open `RacetimeRoom` rows so a
  redeploy doesn't orphan live rooms ([gap 5.2](../gap-analysis.md)).
- **`/platform` status board + restart action** (mirror sahabot2 `restart_bot`).
- **Tenant routing**: every inbound event resolves tenant via the unscoped
  `RacetimeRoom.slug` → `Match` → tenant lookup, wrapped in `tenant_scope`. Acts as
  the **system user**.
- Env docs; tests driving the mock through connect/auth-fail/transient/heartbeat.

## Decisions that apply

Bot health as first-class state; scripted `MOCK_RACETIME`; system-user actor; 1:1
room→tenant routing.

## Reference implementations

- **sahabot2**: `racetime/client.py` (connection loop, `update_bot_status` /
  `record_connection_failure`, auth-vs-transient handling, capped exponential
  backoff, reauthorize task; note it explicitly disables auto-`refresh_races` and
  joins rooms only on demand — do the same).
- **sglman**: `main.py` (`init_discord_bot` lifespan task pattern, done-callback
  error surfacing), `application/tenant_context.py` (`tenant_scope`),
  `application/events/`.

## Acceptance criteria

- Under `MOCK_RACETIME`, the bot "connects," a scripted room transitions
  open→in_progress→finished, and `RacetimeBot.status` reflects connect/auth-fail/
  transient correctly. Killing/restarting the process re-adopts an open room. A
  crashing handler doesn't take down the bot or siblings.

## Out of scope

Auto-open scheduling, seed attach, result capture (PR 6). This PR connects and
tracks state; it does not create rooms for real matches yet.
