# Proctor & admin match-day UX — implementation plan

Follow-up to [`docs/reviews/2026-07-proctor-workflow-ux-audit.md`](../../reviews/2026-07-proctor-workflow-ux-audit.md).
That document is the *evidence*; this directory is the *work*. Read the audit's
finding (F-number) referenced by a task before implementing it.

**Read this file completely before starting any task.** It contains the ground
rules and the verification loop that every task depends on and that none of the
wave files repeat.

## Wave files

| Wave | File | Theme | Tasks |
|---|---|---|---|
| 1 | [wave-1-role-boundary.md](wave-1-role-boundary.md) | Stop proctors doing the admin's job; small gating fixes | T1.1 – T1.5 |
| 2 | [wave-2-checkin-and-stations.md](wave-2-checkin-and-stations.md) | Make check-in honest; give stations a real pool | T2.1 – T2.4 |
| 3 | [wave-3-proctor-board.md](wave-3-proctor-board.md) | A purpose-built proctor board instead of the admin table | T3.1 – T3.6 |
| 4 | [wave-4-admin-review-loop.md](wave-4-admin-review-loop.md) | The admin's verify-and-confirm loop, incl. disputes | T4.1 – T4.5 |

Waves are ordered by dependency. **Do not start wave N+1 until wave N is merged**
— wave 2 assumes the auth split from T1.1, wave 3 assumes the dialog changes from
wave 2, wave 4 assumes the proctor/admin surfaces have diverged (T3.1).

Within a wave, tasks list their own `Depends on`. Tasks with no dependency can be
done in any order or in parallel.

## The workflow being served

A proctor runs an on-site match:

1. Check both players in once they're in the room.
2. Seat each player at a numbered station (players sit on opposite sides of a
   room that faces inward).
3. Generate the seed, if the tournament has one.
4. Confirm both are ready, count them down, mark the match started.
5. On a raised hand, verify the win and record the winner.
6. Done.

An **admin** then reviews the recorded result, resolves any dispute, and confirms
it — which advances the bracket and pushes to Challonge.

Facts established with the product owner that these specs encode. **Do not
re-litigate them; if a task seems to contradict one, the task is wrong — stop and
ask.**

- **One proctor per room.** The board is a *room* board showing every match in
  flight, not a per-proctor worklist. Do not build match→proctor assignment.
- **Check-in is per match**, once both players are present. The single
  match-level `Match.seated_at` is correct. Do not add per-player check-in.
- **Stations are a fixed, venue-owned pool with no pairing rule.** The proctor
  picks two of the real stations; which two is their judgment. Do not build
  automatic station pairing.
- **All devices matter** — phone, tablet, and a shared desk laptop.
- **Confirm is the admin's step**, never the proctor's.
- **One winner, one loser** is the only outcome to model. Do **not** build
  forfeit / DQ / double-forfeit / no-result states.
- **Disputes**: the proctor records their best guess and flags it; the admin
  overrides during confirmation.
- **Seeds reach players by Discord DM.** The proctor needs to know it went out,
  not to hand it over.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit
most often:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service
(`application/services/`) → Repository (`application/repositories/`) → Models.
Presentation never imports repositories and never writes through the ORM.
Services never import NiceGUI. `enforce_architecture.py` blocks violations at
write time.

**Tenant scoping.** Repositories read via `scoped(Model.filter(...))` and write
with `tenant_id=current_tenant_id()` (`application/repositories/_tenant.py`). A
direct model read outside a repository hand-scopes:
`Match.get_or_none(id=x, tenant_id=require_tenant_id())`. Any new tenant-scoped
model needs a leak test in `tests/tenancy/`.

**Errors.** Services raise `ValueError` for user-facing problems and
`PermissionError` for authorization. Presentation catches both and calls
`notify_error(e)` from `theme/notify.py` — amber for `ValueError`, red for
`PermissionError`. Do not hand-roll `ui.notify` for a caught service error.
REST maps `ValueError` → 400, `PermissionError` → 403 (`api/dependencies.py`).

**Audit + events.** Every create/update/delete writes an audit row. When the
change also has a matching `EventType`, use one call:

