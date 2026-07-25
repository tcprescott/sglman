# Escaping `--workers 1`

**Status:** proposed. Supersedes roadmap item 22 of
[2026-07-project-structure-review.md](../reviews/2026-07-project-structure-review.md)
("write the horizontal-scaling escape plan … assert single-worker at startup"),
which was recorded as a one-line recommendation and never written up.

**Headline verdict, and the change from the previous plan:** *`uvicorn --workers N`
is not a reachable target for this app and should stop being the goal.* NiceGUI
is single-worker by design — its bundled reference (`nicegui/llms.md`, "Architecture")
states it outright, its socket.io server is constructed with no cross-process
client manager (`nicegui/nicegui.py:50`), and a client's element tree lives in the
process that rendered its page. Adding workers to `main:app` does not scale this
app; it corrupts it.

What *is* reachable, and what this plan retargets to:

- **Target A — split the singletons out of the web process.** One image, two
  roles: `web` (NiceGUI + REST, still one worker) and `worker` (Discord gateway,
  racetime runtime, the five background loops, the DM queue). No new
  infrastructure. This is the whole win for the driver we actually have.
- **Target B — N web replicas.** Sticky sessions + Redis. Only after A, and only
  once one core is measurably saturated. Not recommended today.

---

## 1. What we're actually buying (be honest about the driver)

There is **no measured throughput problem.** The app is async, the DB is the
bottleneck long before the event loop is, and no profiling has been done. If the
justification for this work is "more requests per second," it is not justified.

The real drivers are **availability and blast radius**, and they are genuine:

1. **Every deploy drops the Discord gateway and every open browser websocket.**
   One process owns the FastAPI app, the py-cord gateway session, the racetime
   bot websockets, and the in-memory DM queue. Restarting to ship a UI copy
   change disconnects a live racetime room's bot and drops whatever DMs were
   still queued (`CoroutineQueue.stop()` counts, logs, and discards them).
2. **Blast radius.** An unhandled failure in a background loop, a seedgen
   upstream hang, or a bracket-layout hot loop shares one event loop with every
   user's websocket.
3. **Migrations run at boot** (`init_db()` → `aerich upgrade()`), so a restart is
   also a schema event. Coupling that to routine web deploys is avoidable.

Target A addresses 1 and 2 directly and makes 3 explicit. Target B addresses
none of them.

---

## 2. Verified inventory of process-global state

Every item below was read in the tree at the time of writing. "Class" is what
actually happens at N>1 — the distinction matters, because roughly half of these
are *duplicated work* (annoying, self-inflicted, sometimes expensive) and a few
are *silent incorrectness* (users see wrong behavior with no error anywhere).

| # | State | Location | What a second process does | Class |
|---|---|---|---|---|
| 1 | Discord gateway session | `main.py:46`, `application/services/discord/discord_service.py:36` | N identify sessions on one token; every interaction and every DM-button press is handled N times | Duplicates |
| 2 | racetime bot connections | `racetimebot/manager.py:152` | N websockets per category; each race command answered N times | Duplicates |
| 3 | Discord DM queue | `application/services/discord/discord_queue` (`utils/coroutine_queue.py`) | FIFO becomes per-process, so serialization is no longer global; queued DMs are dropped per-process on restart | Degrades |
| 4 | Event dispatch queue | `application/events/dispatch_queue` | as above, for webhook delivery + telemetry writes | Degrades |
| 5 | `event_bus` subscribers | `application/events/bus.py:33-34` | each process registers its own subscribers and sees only its own events — no duplicate deliveries, but no cross-process fan-out either | Degrades |
| 6 | `match_live` subscribers | `application/events/match_live.py:27` | **a match change committed in process A never refreshes a browser attached to process B** — the live schedule and bracket views silently go stale | **Breaks** |
| 7 | OAuth handoff nonce store | `application/services/oauth_handoff_service.py:52` | mint on A, claim lands on B → login fails outright; and single-use is only enforced per-process, so the replay defence weakens | **Breaks** (+ security) |
| 8 | Per-match seed lock | `application/services/match/match_schedule_service.py:182` | two processes roll a seed for the same match concurrently → duplicate upstream generation, last-writer-wins seed URL | **Breaks** |
| 9 | Five background loops | `race_room_worker`, `speedgaming_sync_worker`, `discord_event_worker`, `service_health_worker`, `volunteer_reminder` (all via `utils/background_loop.py`) | every loop runs in every process: N racetime rooms auto-opened, N SG syncs, N Discord-event reconciles, N health probe rounds. Only `volunteer_reminder` is protected, by its pre-send `reminder_sent_at` stamp | Duplicates |
| 10 | API rate limiter | `api/rate_limit.py:37` | effective limit becomes N × the configured `API_RATE_LIMIT_PER_MIN` | Degrades (security) |
| 11 | Service-health cache | `application/services/service_health_service.py` | N independent views of "current" health; each *transition into* unhealthy fires its own alert event + super-admin DM | Duplicates |
| 12 | Tenant resolution caches | `application/services/tenant_service.py:33-41` | `_clear_cache()` on write is process-local, so a tenant edit on A leaves B serving the stale slug/domain/theme until B happens to write | Degrades |
| 13 | NiceGUI element trees + socket.io | framework (`nicegui/nicegui.py:50`) | no cross-process client manager; a client's websocket **must** reach the process that rendered its page | **Breaks** |
| 14 | `app.storage.user` | NiceGUI `FilePersistentDict` (`.nicegui/storage-user-*.json`) | per-process in-memory dict flushed to a shared file; interleaved writes lose session state. **Has a supported fix** — see §4 | **Breaks** (fixable) |
| 15 | Aerich `upgrade()` at boot | `main.py` `init_db()` | two processes racing the same migration; Aerich has no locking | **Breaks** |
| 16 | `_warned_hosts` | `middleware/tenant.py:78` | N× the rate-limited unknown-host warning | Noise |

