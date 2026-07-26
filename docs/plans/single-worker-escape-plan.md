# Escaping `--workers 1`

**Status:** proposed. Supersedes roadmap item 22 of
[2026-07-project-structure-review.md](../reviews/2026-07-project-structure-review.md)
("write the horizontal-scaling escape plan … assert single-worker at startup"),
which was recorded as a one-line recommendation and never written up.

**Goal:** serve **at least 500 concurrent websocket connections** (§1 — measured,
not estimated).

> **Status update.** Phase 1's first step — lazy tab rendering — **is shipped**,
> and on the measured workload **the 500-connection target is already met on a
> single worker**: 500/500 tabs connected and held, against 205/500 before. See
> §1.5. The remaining phases are no longer required to hit 500; they are about
> headroom, faster arrival, and availability. Each now has its own plan doc:
>
> | Next | Plan |
> |---|---|
> | Finish the render-cost work (match table, N+1, regression guard) | [render-cost-plan.md](render-cost-plan.md) |
> | Make the single-worker constraint fail loudly, not silently | [singleton-ownership-plan.md](singleton-ownership-plan.md) |
> | Split `web` from `worker` (availability) | [web-worker-split-plan.md](web-worker-split-plan.md) |
> | Run N web replicas (headroom) | [web-replicas-plan.md](web-replicas-plan.md) |

**Headline verdict 1 — the mechanism.** *`uvicorn --workers N` is not a reachable
target for this app and should stop being the goal.* NiceGUI is single-worker by
design — its bundled reference (`nicegui/llms.md`, "Architecture") states it
outright, its socket.io server is constructed with no cross-process client
manager (`nicegui/nicegui.py:50`), and a client's element tree lives in the
process that rendered its page. Adding workers to `main:app` does not scale this
app; it corrupts it. More capacity means more *replicas*, behind sticky sessions.

**Headline verdict 2 — the bottleneck.** Holding 500 websockets is cheap (~3 % of
a core for ~195 sockets, ~3 MB each). **Admitting** them is not: one page render
burns ~250 ms of event-loop CPU, capping a worker at **~4 new tabs/second**. A
measured 500-tab ramp connected only **205**. The database was never contended —
the ceiling is CPU spent building NiceGUI element trees, **~47 % of it rendering
the 8 of 9 home tabs the user cannot see**.

So the path to 500 is, in order:

- **Step 1 — cut render cost (no infrastructure).** Lazy tab rendering, then the
  Schedule tab's element count and its 377-queries-per-render N+1. This is the
  step change, and it multiplies with everything after it.
- **Target A — split the singletons out of the web process.** One image, two
  roles: `web` (NiceGUI + REST, still one worker) and `worker` (Discord gateway,
  racetime runtime, the five background loops, the DM queue). No new
  infrastructure. Buys availability, not capacity.
- **Target B — N web replicas.** Sticky sessions + Redis. The only way to add
  cores, and now a *required* part of the capacity plan rather than a deferred
  nice-to-have — but worth far less before Step 1 than after it.

---

## 1. The capacity target: 500 concurrent websockets

**The goal is 500 concurrent connections.** NiceGUI holds one persistent
socket.io websocket per open browser tab, so that is 500 open tabs. The app was
measured against that target rather than reasoned about; §1.1 is the evidence.

**Verdict: holding 500 websockets is not the problem. Admitting them is.**

### 1.1 Measurements

Method: seeded dev database, single no-reload worker (`uvicorn main:app
--workers 1`, `MOCK_DISCORD`), driver opening real socket.io websockets with the
same handshake `nicegui.js` performs (one authenticated tenant-home tab per
virtual client). Driver and server shared a host, so CPU figures are
conservative. Target page: the staff tenant home (`/t/default/`).

| Measurement | Result |
|---|---|
| Page render, idle, sequential | **~200 ms wall, ~246 ms CPU** per render |
| CPU vs wall over 20 sequential renders | 5.22 s wall / **4.93 s server CPU — 94 % CPU-bound** |
| DB connections used, throughout | **6** (pool cap 5 + 1); `pg_active` never above 1 |
| 25 tabs arriving together | ~2/25 connect; server logs `Response for / not ready after 3.0 seconds` |
| 500 tabs, 0.3 s ramp (150 s) | **205/500 connected**; 36 dropped during a 60 s hold |
| Render latency under that ramp | p50 1214 ms, p95 2898 ms, max 3591 ms |
| CPU during ramp | pegged at **~110 % of one core** |
| CPU while merely *holding* ~195 sockets | **2–4 % of one core** |
| RSS | 145 MB idle → 767 MB at ~200 sockets (**~3 MB per connected tab**) |

### 1.2 What that means

