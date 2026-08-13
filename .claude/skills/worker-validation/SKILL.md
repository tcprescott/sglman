---
name: worker-validation
description: >-
  Exercise a background worker against the real dev app by running its tick on
  demand instead of waiting out a 60-300s interval. The workers are the app's
  least-driven code — five of the eight have no test naming them, and
  BackgroundLoop swallows every failure into one log line, so a broken tick
  looks exactly like an idle one. Use after editing anything under a
  `run_worker_loop` module (seed roll polling, SpeedGaming sync, Discord event
  reconcile, volunteer/stage reminders, async-qualifier expiry, race-room
  auto-open, service health), or when asked to check that a worker actually
  does its job. The worker counterpart of /ui-validation and /api-validation.
---

# Driving a background worker

## Why a worker needs its own loop

`application/utils/background_loop.py` ends every tick with:

```python
except Exception as e:  # never let the loop die
    self._logger.exception('%s tick failed: %s', self.name, e)
```

That is the right call for production and the reason worker bugs go unseen: a
tick that raises on every run produces one log line per interval and no other
symptom. **Never conclude a worker works because nothing happened.**

The interval is the second obstacle. Only seed roll polling ticks fast enough
(5s) to stumble into by hand, and it is the only worker whose bugs were found by
driving the app: a tick landing mid-submit destroyed a live roll, a failed roll
told the admin nothing, and a restart orphaned a long-running one. The other
seven tick at 60-300s.

## Run one tick

```bash
poetry run python scripts/run_worker_tick.py --list
poetry run python scripts/run_worker_tick.py seed_roll
poetry run python scripts/run_worker_tick.py volunteer_reminder --tenant default
```

The runner awaits the module-level `_tick` directly and **re-raises** — the
opposite of the loop, on purpose. Setup is `/ui-validation`'s: `bash
scripts/setup_env.sh` once, then `poetry run python scripts/seed_dev.py`.

`--tenant` pins one tenant for reproducing a single community's behaviour. Leave
it off to exercise the real fan-out, which is what most ticks do.

## Checklist per worker

1. **Seed the state the tick acts on, then assert it acted.** Do not trust the
   fixture to be meaningful: the dev seed's RUNNING seed-roll rows referenced ids
   belonging to no live queue, so the poller retired them within a tick of boot
   and the fixture taught you nothing. Read the row before and after.
2. **Run it with the owning feature flag off.** A worker *skips the tenant*; it
   does not raise. `@requires_feature` raising inside a tick is swallowed, so the
   only evidence is a log line — this is the carve-out CLAUDE.md describes.
3. **Run it with two seeded tenants.** A tick touching scoped data outside
   `tenant_scope(...)` raises `require_tenant_id`, which the loop then hides.
   Confirm each tenant's rows moved and neither saw the other's.
4. **Grep the log, never the exit code.** `grep 'tick failed' /tmp/app.log` after
   any in-app run. The runner re-raises, but the live loop does not.
5. **Check what the tick renders.** Several send Discord DMs or web-push; those
   go through `notification_links` and must carry an absolute tenant-qualified
   link (see the calls-to-action rule in CLAUDE.md). `/discord-ux` renders the
   embed without a live bot.
6. **Re-run the tick immediately.** Nearly every one must be idempotent — the
   interval guarantees it runs again over the same rows. A second tick that
   sends a second DM is the bug.

## Worker map

| Name | Module | Tick |
|---|---|---|
| `seed_roll` | `application/services/seed_roll_worker.py` | 5s |
| `volunteer_reminder` | `application/services/volunteer/volunteer_reminder.py` | 60s |
| `async_qualifier` | `application/services/async_qualifier/async_qualifier_worker.py` | 60s |
| `speedgaming_sync` | `application/services/speedgaming_sync_worker.py` | 60s |
| `stage_reminder` | `application/services/match/stage_reminder.py` | 60s |
| `race_room` | `application/services/race_room_worker.py` | 60s |
| `service_health` | `application/services/service_health_worker.py` | 120s |
| `discord_event` | `application/services/discord/discord_event_worker.py` | 300s |

Only `stage_reminder` and `volunteer_reminder` have a dedicated test
(`tests/test_stage_reminder_worker.py`, `tests/services/test_volunteer_reminder.py`).
If your change is mechanical enough to pin down, leaving a test behind is worth
more than the session that found it.
