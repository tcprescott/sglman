---
name: incident
description: >-
  Diagnose and fix a live production problem in Wizzrobe fast — the app is
  slow, frozen, erroring, or a worker has gone quiet — during an event. Reads
  live load (the super-admin `runtime_stats` MCP tool), Sentry issues, traces,
  profiles and logs, narrows the cause to a file and line, reproduces it
  locally, and ships the smallest safe fix as a PR. Use whenever someone
  reports production trouble ("the schedule is slow", "pages won't load",
  "people are getting errors", "DMs stopped"), or asks to investigate a Sentry
  alert or a loop-stall issue.
---

# Production incident

Production is one container on one asyncio loop (`docs/scaling-roadmap.md`).
That shapes every diagnosis: a slow request is rarely the problem on its own,
and one synchronous stretch in any handler freezes every user. Work in this
order and stop as soon as the cause is clear. Speed matters more than polish,
but a fix that turns CI red costs more time than it saves.

## 1. Look before touching code

Run these together, in one turn:

- **`runtime_stats`** (Wizzrobe MCP, super admin, no `tenant`). Read it like this:
  - `event_loop.recent_stalls` not empty: something blocked the loop, and
    `culprit` is the file and line. That's the fix target. Go to step 3.
  - `lag_ms_p95` high, no stalls, `cpu_percent` near 100: the app is saturated
    by load (renders are CPU-bound, about 10 new tabs a second per process).
    Look at `clients.connected` and `watch_pages_by_tenant_id.*.arrivals_last_minute`.
    The fast lever is static mode on the Watch page (Admin → Settings → Watch
    page) and pointing crowds at static `/live/…` bracket links, not code.
  - `db_pool.idle` at 0 with `size` at `max`: queries are queueing. Find the
    slow query in Sentry traces.
  - A worker with `failures` climbing, or `last_started_at` far older than its
    `interval_seconds`: that worker is broken or stuck. See
    `/worker-validation` for exercising its tick locally.
- **Sentry** (connector): unresolved issues in production for the current
  `release`, newest first; any issue tagged `loop_blocked_in`; traces for the
  slow page (sort by duration) and their profiles; Sentry Logs filtered by
  `tenant_id` around the reported time.
- **`list_service_health`** for the community, when the symptom smells like an
  outside service (racetime, Challonge, Discord, seed generators).

If a tool is missing or refuses (Sentry not signed in, connection not super
admin), say so to the person in one line and carry on with what you can read.
Never guess at production state.

## 2. Say what you found

Before writing code, reply with the cause in one or two sentences and the
evidence (the stall culprit, the trace, the issue link), plus any lever staff can
pull right now without a deploy (static mode, or turning a module's logging up on
Platform → Logging). They may need that lever
more than the fix.

## 3. Reproduce

- A loop stall or slow render: `scripts/loadtest/profile_render.py` cProfiles a
  page render in-process; point `PATH` at the slow page. `scripts/loadtest/ws_load.py`
  reproduces the admission ceiling. Setup in `scripts/loadtest/README.md`.
- A query fan-out: `tests/test_query_budget.py` shows how to count queries per
  render. Add a budget for the page you fix.
- An error: write the failing test first from the Sentry stack.

## 4. Fix narrowly

- The usual culprits on this loop: a sync call in an async path (`requests`,
  `time.sleep`, heavy CPU in a handler, a big `json`/markdown render per row),
  a per-row query inside a render loop (move it into the repository's
  prefetch), or a table rebuilt in full on every live refresh.
- CPU-heavy work that can't shrink goes in `await asyncio.to_thread(...)`.
- No feature work and no refactors mid-event. Keep the diff to what the
  incident needs, and leave a follow-up note for anything bigger.
- If the fix touches a migration, say so loudly: rollback won't undo it
  (`docs/deployment.md#rollback-caveat`), and Thomas needs a DB backup first.

## 5. Ship

- Run the fast checks for what you touched (the relevant pytest files, ruff,
  the guardrail hooks fire on their own), then push and open the PR, then
  subscribe to it and drive CI to green.
- In the reply, give the merge-and-deploy steps: after merge, the
  `Publish Container` workflow builds `ghcr.io/tcprescott/wizzrobe` (usually
  5 to 11 minutes); then on the host, the Upgrade steps in
  `docs/deployment.md` (`docker compose pull wizzrobe` when the compose file
  points at the GHCR image, then `docker compose up -d wizzrobe`).
  A redeploy keeps sessions (Redis) but drops open sockets for a few seconds.
- After the deploy, read `runtime_stats` and Sentry again to confirm the stall
  or error is gone under the new `release`.