- **Idle websockets are cheap.** ~195 held sockets cost 2–4 % of a core. 500
  idle tabs extrapolates to well under 10 % of one core. Sockets are not the
  constraint; file descriptors (`ulimit -n`) are not either.
- **Memory is a budget item, not a wall.** ~3 MB per tab ⇒ 500 tabs ≈ 1.6 GB
  resident. Size the container accordingly.
- **Admission is the wall.** One page render costs ~250 ms of *event-loop CPU*,
  so a single worker admits **~4 tabs per second**. 500 tabs arriving over a
  two-minute window is ~4.2/s — exactly at the cliff, which is why only 41 %
  connected. Renders queue behind each other, exceed NiceGUI's 3-second
  page-response timeout, and the client is torn down before its socket attaches.
- **The database is not the bottleneck.** `maxsize=5` was the prime suspect; it
  was never contended (`pg_active` ≤ 1). Raising the pool would buy nothing
  today. *(Still worth making configurable — but as hygiene, not as capacity.)*

This matters because 500 concurrent tabs is not a slow trickle. The realistic
arrival pattern for this app is a **crowd**: a race goes live, a bracket is
published, a Discord announcement fires. That is precisely the pattern the
current admission rate cannot serve.

### 1.3 Where the 250 ms goes

In-process `cProfile` over 10 renders of the staff tenant home:

- **`_render_tab_panels` — 2.32 s of 4.92 s (≈47 %).** `theme/base.py:453` loops
  `for tab in self.tabs` and **awaits every tab's content eagerly**. The staff
  home has **9 tabs**; the user sees one. The Profile tab alone
  (`player_edit_info.render_edit_info_tab`) costs 0.74 s across the batch, fully
  paid on every page load by every user whether or not they open it.
- **377 database queries per single page render** (3771 `queryset._execute` calls
  over 10 renders). Locally that is only ~90 ms because the DB is on loopback; on
  a network-attached database each round trip is charged again. This is an N+1
  problem spread across the eagerly-rendered tabs.
- **~488 NiceGUI elements per render**, and `inspect.signature` called ~1509
  times per render (0.72 s across the batch, ≈15 %) via NiceGUI's
  `expects_arguments` on every event-handler registration. This is a direct
  function of element count — the only way down is to build fewer elements.

### 1.4 What this changes about the plan

The ordering below is now driven by measurement, not by the availability
argument in §2:

1. **Lazy tab rendering is the single highest-leverage change** and it is a
   presentation-layer fix requiring none of this document's infrastructure.
   Rendering only the active panel, and building others on first switch, removes
   roughly half the render cost and a large share of the 377 queries. Every
   replica benefits, so it multiplies with anything done later.
2. **Then reduce the remaining render cost** (the match table's element count and
   the N+1 queries behind the Schedule tab).
3. **Then add processes.** Extra cores are the only way past a Python event
   loop's single-threaded ceiling — but adding a second replica only doubles
   admission (~4/s → ~8/s), whereas step 1 is a step change on every replica.
   Doing step 3 first buys the least improvement for the most infrastructure.

Concretely: at ~4 renders/s the target is out of reach; at a plausible post-fix
~12–15 renders/s a single worker admits 500 tabs in ~35–40 s, and two replicas
comfortably absorb a crowd. **Target B (§5) is therefore no longer "do not
build" — it is the last step of a capacity plan, not the first.**

### 1.5 Result after lazy tab rendering (shipped)

`BaseLayout._render_tab_panels` now creates every panel container up front but
builds a tab's **content** only when it is first shown. Same harness, same
seeded data, same single no-reload worker:

| | Before | After |
|---|---|---|
| Tenant home (9 tabs), CPU/render | 289 ms | **132 ms** (−54 %) |
| Admin (24 tabs), CPU/render | 566 ms | **116 ms** (−79 %) |
| 500 tabs @ 0.3 s ramp | 205/500 connected | **500/500 connected** |
| …still connected after 60 s hold | 169 | **500** |
| Render latency under that ramp | p50 1214 ms / p95 2898 ms | **p50 81 ms / p95 485 ms** |
| RSS at end of run | 767 MB @ ~200 sockets | **561 MB @ 500 sockets** |
| CPU holding the sockets | 2–4 % of a core @ ~195 | **~7 % of a core @ 500** |

Two things worth noting beyond the headline:

- **Memory improved as much as CPU.** Per-connection cost fell from ~3 MB to
  ~0.85 MB, because a client now holds one panel's element tree instead of nine.
  500 tabs fit in ~560 MB rather than the ~1.6 GB projected in §1.2.
- **The admin page gained most** (−79 %), which matters because staff sit on it
  during an event, and it is the page most likely to be open in a second tab.

