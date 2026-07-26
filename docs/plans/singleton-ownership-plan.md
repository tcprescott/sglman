# Singleton ownership: make `--workers 1` fail loudly

**Status:** proposed. Phase 2 of
[single-worker-escape-plan.md](single-worker-escape-plan.md).

**Why this is worth doing on its own:** today, raising the worker count or
running a second replica produces **duplicate Discord DMs, duplicate racetime
rooms, duplicate SpeedGaming syncs, and a broken custom-domain login** — with no
error anywhere. Nothing in the codebase notices. This plan makes that
misconfiguration loud, and it is the prerequisite for both the process split and
replicas.

It buys **no capacity**. It is a safety net, and it is cheap.

---

## 1. Why the obvious approach does not work

Roadmap item 22 of the [project-structure review](../reviews/2026-07-project-structure-review.md)
asked to "assert single-worker at startup (fail fast if `workers>1`)".

**That cannot be implemented as written.** `uvicorn --workers N` forks N children
and each child runs the app; a child cannot read its own worker count, and
`WEB_CONCURRENCY` is not set by uvicorn's own `--workers` flag. There is no
in-process value to assert on.

What *is* observable is the thing we actually care about: **whether another
process is already doing the singleton work.**

---

## 2. Design: Postgres advisory-lock leader election

On startup, the process attempts `pg_try_advisory_lock(<constant>)`.

- **Lock acquired ⇒ leader.** Start the Discord gateway, the racetime runtime,
  and the five `BackgroundLoop` workers.
- **Lock refused ⇒ follower.** Log a WARNING naming what is being skipped and
  why, and start nothing. Do **not** exit: a follower stays up as a warm standby
  and takes over when the leader dies.

Postgres is already a hard dependency, so this adds no infrastructure.

### The connection is the whole design

`pg_advisory_lock` is **session-scoped** — it is held by a *connection* and
released when that connection closes. That is exactly the failover semantics we
want (leader dies ⇒ lock frees ⇒ a follower can take over), but it means the lock
**must not** be taken on a Tortoise-pooled connection: pooled connections are
returned and reused, so the lock would be released at an arbitrary moment.

Take it on a **dedicated `asyncpg.connect()`** owned by the lifespan, held open
for the process's life, and closed on shutdown. This is the same "one long-lived
side connection" shape the `LISTEN`/`NOTIFY` work needs
([web-worker-split-plan.md](web-worker-split-plan.md)), so build the connection
helper once and let both use it.

### Follower promotion

A follower that never retries is only half a safety net. Give it a slow retry
(e.g. every 30 s) on the same dedicated connection; on acquiring the lock it
starts the singleton work in place. This turns the mechanism into genuine
failover rather than a startup-time coin flip.

*Decide explicitly:* whether promotion is in scope for the first cut. A
non-retrying follower is strictly better than today and much simpler. Retry can
follow.

---

## 3. What gets gated

Leader-only, from `main.py`'s lifespan:

| Work | Today |
|---|---|
| Discord gateway | `init_discord_bot()` |
| racetime bot runtime | `init_racetime_bot()` |
| race-room auto-open worker | `race_room_worker.start()` |
| SpeedGaming sync worker | `speedgaming_sync_worker.start()` |
| Discord events reconciler | `discord_event_worker.start()` |
| Service-health monitor | `service_health_worker.start()` |
| Volunteer reminders | `volunteer_reminder.start()` |

**Not gated** (every process needs its own): the DM queue and event dispatch
queue workers, the event-bus subscribers (webhooks, telemetry), NiceGUI, REST.

Note `volunteer_reminder` is already partly protected by its pre-send
`reminder_sent_at` stamp — it is the one worker that would not duplicate DMs
today. The other four have no such guard.

### Migrations

`init_db()` runs `aerich upgrade()` on every boot. Two processes racing the same
migration is item 15 of the escape plan's inventory and a real corruption risk.
Gate migrations behind **their own** advisory lock (a different constant, taken
and released around the upgrade) so a follower *waits for* the schema rather than
skipping it — followers still need the migrated schema to serve requests.

Do not fold this into the leader lock: leadership is long-lived, migration is a
short critical section, and a follower must block on the latter but not the
former.

---

## 4. Also in scope: document the correctness-critical singletons

Two module-level stores encode "one process" as a **correctness** guarantee, not
a performance assumption:

- `application/services/oauth_handoff_service.py:52` — `_pending` nonce store.
  Already documents this in its module docstring. Leave as is.
- `application/services/match/match_schedule_service.py:182` — `_seed_locks`.
  **Undocumented.** Add a comment stating that cross-process seed rolls are
  unguarded, so the next reader does not assume the lock is distributed.

---

## 5. Tests

- Leader path starts the gated work; follower path starts none of it.
- A follower logs the WARNING naming the skipped subsystems.
- The lock is released when the leader's connection closes (simulate a leader
  exit, assert a second process can acquire).
- Migration lock serializes: two concurrent `init_db()` calls apply the migration
  once, and the loser still sees the migrated schema.

The suite runs on SQLite, which has no advisory locks — so the election helper
needs a seam that no-ops (always-leader) on non-Postgres backends, and the
Postgres-specific behavior belongs in the existing Postgres CI job.

---

## 6. Success criteria

- Starting a second instance against the same database produces **zero**
  duplicate DMs, rooms, syncs, or health alerts, and says why in the log.
- The single-instance deployment behaves exactly as today (leader always wins an
  uncontended lock).
- `docs/deployment.md` documents the follower log line, so an operator who sees
  it knows it is a configuration problem, not a crash.
