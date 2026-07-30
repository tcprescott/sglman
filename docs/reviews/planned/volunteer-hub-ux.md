# Brief — Volunteer hub UX

**Recommended next.** Scope, method and leads for an audit nobody has run yet.
Leads below are unverified suspicions from reading the code; the audit confirms or
refutes each one against the running app.

## Scope

The volunteer subsystem from both sides:

- **Volunteer's own surface** — [`pages/volunteer.py`](../../../pages/volunteer.py)
  and its tabs: `My Availability`
  ([`volunteer_tabs/availability.py`](../../../pages/volunteer_tabs/availability.py),
  an 11-line wrapper over
  [`theme/availability_editor.py`](../../../theme/availability_editor.py)),
  `My Shifts` ([`volunteer_tabs/my_shifts.py`](../../../pages/volunteer_tabs/my_shifts.py)),
  plus the opt-in path and the reminder DMs.
- **Coordinator's surface** — [`admin_volunteers.py`](../../../pages/admin_tabs/admin_volunteers.py)
  (the day grid, shift generation, the assign picker),
  [`admin_volunteer_roster.py`](../../../pages/admin_tabs/admin_volunteer_roster.py),
  and the four dialogs (`volunteer_shift_dialog`, `volunteer_position_dialog`,
  `volunteer_profile_dialog`, `volunteer_export_dialog`).
- **Services** — [`application/services/volunteer/`](../../../application/services/volunteer/):
  profile, availability, positions, schedule, autoschedule, qualification,
  export, reminders.

Out of scope: the Proctor Station tab (audited and shipped in #146), and
commentator/tracker crew, which is a different subsystem —
[crew-signup-ux.md](../crew-signup-ux.md).

## Why this one

- **The surface is lopsided in a way that usually means the thin side was never
  designed.** Coordinator tooling is ~625 lines plus four dialogs; the
  volunteer's own three tabs total ~186 lines, one of which is an 11-line
  delegation.
- **It is the second-most-visited path in production.** `/volunteer` shows 7 views
  across 3 distinct users against `/admin`'s 53 across 2 (telemetry for `sgl26`,
  read at audit-scoping time — the tenant is pre-event, so this ranks surfaces
  rather than proving traffic).
- **Volunteers are assigned work by a machine.** `volunteer_autoschedule_service`
  places people into shifts; the question an audit answers is whether the person
  on the receiving end can tell what they were given, why, and what they owe.

## What to measure

1. **Coordinator: staffing one event day.** Interactions from an empty day to a
   fully-covered one — generate shifts for a position, then assign N volunteers.
   Count per assignment, and measure the assign dialog: does the picker show each
   candidate's availability, their existing load, and their qualifications, or
   just a name list? Measure the day grid's scroll height at a realistic shift
   count (extend `seed_dev.py` if the fixtures are too thin, and say so).
2. **`assign()` returns `(assignment, soft warnings)`**
   ([`volunteer_schedule_service.py:208-251`](../../../application/services/volunteer/volunteer_schedule_service.py#L208)).
   Find where those warnings render, and whether a coordinator can act on them.
   Note the contrast worth checking: hard failures include
   `overlapping_for_user` — **volunteer shifts have the double-booking check that
   crew signup lacks entirely.** If it works well here, it is the model for the
   crew fix.
3. **Volunteer: the full arc.** Opt in → set availability → get assigned (both by
   hand and by the autoscheduler) → acknowledge → check in. Count interactions,
   capture every notification verbatim, and note at each step whether the
   volunteer can tell what happens next.
4. **The availability editor's legibility.** It encodes a real precedence rule
   (`Unavailable beats Preferred beats Available`,
   [`availability_editor.py:145`](../../../theme/availability_editor.py#L145)) and
   renders an "Effective availability" graph. Measure whether a volunteer can tell
   what the windows are *for* — the help text is one line, "Add the windows you can
   work" — and whether the same editor serves player availability without
   confusing the two.
5. **Reminders.** `volunteer_reminder.py` sends DMs; establish what fires, when,
   and whether the web surface says anything about them.
6. **Both surfaces at 390×844.** Volunteers work from phones on-site.

## Leads to verify

- The volunteer's tabs are gated on `is_volunteer or is_staff`, with a comment
  saying they are "safe (and empty) for someone who volunteers for nothing"
  ([`volunteer.py:30-37`](../../../pages/volunteer.py#L30)) — check what a
  volunteer-role user with no shifts and no availability actually sees, and whether
  anything invites them to do the first thing.
- Auto-generated assignments carry `auto_generated=True`. Check whether that is
  ever surfaced — a volunteer being told "you were scheduled automatically" reads
  differently from "a coordinator picked you".
- `volunteer_qualification_service` exists; verify whether a volunteer can see
  which qualifications they hold or need, or only the coordinator can.
- My Shifts filters to upcoming by default with a toggle
  ([`my_shifts.py:22-40`](../../../pages/volunteer_tabs/my_shifts.py#L22));
  check whether a past shift they never checked into is distinguishable from one
  they worked.
- `VolunteerExportDialog` is the coordinator's data-out path; check whether it
  duplicates something the roster page could show directly.

## Fixtures and roles

`scripts/seed_dev.py` seeds volunteers and shifts. Drive as: `staff_user`
(coordinator-equivalent — note `staff_user` also holds VOLUNTEER_COORDINATOR),
`player_three` (plain VOLUNTEER), and a **VOLUNTEER_COORDINATOR-only** account,
which the seed does not create — grant it by hand and record that as a seed gap
(the two completed audits both found their headline in a role the seed cannot
produce).

## Deliverable

`docs/reviews/volunteer-hub-ux.md`, in the shape of the two completed audits:
measured shape table, root causes, findings ranked with `file:line` evidence, a
"what works" section, and an explicit "not covered". Do not fix anything in the
same pass.
