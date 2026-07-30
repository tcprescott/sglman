# Volunteer hub UX — implementation plan

Follow-up to [`docs/reviews/volunteer-hub-ux.md`](../../reviews/volunteer-hub-ux.md).
That document is the *evidence*; this directory is the *work*. Read the finding
(F-number) and root cause (RC-number) a task names before implementing it.

**Read this file completely before starting any task.** It carries the design
decisions, the ground rules and the verification loop that every task depends on
and that none of the wave files repeat.

## Wave files

| Wave | File | Theme | Tasks |
|---|---|---|---|
| 1 | [wave-1-draft-means-draft.md](wave-1-draft-means-draft.md) | A draft is the coordinator's sketch until they publish it | T1.1 – T1.5 |
| 2 | [wave-2-autofill-you-can-trust.md](wave-2-autofill-you-can-trust.md) | Availability becomes a constraint, hours a ceiling, the result a record | T2.1 – T2.4 |
| 3 | [wave-3-the-volunteers-side.md](wave-3-the-volunteers-side.md) | A page instead of a receipt: hand a shift back, know what it is, be told when it changes | T3.1 – T3.5 |
| 4 | [wave-4-day-at-a-glance.md](wave-4-day-at-a-glance.md) | The coordinator's on-site view: sticky day, coverage strip, a phone-sized grid | T4.1 – T4.3 |

Waves are ordered by dependency. **Do not start wave N+1 until wave N is merged.**
Wave 2's result panel assumes wave 1's publish step exists (its open-slot list
sits beside the Publish button); wave 3's DMs assume the wave 1 invariant that an
`auto_generated` assignment has never been announced; wave 4 restyles the grid
wave 1 and 2 add controls to.

Within a wave, tasks list their own `Depends on`. Tasks with no dependency can be
done in any order or in parallel.

## The workflow being served

Two people, and the whole plan is about the seam between them.

A **coordinator** builds an event day: define positions, generate the day's
shifts, auto-fill a draft from availability, review and fix it by hand, then
**publish** it — which is the moment the volunteers are told. On the day they
watch coverage and check people in.

A **volunteer** opts in, declares availability, and then wants three things from
their own page: what am I down for, what does it involve, and how do I get out of
one I can no longer do.

## Design decisions

