# Match runners — implementation plan

Make "who runs this match" a first-class type instead of a scattered
`is_racetime` boolean, so a third way of running matches (a human coordinating
an online match, or some future third-party race tool) can be added without
touching sixteen call sites.

**Read this file completely before starting any task.** It carries the evidence,
the design decisions and the ground rules that the wave files do not repeat.

## Wave files

| Wave | File | Theme | Migration? |
|---|---|---|---|
| 1 | [wave-1-capability-type.md](wave-1-capability-type.md) | Introduce `MatchRunner` + capabilities; replace the service-layer checks | no |
| 2 | [wave-2-presentation.md](wave-2-presentation.md) | Replace the eleven template conditionals and the row dict | no |
| 3 | [wave-3-unify-lifecycle.md](wave-3-unify-lifecycle.md) | One lifecycle path, so racetime stops bypassing audit/events/notifications | no |
| 4 | [wave-4-manual-remote.md](wave-4-manual-remote.md) | The third runner, and the column that makes runners selectable | **yes** |

Waves 1 and 2 are a pure refactor with no behaviour change — **you can stop
after wave 2** and still have collapsed the abstraction. Wave 3 is a correctness
fix that changes what subscribers see. Wave 4 is the new capability.

Do not start wave N+1 until wave N is merged.

## The evidence this exists to fix

Counted on the branch this plan was written against:

- **16 places test racetime-ness**, across four layers — 11 Vue templates
  (`match_grid.py` ×7, `match_slots.py` ×4), 3 services, 1 repository, 1 model.
- Four consecutive waves of the proctor-UX work each had to touch them
  separately: the seed button, the check-in button, the stations button, the
  board filter.

Two symptoms say the concept is missing rather than merely repeated:

**It has no queryable representation.** `Tournament.is_racetime_enabled` is a
Python `@property` over the `racetime_bot` FK, so
`tournament__is_racetime_enabled=False` raises `FieldError`.
`MatchRepository.get_all` reaches through to
`tournament__racetime_bot_id__isnull=True` instead. The concept exists in Python
and not in SQL.

**One identity flag answers four different questions.** Each site actually wants
a capability, not the identity of an integration:

| Site | The real question |
|---|---|
| Seed *Generate* button | Does something else own the seed? |
| *Check In* button | Does a human seat players? |
| *Assign Stations* | Are there physical seats? |
| Proctor board filter | Does this match need a person at all? |

**And the two paths have diverged.** `application/services/race_room_service.py`
writes `match.started_at`, `match.finished_at` and `MatchPlayers.finish_rank`
**directly**, never through `MatchScheduleService._transition`. Consequences,
all of which wave 3 addresses:

- It emits `RACE_ROOM_STARTED` / `RACE_ROOM_FINISHED`, not `MATCH_STARTED` /
  `MATCH_FINISHED`. A webhook subscriber watching for a match to start never
  hears about a racetime match.
- It sends no player notifications; `_transition` does.
- `_settle_bracket` exists purely because a racetime finish never *confirms*,
  so `advance_if_linked` (which hangs off `confirm_match`) would never fire.
  Its own docstring says so.

## Design decisions

Fixed. **If a task seems to contradict one of these, the task is wrong — stop
and ask.**

- **Confirmation is not part of a runner.** Whoever runs the race, an admin
  still verifies and confirms; that is Wizzrobe's governance, not the race
  system's. `confirm_match`, `can_confirm_match`, bracket advancement, the
  Challonge push and the review flag all stay outside the abstraction.
- **The name is `MatchRunner`, not `RaceManager`.** The thing that varies is who
  runs the match; confirm sits above all of them. A "manager" implies it owns
  the whole lifecycle, which would invite exactly the mistake above.
- **Capabilities, not `isinstance`.** Call sites ask *"does this runner assign
  stations?"*, never *"is this the racetime runner?"*. An `isinstance` check or
  a `runner.key == 'racetime'` comparison outside the runner module is a bug.
- **Derived before stored.** Waves 1–3 resolve the runner from data that already
  exists (`racetime_bot_id`). The `runner_key` column arrives only in wave 4,
  when there is a third runner that cannot be derived.
