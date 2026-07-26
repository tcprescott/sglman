# Splitting `web` from `worker`

**Status:** proposed. Phase 3 of
[single-worker-escape-plan.md](single-worker-escape-plan.md).
**Depends on:** [singleton-ownership-plan.md](singleton-ownership-plan.md).

**What this buys:** availability, not capacity. Today one process owns the
FastAPI app, the Discord gateway, the racetime websockets, the DM queue, and the
five background loops — so shipping a UI copy change disconnects a live
racetime room's bot and drops whatever DMs were queued. This separates the
release cadence of the web tier from the long-lived connections.

**What it does not buy:** admissions per second. If the goal is purely the
500-connection target, that is already met
([escape plan §1.5](single-worker-escape-plan.md)) and this can wait.

---

## 1. Shape

One image, two roles, selected by env var:

```
ROLE=web      FastAPI + NiceGUI + REST + tenant caches.  --workers 1
ROLE=worker   Discord gateway, racetime runtime, the five background
              loops, the DM queue, migrations.  No HTTP server.
ROLE=all      Today's behavior. The default, and what dev uses.
```

`ROLE=all` staying the default matters: local development, the test suite, and
`/ui-validation` should not have to run two processes.

---

## 2. The one new primitive: Postgres `LISTEN`/`NOTIFY`

Two things must cross the process boundary once the split lands.

**Live UI updates (the blocking one).** `application/events/match_live.py`
publishes in-process; `theme/realtime.py` and `theme/brackets/live.py` subscribe
per browser client. After the split, a match change committed by the *worker*
(racetime finishing a race, the SpeedGaming sync landing a schedule) would never
reach a browser attached to the *web* process. The live schedule and bracket
would silently go stale — escape-plan inventory item 6, the one break that is
invisible rather than noisy.

**The DM queue.** Web-side code enqueues Discord sends; the worker drains them.

Use `LISTEN`/`NOTIFY` rather than adding Redis:

- `match_live.publish()` also issues `NOTIFY wizzrobe_match_live, '<json>'`.
- Each process holds one long-lived listener connection and re-publishes what it
  receives into its own local `_subscribers`, so **`theme/realtime.py` and
  `theme/brackets/live.py` need no changes at all**.
- Ship it behind an env switch, default off, so it is a no-op in the current
  single-process deployment and can land before the split does.

**Constraints to design around:**

- `NOTIFY` payloads cap at 8000 bytes and deliver on commit. Carry identifiers
  only — never a serialized model.
- The listener needs a dedicated `asyncpg.connect()`, not a Tortoise-pooled
  connection. Same helper as the advisory lock; build it once.
- Delivery is at-most-once and best-effort. That is acceptable for a UI nudge
  (a missed refresh self-heals on the next event or reload) and **not**
  acceptable for anything transactional. Do not extend this to domain events
  that must not be lost.

`event_bus` does **not** need to cross the boundary: each process publishing its
own events to its own subscribers is correct, provided the webhook and telemetry
subscribers are registered in **both** roles. Verify that when wiring the roles.

---

## 3. Loose ends the split creates

- **Migrations.** Assign to the worker role. Web waits for the schema. The
  migration advisory lock from
  [singleton-ownership-plan.md](singleton-ownership-plan.md) is what makes
  "waits" well-defined.
- **Healthchecks.** The Docker and compose healthchecks curl `/api/health`,
  which the worker role will not serve. Give the worker its own liveness signal
  — a heartbeat row, or a minimal HTTP listener — rather than leaving it
  unmonitored. An unmonitored worker that has silently died is worse than
  today's coupled process.
- **DB pool.** Tortoise defaults to `maxsize=5` per process; two roles double
  the connection count. Make it configurable while here. (Not a capacity fix —
  the pool was measured uncontended — just hygiene now that process count is
  variable.)
- **`main.py` lifespan** grows one branch on role. Keep the existing feature-flag
  checks exactly where they are; role gating is a separate axis from
  `FeatureFlag`.
- **`tenant_scope`.** Already correct — every worker path wraps scoped data
  today, a discipline built for the existing background loops. No new work, but
  worth re-checking anything that moves.

---

## 4. Open question: the DM queue

Two defensible answers; **pick one deliberately rather than letting it drift.**

1. **Enqueue across the boundary.** Web `NOTIFY`s, worker drains. Clean
   ownership — one Discord connection, one sender. Adds a durability question we
   have so far avoided: a `NOTIFY` lost between commit and delivery is a DM
   silently never sent, which is worse for a match notification than for a UI
   refresh.
2. **Web keeps its own DM queue.** Simpler, no new failure mode, but Discord
   sends then originate from two processes and serialization becomes per-process
   rather than global.

Note (1) is only safe if the send is recoverable — the pattern to copy is
`volunteer_reminder`'s pre-send `reminder_sent_at` stamp, which the review
already flagged as the durability model the notification queue should adopt.
**Recommendation:** (2) for the first cut, revisit if per-process ordering
actually bites.

---

## 5. Phasing

1. `LISTEN`/`NOTIFY` transport behind `match_live`, env-switched, default off.
   Land and verify while still single-process.
2. Tests: publish on one connection, assert delivery to a subscriber registered
   against another; assert the switch-off path is a pure no-op.
3. `ROLE` branch in the lifespan, `start.sh`, and compose.
4. Migrations to the worker role; web waits.
5. Worker liveness; DB pool knob.
6. Resolve §4 and implement it.

---

## 6. Success criteria

- Restarting the web role leaves the Discord gateway connected and a live
  racetime room undisturbed.
- A match change made by the worker role refreshes an open browser attached to
  the web role (the item-6 regression, tested end to end in a browser — pytest
  cannot see this).
- `ROLE=all` is byte-for-byte today's behavior; dev and CI are unchanged.
- Killing the worker role is visible in monitoring within one healthcheck period.