Items 6, 7, 8, 13, 14 and 15 are why "just bump the worker count and see" is not
a safe experiment even in staging with real data.

### What changed since the previous plan was recorded

The 2026-07 review counted "six in-process singletons." There are now sixteen,
but the picture improved in two ways that make this cheaper than it looks:

- **The scaffolding got unified.** `BackgroundLoop` (item 9) and `CoroutineQueue`
  (items 3–4) replaced five and two hand-rolled copies respectively. There is now
  exactly one place to hang "only run this in the process that owns it."
- **NiceGUI 3.12 ships a Redis storage backend** (`NICEGUI_REDIS_URL` →
  `RedisPersistentDict`, `nicegui/storage.py:78-96`), which the review predated.
  Item 14 is now a config line rather than a fork of the framework.

Two of the new singletons are the dangerous kind: the OAuth handoff nonce store
(item 7) and the seed lock (item 8) both encode "one process" into a
*correctness* guarantee, not just a performance assumption. Item 7 already
documents this in its own module docstring; item 8 does not.

---

## 3. Target A — split web from worker (recommended)

One Docker image, two roles chosen by env var, both started from `start.sh`.

```
web    role: FastAPI + NiceGUI + REST + tenant caches.        --workers 1
worker role: Discord gateway, racetime runtime, the five      no HTTP server
             background loops, the DM queue, migrations.
```

Ownership after the split:

| Item | web | worker |
|---|---|---|
| 1, 2, 9, 11 (gateway, racetime, loops, health probes) | — | ✅ owns |
| 3 (DM queue) | enqueues → must cross the boundary | ✅ drains |
| 6 (`match_live`) | subscribes | publishes → must cross the boundary |
| 4, 5 (`event_bus` + dispatch) | own instance | own instance |
| 7, 8, 10, 12, 13, 14 | web-only, unchanged | n/a |
| 15 (migrations) | skips | ✅ runs, web waits |

### The one new primitive: Postgres `LISTEN`/`NOTIFY`

Two things must now cross a process boundary — a `match_live` publish from a
worker-side commit (item 6) and a DM enqueued by a web request (item 3). Both are
"fire a small nudge, never block, tolerate loss."

Use Postgres `LISTEN`/`NOTIFY` on a dedicated asyncpg connection rather than
adding Redis. We already run Postgres; asyncpg exposes `add_listener` directly;
payloads here are tiny (`match_id`, `change_type`). The shape:

- `match_live.publish()` additionally issues `NOTIFY wizzrobe_match_live, '<json>'`.
- Each process holds one long-lived listener connection and re-publishes what it
  receives into its own local `_subscribers` — so `theme/realtime.py` and
  `theme/brackets/live.py` need no changes at all.
- The same seam serves `event_bus` if cross-process domain events are ever
  wanted. They are not needed for Target A: each process publishing its own
  events to its own subscribers is correct, not lossy, as long as the *webhook
  and telemetry subscribers are registered in both roles*.

**Caveat to design around:** `NOTIFY` payloads are capped at 8000 bytes and are
delivered on commit. Keep the payload to identifiers — never a serialized model.
The listener connection must be a dedicated `asyncpg.connect()`, not a
Tortoise-pooled connection, because pooled connections rotate.