These are the choices the tasks encode. **Do not re-litigate them mid-task; if a
task seems to contradict one, the task is wrong — stop and ask.** The five marked
**confirm** are recommendations that need the product owner's yes before wave 1
starts (see [Open questions](#open-questions)).

- **`auto_generated=True` means "nobody has been told".** That is the invariant
  the whole first wave exists to create, and every later wave leans on it: a
  draft is invisible to the volunteer, never reminded, never acknowledgeable, and
  silently deletable. Publishing flips the flag, and flipping the flag is what
  sends the DM.
- **A draft is hidden from the volunteer, not labelled for them** (confirm). A
  provisional shift they cannot act on and might lose is noise, and the audit
  measured what labelling-by-omission does. Publish is the moment it becomes
  real.
- **Publish acts on the selected day's window**, the same window auto-fill and
  clear-draft already act on. No per-assignment publish button; a coordinator who
  wants one volunteer told now assigns them by hand, which already notifies.
- **Coordinator-facing counts keep counting drafts.** The grid's `n/m` badges,
  `coverage()`, the CSV export and `volunteer_hour_trends` are the coordinator's
  working schedule — a draft is real work-in-progress to them. The invariant is
  about what the *volunteer* is told, not about the coordinator's arithmetic.
- **A volunteer releases a shift immediately; they do not request permission**
  (confirm). It mirrors crew withdrawal, and a schedule that shows someone who
  has already said no is worse than an open slot. The coordinator is DMed at
  once, and the volunteer is warned when they are inside the reminder lead.
- **Stated availability is a hard constraint for auto-fill** (confirm), with an
  explicit opt-in to fill outside it, and the result names everyone it placed
  outside their window. Hours get a ceiling (default 8 per volunteer per run,
  confirm), not a tiebreaker.
- **Changing a shift's start or end clears its acknowledgments** (confirm) and
  re-asks. Someone who agreed to 08:00–12:00 has not agreed to 16:00–20:00.
- **No new model, no migration, in any wave.** Every finding is served by fields
  that already exist (`auto_generated`, `acknowledged_at`, `VolunteerShift.notes`,
  `VolunteerPosition.description`). If a task seems to need a column, stop and
  ask — that is a sign it has grown past its finding.
- **No new feature flag.** The whole subsystem already sits behind
  `FeatureFlag.VOLUNTEERS`, whose spec covers `application/services/volunteer/`
  wholesale ([`application/feature_flags.py:136`](../../../application/feature_flags.py)),
  so new service methods in that package inherit the gate. Per CLAUDE.md step 0
  the question was asked and the answer is no: these are fixes to a gated
  feature, not a new one.

## What already works — do not regress it

The audit's headline is that the coordinator's surface is the best-designed admin
page in the app. Each wave's `Verify` re-checks these:

- The **assign picker**: per-candidate availability badge, `Qualified` badge, the
  unqualified filter that only appears when the position defines qualifications,
  and `No qualified volunteers available.` when the pool is genuinely empty
  ([`admin_volunteers.py:190-273`](../../../pages/admin_tabs/admin_volunteers.py)).
- **Soft-vs-hard failures in `assign`**: raises on already-assigned and on
  overlapping shifts, returns advisory warnings for overfilled and
  outside-availability
  ([`volunteer_schedule_service.py:208-264`](../../../application/services/volunteer/volunteer_schedule_service.py)).
  Wave 2 lifts its `_availability_warning` sentence into the bulk path; it must
  not change the manual path's behaviour.
- The **typed-phrase reset** (`yes please delete all shifts`) and the
  **delete-shift warning** that counts the assignments it will take with it.
- The **availability editor**'s event-window header, effective-availability graph
  and written precedence rule.
- The **roster page**, which already shows the qualifications and declared
  availability that wave 3's shift brief borrows.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit
most often:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service
(`application/services/`) → Repository (`application/repositories/`) → Models.
Presentation never imports repositories and never writes through the ORM;
services never import NiceGUI. `enforce_architecture.py` blocks violations at
write time. Two tasks here are tempting violations: the coverage strip (T4.2) must
extend `VolunteerScheduleService.coverage`, not query in the page, and the
coordinator DM fan-out (T3.1) reads `UserRoleRepository.list_users_with_role`
from the *service*, never from the page.

**Tenant scoping.** Repositories read via `scoped(Model.filter(...))` and write
with `tenant_id=current_tenant_id()`. `due_for_reminder` is deliberately
**unscoped** (the worker scans every tenant, then wraps each row in
`tenant_scope`) — the comment at
[`volunteer_assignment_repository.py:100-102`](../../../application/repositories/volunteer_assignment_repository.py)
says so; T1.1 adds a filter to it and must not add scoping.

**Errors.** Services raise `ValueError` for user-facing problems and
`PermissionError` for authorization. Presentation catches both and calls
`notify_error(e)` from `theme/notify.py`. `my_shifts.py` currently hand-rolls
`ui.notify(str(e), color='warning')` at
[`my_shifts.py:59-60`](../../../pages/volunteer_tabs/my_shifts.py) — collapse it
into `notify_error` when you touch that file in wave 3.

**Audit + events.** Every create/update/delete writes an audit row; when the
change has a matching `EventType`, use one `write_and_publish` call.
`check_dry_regressions.py` blocks a hand-rolled `write_log` + `event_bus.publish`
pair. This plan adds three `AuditActions` members and one `EventType` member —
each task says which, and says whether the action needs a mirror `EventType` or a
ledger entry in `_EVENT_CANDIDATES` / `_EXCLUDED_BY_DESIGN` in
[`tests/services/test_event_audit_parity.py`](../../../tests/services/test_event_audit_parity.py).
Get this wrong and `test_no_untriaged_audit_actions` fails.

**Discord.** Every DM is best-effort and must never raise: gate on
`discord_id` **and** `user.dm_notifications`, build the text in
`application/utils/discord_messages.py` and the card in
`application/utils/discord_embeds.py` (never inline either), and enqueue through
`discord_queue.enqueue(...)`. Copy the shape of
[`_request_acknowledgment`](../../../application/services/volunteer/volunteer_schedule_service.py#L360).
Verify with `MOCK_DISCORD=true` and read the DM log — see the `discord-ux` skill.

**NiceGUI.** `background_tasks.create(...)`, never `asyncio.create_task`. Capture
`context.client` before a background task that touches UI and restore it with
`with client:` (sync `with`). Never store per-user state at module level — the
grid's `state` dict lives inside the page function and must stay there; T4.1
moves its *persistence* to `tenant_session_*`, not to a module global.

**Mobile.** The volunteer grid is cards, not a `ui.table`, so the mobile-grid hook
does not apply — but T4.3 owns the phone layout and every wave's `Verify`
re-measures at 390×844. The roster page *is* a table with a bespoke `item` slot;
a change to one of its desktop cell slots needs the mirror change in that slot.

**Dev seed.** `scripts/seed_volunteers.py` is the fixture set every browser check
runs against. Wave 1 adds a draft assignment, wave 2 a volunteer with no declared
availability, wave 3 a shift with notes and a position with a description. Keep
each idempotent (`get_or_create`) and tenant-scoped like the rows around it.

**File length.** `check_file_length.py` advises over 800 lines and demands a split
over 1500. `pages/admin_tabs/admin_volunteers.py` is 409 lines and gains controls
in three of the four waves — if wave 4 pushes it past 800, extract the grid's card
rendering into `theme/` rather than letting it grow.

## Verification loop

Every task's `Verify` section assumes this is already running.

```bash
bash scripts/setup_env.sh                      # once per environment
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/default/login`: `staff_user` (STAFF +
VOLUNTEER_COORDINATOR, the coordinator), `player_one` / `player_three` (plain
volunteers), `proctor_user`. Pages live under `/t/default/…`; a bare `/admin`
404s. Chromium is at `/opt/pw-browsers` — **never run `playwright install`**.

**Drive both sides at once.** Every task that changes what a volunteer sees is
verified in two browser contexts in one script — `staff_user` on
`/t/default/admin/volunteers` and `player_one` on `/t/default/volunteer/my-shifts`
— acting as the coordinator and re-reading the volunteer's page without
re-logging-in. That two-context loop is what turned "drafts exist" into the
blocker; a single-session check will not reproduce these findings.

```bash
cat > /tmp/check.json <<'JSON'
{
  "loginAs": "staff_user",
  "tenant": "default",
  "outDir": "/tmp/ui-check",
  "targets": [
    { "name": "coordinator", "path": "/admin/volunteers" }
  ]
}
JSON
NODE_PATH=$(npm root -g) node scripts/ui_smoke.js /tmp/check.json
```

Add `"viewport": {"width": 390, "height": 844}` at the config top level for the
phone measurement. Read the resulting `.png` with the Read tool — a blank card or
a `console.error` means a broken template, which Python tests cannot catch. For
anything needing a click (a dialog, a publish), write a one-off Playwright script;
see the `ui-validation` skill for the login snippet.

Discord DMs:

```bash
grep -i 'DM to' /tmp/app.log | tail -20     # MOCK_DISCORD writes the DM log here
```

Tests:

```bash
poetry run pytest                                        # whole suite, parallel
poetry run pytest tests/services/ -k volunteer           # the subsystem
poetry run pytest -n0 -k draft                           # serial, for -s / pdb
scripts/ui_flag_sweep.sh                                 # flags-off sweep
```

## Definition of done for every task

1. The change is implemented in the files named, at the layer named.
2. `poetry run pytest` is green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot be written and why.
4. The affected page renders at 1500px **and** 390px, verified by screenshot, with
   no new console errors — and for anything touching the seam, verified from both
   sides at once per the loop above.
5. Any DM the task adds is confirmed in the `MOCK_DISCORD` log, with its copy
   quoted in the commit message.
6. Docs named in the task are updated.
7. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and say
explicitly what you left out and why.** Do not silently narrow scope.

## Open questions

Answer these before wave 1 starts. Each has a recommendation, and each changes
what gets built rather than how.

1. **Do drafts vanish from the volunteer's page, or appear labelled "proposed"?**
   *Recommended: vanish.* Labelled drafts mean the volunteer watches shifts appear
   and disappear with no notification either way.
2. **Can a volunteer drop a shift outright, or only ask to be released?**
   *Recommended: drop, with the coordinator DMed immediately* — the same
   capability crew signup already gives the same person.
3. **What is the auto-fill hour ceiling per volunteer per run?** *Recommended: 8,
   coordinator-editable in the auto-fill dialog.* The audit measured one person
   given 16 consecutive hours.
4. **Should moving a shift's time clear its acknowledgments and re-ask?**
   *Recommended: yes.*
5. **Does a released or removed shift need to reach anyone besides the
   coordinators** — a Discord channel post, say? *Recommended: no for now*; DM the
   `VOLUNTEER_COORDINATOR`/`STAFF` holders and let the new `volunteer.released`
   event carry it to any community that wants a webhook.

## When this directory is finished

`docs/README.md` states the convention: *design records are not kept after they
ship*. When the last wave merges, **delete `docs/plans/volunteer-hub/` and
[`docs/reviews/volunteer-hub-ux.md`](../../reviews/volunteer-hub-ux.md)**, drop
its row from the audit table in
[`docs/reviews/README.md`](../../reviews/README.md) and its entry from the "Work
in flight" table in [`docs/README.md`](../../README.md), and make sure the
behaviour they described now lives in the reference docs — principally
[`docs/reference/services.md`](../../reference/services.md) (the draft lifecycle,
`publish_draft`, `release`, the notification matrix) and
[`docs/reference/frontend.md`](../../reference/frontend.md#volunteer-hub-volunteer-pagesvolunteerpy)
(the volunteer hub section, which currently describes My Shifts as position +
time + Acknowledge). Also update the **cross-cutting themes** in
`docs/reviews/README.md`: "notification is one-directional" is half-fixed once
wave 3 lands, and the entry should say so rather than being deleted — the crew
half is still open.

Delete a wave file as its wave merges, rather than all four at the end — a
half-done plan left lying around reads as current work.