```python
await self.audit_service.write_and_publish(
    actor, AuditActions.MATCH_X, {...}, EventType.MATCH_X,
    event_extra={'tournament_id': match.tournament_id},
)
```

`check_dry_regressions.py` blocks a hand-rolled `write_log` + `event_bus.publish`
pair. A new `AuditActions` member **must** either gain a mirror `EventType`
member (added to both `EventType` and `EventType.ALL`) or be listed in
`_EVENT_CANDIDATES` / `_EXCLUDED_BY_DESIGN` in
`tests/services/test_event_audit_parity.py` — otherwise that test fails. Each
task below says which.

**NiceGUI.** `background_tasks.create(...)`, never `asyncio.create_task`. Capture
`context.client` before a background task that touches UI and restore it with
`with client:` (sync `with`, never `async with`). Never store per-user state at
module level.

**Mobile.** Every `ui.table` needs a grid/card view. The match table has a
bespoke `item` slot in `theme/tables/match_grid.py`; **any change to a desktop
cell slot in `match_slots.py` almost always needs the mirror change in
`match_grid.py`.** Each task calls out both files where that applies.
`check_table_grid.py` enforces this for new tables.

**Dev seed.** A new model, or a new state a proctor/admin can reach, needs a
representative row in `scripts/seed_dev.py` (idempotent `get_or_create`,
tenant-scoped like the rows around it). `check_seed_coverage.py` blocks a new
model that no seed script mentions.

**File length.** `check_file_length.py` advises over 800 lines and demands a
split over 1500. `theme/dialog/match_dialog.py` is already 799 — do not grow it.

## Verification loop

Every task's `Verify` section assumes this is already running.

```bash
bash scripts/setup_env.sh                      # once per environment
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Seeded logins (mock Discord user picker at `/t/default/login`):
`proctor_user` (PROCTOR + VOLUNTEER), `staff_user` (STAFF), `sm_user`,
`player_one`…`player_four`. Pages live under `/t/default/…`; a bare `/admin`
404s.

Drive a page and screenshot it:

```bash
cat > /tmp/check.json <<'JSON'
{
  "loginAs": "proctor_user",
  "tenant": "default",
  "outDir": "/tmp/ui-check",
  "targets": [
    { "name": "proctor", "path": "/volunteer/proctor-station", "selector": ".match-table" }
  ]
}
JSON
NODE_PATH=$(npm root -g) node scripts/ui_smoke.js /tmp/check.json
```

Add `"viewport": {"width": 430, "height": 1200}` at the config top level for the
mobile card layout. Read the resulting `.png` with the Read tool — a blank cell
or a `console.error` means a broken Vue template, which Python tests cannot
catch. For anything that needs a click (opening a dialog, submitting it), write a
one-off Playwright script; see the `ui-validation` skill for the login snippet.

Tests:

```bash
poetry run pytest                                   # whole suite, parallel
poetry run pytest tests/services/test_auth_service.py
poetry run pytest -n0 -k station                    # serial, for -s / pdb
```

Migrations, when a task adds one:

```bash
poetry run aerich migrate --name <snake_case_name>
poetry run aerich upgrade
```

## Definition of done for every task

1. The change is implemented in the files named, at the layer named.
2. `poetry run pytest` is green.
3. The task's own tests exist and fail without the change.
4. The affected page renders in the browser at both desktop (1500px) and phone
   (430px) widths, verified by screenshot, with no new console errors.
5. Docs named in the task are updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and say
explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md` states the convention: *design records are not kept after they
ship*. When the last wave merges, **delete `docs/plans/proctor-ux/` and
`docs/reviews/2026-07-proctor-workflow-ux-audit.md`**, remove their rows from the
"Work in flight" table in `docs/README.md`, and make sure the behaviour they
described now lives in the feature docs — principally
[`docs/features/match-participation.md`](../../features/match-participation.md)
(check-in, stations, the dispute flag) and
[`docs/reference/authentication.md`](../../reference/authentication.md) (the
`can_run_match` / `can_confirm_match` split). Git history holds the rationale.

Delete a wave file as its wave merges, rather than all four at the end — a
half-done plan left lying around reads as current work.