### The safety net: advisory-lock leader election

Review item 22 asked to "fail fast if `workers>1`." That cannot be implemented
as written — a uvicorn worker child cannot read its own worker count. The
implementable equivalent, which also protects against a misconfigured second
`worker` replica:

- On worker-role startup, take `pg_try_advisory_lock(<constant>)` on a dedicated
  long-lived asyncpg connection (session-scoped locks are released when the
  connection closes, which is exactly the failover behavior we want).
- Lock acquired → start the gateway, the racetime runtime, and the five loops.
- Lock refused → log loudly and run nothing; do not exit, so the container stays
  up as a warm standby that takes over when the leader dies.

This is worth doing **even without the split**, as a standalone guard: it makes
"someone raised the worker count" a loud, correct degradation instead of
duplicate DMs and duplicate racetime rooms.

### Loose ends the split creates

- **Migrations.** Assign `aerich upgrade()` to the worker role only; web waits
  for the schema (poll, or an init container). Two processes racing Aerich is
  item 15 and is a real corruption risk, not a theoretical one.
- **Healthchecks.** The Docker/compose healthcheck curls `/api/health`, which the
  worker role will not serve. Give the worker its own liveness signal (a
  heartbeat row, or a minimal HTTP listener) rather than leaving it unmonitored.
- **DB pool.** Tortoise defaults to `maxsize=5` per process; two roles double the
  connection count. Make it a config knob while touching this.
- **`tenant_scope`.** Already correct — the worker role's paths all wrap scoped
  data in `tenant_scope(...)` today (that discipline was built for the existing
  background loops), so nothing new is required here.
- **`main.py` lifespan** currently starts everything unconditionally per feature
  flag. It grows one branch on role; keep the flag checks where they are.

---

## 4. Target B — N web replicas (defer)

Only after A, and only with a measurement showing one core saturated. What it
would take:

- **Sticky sessions** at the load balancer, keyed on the NiceGUI client cookie.
  Non-negotiable: item 13 has no software fix short of a socket.io Redis manager,
  which NiceGUI does not wire up.
- **`NICEGUI_REDIS_URL`** for `app.storage.user` / `general` / `tab` (item 14).
- **Shared stores** for items 7 (nonce), 8 (seed lock), 10 (rate limiter) — Redis
  is the natural fit for all three; item 8 could alternatively become a Postgres
  advisory lock keyed on `match_id`, which avoids Redis entirely.
- **Item 12** (tenant cache invalidation) piggybacks on the §3 `NOTIFY` channel.
- Item 6 is already solved by A.

That is a Redis dependency plus LB configuration to buy throughput we have no
evidence we need. **Recommendation: do not build B. Revisit only with a profile.**

---

## 5. Phasing

**Phase 0 — make the constraint safe and honest (do this regardless).**
1. Advisory-lock leader election guarding the gateway, the racetime runtime, and
   the five `BackgroundLoop`s (§3). Standalone value; no split required.
2. Document item 8 (the seed lock) as a single-process correctness dependency, as
   item 7 already documents itself.
3. Replace the "Scale vertically" line in [deployment.md](../deployment.md) and
   the paragraph in [architecture.md](../architecture.md) with a pointer here.

**Phase 1 — cross-process nudge.**
4. `LISTEN`/`NOTIFY` transport behind `match_live.publish` / subscribe, with the
   listener connection owned by the lifespan. Behind an env switch, default off,
   so it is a no-op in the current single-process deployment.
5. Tests: publish in one connection, assert delivery to a subscriber registered
   against another.

**Phase 2 — the split.**
6. `ROLE=web|worker` branch in `main.py`'s lifespan + `start.sh` + compose.
7. Move migrations to the worker role; make web wait.
8. Worker-role liveness; DB pool knob.
9. Route the DM queue enqueue across the boundary (or accept that web-side DM
   sends stay in the web process — decide, don't drift).

**Phase 3 — only on evidence.** Target B.

---

## 6. Open questions

- **Is availability the actual goal, or is this pre-emptive?** Phase 0 is worth
  doing either way; Phases 1–2 are only worth it if web-tier deploys dropping the
  Discord gateway is a felt problem.
- **DM queue after the split (step 9).** Enqueue-across-the-boundary is the clean
  answer but adds a durable-queue question we have otherwise avoided. Letting the
  web role keep its own DM queue is simpler and keeps ordering per-process only.
  Unresolved.
- **Does the worker role need `MOCK_*` parity** for local dev, or does dev keep
  running one combined process? Recommend: dev stays combined
  (`ROLE=all`, the current behavior, and the default).
