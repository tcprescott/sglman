# Running N web replicas

**Status:** proposed, and **not currently needed**. Phase 4 of
[single-worker-escape-plan.md](single-worker-escape-plan.md).
**Depends on:** [singleton-ownership-plan.md](singleton-ownership-plan.md),
[web-worker-split-plan.md](web-worker-split-plan.md).

**Read this first.** After lazy tab rendering, a single worker connected
**500/500 tabs and held them all**
([escape plan §1.5](single-worker-escape-plan.md)). The 500-concurrent-websocket
target is met without replicas. This plan exists for the case where the target
moves — a faster arrival burst, a larger event, or a second community sharing the
deployment — and it is the most expensive item in the programme. Do not build it
speculatively.

**Trigger to build:** a measured admission-rate shortfall that
[render-cost-plan.md](render-cost-plan.md) cannot close. Re-measure with
`scripts/loadtest/` before committing to this.

---

## 1. Why `--workers N` is still not the answer

Adding uvicorn workers to `main:app` does not work at any point in this
programme, before or after the split. NiceGUI is single-worker **by design**:

- Its bundled reference (`nicegui/llms.md`, "Architecture") states it outright.
- Its socket.io server is constructed with no cross-process client manager
  (`nicegui/nicegui.py:50`), so there is no way to route a message to a client
  held by another process.
- A client's element tree lives in the process that rendered its page.

More capacity therefore means more **replicas** — separate processes, each
serving whole clients — behind a load balancer that keeps a client on the
replica that rendered it.

---

## 2. Requirements

### 2.1 Sticky sessions (non-negotiable)

The load balancer must pin a browser to one replica, keyed on the NiceGUI client
cookie. Without it, a websocket lands on a replica that has never heard of that
`client_id` and the connection is refused — the exact failure the load driver
surfaces as `One or more namespaces failed to connect`.

There is no software workaround short of a socket.io Redis manager, which
NiceGUI does not wire up. If the deployment target cannot do sticky sessions,
**this plan is not viable** and render cost is the only lever.

### 2.2 Shared session storage

`app.storage.user` is a per-process dict flushed to `.nicegui/storage-user-*.json`.
Two replicas interleaving writes lose session state.

NiceGUI 3.12 ships the fix: set **`NICEGUI_REDIS_URL`** and storage moves to
`RedisPersistentDict` (`nicegui/storage.py:78-96`). This covers
`app.storage.user`, `general`, and `tab`.

This introduces **Redis as a hard dependency** — the first new infrastructure in
the whole programme. Weigh it accordingly.

### 2.3 Shared stores for the per-process state

From the escape plan's inventory, the items that break or degrade across
replicas and are *not* already solved by the split:

| Item | State | Fix |
|---|---|---|
| 7 | OAuth handoff nonce (`oauth_handoff_service.py:52`) | Redis. **Correctness + security**: mint on A, claim on B fails login, and single-use stops being enforced globally. |
| 8 | Per-match seed lock (`match_schedule_service.py:182`) | Postgres advisory lock keyed on `match_id` — avoids Redis, matches the primitive already introduced. **Correctness**: two replicas otherwise roll duplicate seeds. |
| 10 | API rate limiter (`api/rate_limit.py:37`) | Redis counter, or accept an effective limit of N × configured and document it. |
| 12 | Tenant resolution caches (`tenant_service.py:33-41`) | Piggyback invalidation on the `LISTEN`/`NOTIFY` channel from the split. |
| 6 | `match_live` fan-out | **Already solved** by the split's `LISTEN`/`NOTIFY`. |
| 14 | `app.storage.user` | §2.2. |
| 13 | Element trees / socket.io | §2.1. |

Items 7 and 8 are the ones that fail *silently and wrongly*; 10 and 12 merely
degrade. Sequence 7 and 8 first.

---

## 3. Sizing

From the measured post-lazy numbers, **per replica**:

- **~7.6 admissions/second** (tenant home at 132 ms CPU/render). Improves with
  [render-cost-plan.md](render-cost-plan.md); re-derive from that work rather
  than from this figure.
- **~0.85 MB RSS per connected tab**, plus ~145 MB baseline. 500 tabs ≈ 560 MB.
- **~7 % of one core** to hold 500 idle sockets. Holding is not the cost;
  admitting is.

Size replica count from the **arrival burst** you need to absorb, not from the
steady-state connection count:

```
replicas ≈ ceil( peak_arrivals_per_second / admissions_per_second_per_replica )
```

Memory then follows from how the held connections distribute across them.

---

## 4. Open questions

- **What is the real arrival pattern?** The whole plan turns on this. 500 tabs
  over an evening needs nothing; 500 in ten seconds when a Discord announcement
  fires needs several replicas. Worth answering from telemetry — page-view
  timestamps already exist — before provisioning anything.
- **How many tabs per person?** 500 connections is not 500 people if spectators
  keep the bracket and the schedule open side by side. Also answerable from
  telemetry, and it changes the sizing denominator.
- **Is Redis acceptable?** It is required for §2.2 and the cleanest answer for
  §2.3. If not, the ceiling is one web replica and render cost is the only lever.

---

## 5. Success criteria

- N replicas behind sticky sessions serve a burst of `N × 500` tabs with zero
  connection failures and no session loss on reconnect.
- Custom-domain login works when the mint and the claim land on different
  replicas (item 7).
- Two replicas cannot roll duplicate seeds for the same match (item 8).
- A match change on any replica refreshes browsers attached to every replica.
- Killing one replica drops only its own clients; they reconnect and recover.