**Since then**, a second fix (the match table was loading three times per page —
see [render-cost-plan.md](render-cost-plan.md) R1) took the home page to **74 ms
CPU and 26 queries** per render. The measured end-to-end ceiling is now
**~10 tabs/second**: 500 tabs connect with zero failures at 3.3/s, 6.7/s and
10/s, and fall over at 16/s. Before this work, 500 tabs failed at 3.3/s.

---

## 2. The other driver: availability and blast radius

Independently of capacity, the single-process model has costs:

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

## 3. Verified inventory of process-global state

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

## 4. Target A — split web from worker

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

## 5. Target B — N web replicas

One core **is** saturated at the 500-tab target (§1.1), so this is now required —
but sequence it after Step 1, because a replica multiplies whatever per-render
cost it inherits. Two replicas of today's app admit ~8 tabs/s; two replicas after
Step 1 admit ~25–30/s. Same infrastructure, very different outcome.

What it takes:

- **Sticky sessions** at the load balancer, keyed on the NiceGUI client cookie.
  Non-negotiable: item 13 has no software fix short of a socket.io Redis manager,
  which NiceGUI does not wire up.
- **`NICEGUI_REDIS_URL`** for `app.storage.user` / `general` / `tab` (item 14).
- **Shared stores** for items 7 (nonce), 8 (seed lock), 10 (rate limiter) — Redis
  is the natural fit for all three; item 8 could alternatively become a Postgres
  advisory lock keyed on `match_id`, which avoids Redis entirely.
- **Item 12** (tenant cache invalidation) piggybacks on the §4 `NOTIFY` channel.
- Item 6 is already solved by A.

**Recommendation:** build B, but not first. Re-measure after Step 1 and size the
replica count from the observed renders/second rather than from this estimate.

---

## 6. Phasing

Ordered by capacity-per-unit-effort, which puts the presentation-layer work
first and the infrastructure last. Each phase past the first has its own doc.

**Phase 1 — cut the render cost (the capacity work; no infrastructure).**
1. ✅ **Lazy tab panels** — shipped. `theme/base.py` builds panel containers up
   front and each tab's content on first show. Results in §1.5.
2. **Everything else** → [render-cost-plan.md](render-cost-plan.md): re-profile
   (the §1.3 attribution predates lazy tabs), the match table's element count,
   the Schedule tab's N+1, and a queries-per-render regression guard.

**Phase 2 — make the current constraint safe and honest (independent; cheap).**
→ [singleton-ownership-plan.md](singleton-ownership-plan.md). Advisory-lock
leader election over the gateway, the racetime runtime, and the five
`BackgroundLoop`s, plus a separate migration lock. Also documents item 8 (the
seed lock) as a single-process correctness dependency, as item 7 already
documents itself. Buys no capacity; makes a second process loud instead of
silently duplicating work. Prerequisite for Phases 3 and 4.

**Phase 3 — cross-process nudge + the split (availability).**
→ [web-worker-split-plan.md](web-worker-split-plan.md). `LISTEN`/`NOTIFY` behind
`match_live` (env-switched, landable before the split), then the
`ROLE=web|worker|all` branch, migrations moved to the worker role, worker
liveness, and the DB pool knob.

**Phase 4 — replicas (Target B).**
→ [web-replicas-plan.md](web-replicas-plan.md). Sticky sessions,
`NICEGUI_REDIS_URL`, shared stores for items 7/8/10. **Not currently needed** —
one worker now holds 500. Build only on a measured shortfall, and size from
Phase 1's re-measurement (~7.6 admissions/s and ~0.85 MB per tab today).

**Docs housekeeping (done alongside):** the "Scale vertically" line in
[deployment.md](../deployment.md) and the process-model paragraph in
[architecture.md](../architecture.md) now point here.

---

## 7. Open questions

- **What is the real arrival pattern for 500?** The plan assumes a crowd (a race
  goes live, a Discord announcement fires) because that is the hard case. If 500
  is really a slow accumulation over an evening, today's ~4 tabs/s already
  clears it and only memory needs sizing — Phase 1 stays worth doing, Phase 4
  may not be.
- **How many tabs does a typical viewer actually open?** 500 *connections* is not
  500 *people* if spectators keep the bracket and schedule open in two tabs.
  Worth measuring from telemetry before sizing replicas.
- **Is availability also a goal, or only capacity?** Phase 3 buys no capacity. If
  deploys dropping the Discord gateway is not a felt problem, Phase 3 can wait
  behind Phase 4 — but Phase 4's leader-election prerequisite (step 5) cannot.
- **DM queue after the split (step 9).** Enqueue-across-the-boundary is the clean
  answer but adds a durable-queue question we have otherwise avoided. Letting the
  web role keep its own DM queue is simpler and keeps ordering per-process only.
  Unresolved.
- **Does the worker role need `MOCK_*` parity** for local dev, or does dev keep
  running one combined process? Recommend: dev stays combined
  (`ROLE=all`, the current behavior, and the default).