- **A registry, not a plugin loader.** A dict of concrete classes in one module.
  No entry points, no dynamic discovery, no third-party registration hook. If
  that is ever wanted, it is a separate decision.
- **No per-tenant feature flag.** This is infrastructure every tenant already
  uses implicitly, not a gated subsystem.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service
(`application/services/`) → Repository (`application/repositories/`) → Models.
`enforce_architecture.py` blocks violations at write time. **The runner type is
a domain concept, not a service** — see wave 1 for where it lives and why.

**Tenant scoping.** Repositories read via `scoped(...)` and write with
`tenant_id=current_tenant_id()`. A runner must never perform an unscoped read.

**Errors.** Services raise `ValueError` (user-facing) / `PermissionError`
(authorization); presentation catches and calls `notify_error(e)`. When a
capability forbids an action, the *runner* supplies the message — that is much
of the point, since today those strings are hardcoded to say "racetime.gg".

**Audit + events.** `AuditService.write_and_publish`; `check_dry_regressions.py`
blocks a hand-rolled `write_log` + `event_bus.publish` pair. `EventType` is an
external contract — add, never rename. Wave 3 changes which events fire for
racetime matches; that is a deliberate, breaking-ish change and must be called
out in its commit message.

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. A table
event handler that touches tenant-scoped data must be scheduled through
`MatchTableView._bg` — `tests/theme/test_match_table_tenant_binding.py` enforces
it, and names events by their *registered* string (note `'edit-stage'`
uses hyphens).

**Vue templates** are Python strings with server-injected placeholders
(`__IA__`, `__CC__`, `__DID__`, `__WATCH__`, `__ACTCLS__`) substituted via
`_fill`. `STATE_SLOT` goes through `_fill`; `SEED_SLOT` is registered **raw**.
Confirm a template is filled before relying on a placeholder in it, and run
`tests/theme/test_match_slot_templates.py`, which sweeps for survivors.

**Mobile.** Every desktop cell-slot change needs its mirror in
`theme/tables/match_grid.py`.

**Dev seed — one tournament per runner.** The seed currently splits
on-premises from racetime-managed fixtures. That split is really *one
tournament per way of running matches*, and it generalises with this plan:
every runner gets its own representative tournament, named for how it is run,
with matches in the states that runner can actually reach. A racetime
tournament should not hold matches walked through the proctor lifecycle, and an
on-premises one should not hold a race room. Adding a runner without adding its
tournament means no one can see it — treat the seed as part of the runner, not
an afterthought. `check_seed_coverage.py` enforces this for new models.

**File length.** `check_file_length.py` advises over 800 lines. Several files
this plan touches are already close — check before adding, and extract a module
the way `application/services/match/match_review.py` and `scripts/seed_onsite.py`
already are.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/<slug>/login`: `proctor_user`, `staff_user`,
`player_one`…`player_four`. Pages live under `/t/default/…`; a bare `/admin`
404s. Chromium is at `/opt/pw-browsers` — **never run `playwright install`**.
`scripts/ui_smoke.js` is a config-driven harness; read its header comment.

The four surfaces that share these templates and must all be checked at 1500px
**and** 430px:

- `/t/default/volunteer/proctor-station` as `proctor_user`
- `/t/default/admin/schedule` as `staff_user`
- `/t/default/` and `/t/default/home/player` as `player_one`

```bash
poetry run pytest                 # whole suite, parallel
poetry run pytest -n0 -k runner   # serial, for -s / pdb
scripts/ui_flag_sweep.sh          # flags-off sweep
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why.
4. The affected surfaces render at both widths, verified by screenshot, with no
   new console errors.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each
wave file as its wave merges, and when the last one lands delete this directory,
remove its row from the "Work in flight" table, and make sure the behaviour
lives in the feature docs — principally
[`docs/reference/data-model.md`](../../reference/data-model.md) (the runner and
its resolution) and
[`docs/features/online-tournaments.md`](../../features/online-tournaments.md)
(what the racetime runner does, and what a manual one does instead). Git history
holds the rationale.
