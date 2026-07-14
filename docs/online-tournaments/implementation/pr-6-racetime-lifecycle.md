# PR 6 — Racetime room lifecycle for scheduled matches

> Feature 5. Roadmap phase 4 — **the core online loop.** Completes scheduled online
> brackets (the decided-first focus).
>
> **Status: implemented.** `RaceRoomService` maps the lifecycle onto a `Match`:
> `create_room_for_match` (idempotent; opens the room, attaches the seed via
> `MatchScheduleService.generate_seed`), `mark_in_progress` (sets `started_at`),
> `record_finish` (maps racetime entrants → linked `User`, records `finish_rank`
> place + `finish_time` seconds, closes the match, feeds the existing result path +
> optional Challonge push), `cancel_room`. Terminal states (forfeit / no-show / DQ /
> one-finisher) map correctly; unmatched handles are surfaced in the audit for staff
> reconcile. Every transition audits + publishes a `race_room.*` event as the system
> user. `RaceRoomLifecycle` is the adapter the PR 4 handler injects (transport event
> → service call). The auto-open worker (`race_room_worker`) is an opt-in background
> loop (`racetime_auto_create_rooms` + `room_open_minutes_before`, eligibility = all
> entrants linked, idempotent, keep-room-on-reschedule); `manual_create_room`
> (STAFF/`SYNC_ADMIN`) is exposed from the admin match dialog. Migration 25 adds
> `matchplayers.finish_time`. Mock-driven tests cover the full lifecycle, terminal
> states, and the worker's eligibility rules.

**Goal:** from a scheduled `Match`, auto-create and drive a racetime room through
finish/cancel, attaching the seed and capturing results.

**Depends on:** PR 1 (presets), PR 2 (identity), PR 4 (bot runtime). **Unblocks:**
PR 10 (live races reuse this).

## Deliverables

- **`RaceRoomService`**: the business layer both the auto-open worker and the PR 4
  handlers call. Lifecycle mapped onto `Match`:
  create → open → **attach seed** (via `SeedGenerationService` + the tournament's
  `Preset`, posted at the configured moment) → in-progress (`started_at`) →
  **finish** (capture each entrant's finish time/place, map racetime users → `User`,
  record results, `finished_at`, hand to result reporting) → cancel/abort. Audit +
  `race_room.*` events on every transition. Acts as the **system user**.
- **Auto-open worker** ([decisions](../README.md#decisions-log)): background loop
  under `tenant_scope`; **opt-in per tournament** (`racetime_auto_create_rooms` +
  `room_open_minutes_before`); **eligibility = all entrants have linked racetime**;
  **idempotent** (one `RacetimeRoom` per match); retry with backoff + staff-visible
  error + manual-create fallback. **Reschedule with an open room = keep the room,
  update time only.**
- **Result capture**: reuse `MatchPlayers.finish_rank` for place, add a finish-time
  column; map handles → `User` (unlinked → raw handle for staff reconcile). Handle
  **terminal states** — forfeit / no-show / one-finisher / DQ ([gap §3.1](../gap-analysis.md)),
  not just a clean finish.
- **Result reporting**: feed the existing `record_match_result` / confirm path;
  Challonge push is the optional downstream step (**non-Challonge tournaments still
  close** — [gap §3.4](../gap-analysis.md)). Corrections flow through the existing
  path, not a one-shot ([gap §3.3](../gap-analysis.md)).
- **Manual room creation** (STAFF/`SYNC_ADMIN`) regardless of the auto-open toggle.
- Migration (finish-time column), tests (mock-driven lifecycle end to end).

## Decisions that apply

Opt-in auto-open; linked-entrants eligibility; keep-room-on-reschedule; hybrid
config; system-user actor. Honor gap §3.1/§3.3/§3.4.

## Reference implementations

- **sahabot2**: `application/services/racetime/racetime_room_service.py`,
  `racetime/client.py` (in-room seed roll guards: one-seed lock, re-roll, roll
  authorization), the room-open lead-time = `stream_delay + room_open_time` and
  countdown-vs-restream time handling ([gap rt-stream-delay](../gap-analysis.md)).
- **sglman**: `application/services/match_schedule_service.py` (transition ordering,
  seed attach, DM fan-out — note the ordering guards seat→start→finish),
  `match_service.py:record_match_result`, `challonge_service.py:push_match_result`.

## Acceptance criteria

- A scheduled ALTTPR match with two linked players auto-opens a room at the lead
  time, gets seeded, and on finish records both results + reports to Challonge (mock
  the racetime side; verify against a real seed roll). A match with an unlinked
  entrant is skipped with a staff-visible note. Forfeit/no-show map correctly.

## Out of scope

Async qualifier live races (PR 10); N-way FFA bracket reporting (brackets are 1v1).
