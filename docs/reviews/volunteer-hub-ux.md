# Volunteer hub UX — evaluation

**Scope:** the volunteer subsystem from both sides — the coordinator's grid
([`admin_volunteers.py`](../../pages/admin_tabs/admin_volunteers.py)), the roster
([`admin_volunteer_roster.py`](../../pages/admin_tabs/admin_volunteer_roster.py)),
the volunteer's own tabs
([`volunteer.py`](../../pages/volunteer.py),
[`my_shifts.py`](../../pages/volunteer_tabs/my_shifts.py),
[`availability.py`](../../pages/volunteer_tabs/availability.py) over
[`theme/availability_editor.py`](../../theme/availability_editor.py)), and the
services ([`application/services/volunteer/`](../../application/services/volunteer/)).
The Proctor Station tab was audited and shipped in #146; commentator/tracker crew
is [crew-signup-ux.md](crew-signup-ux.md).

**Method:** read the services and repositories, then drove the running app against
a seeded `default` tenant as `staff_user` (coordinator-equivalent) and
`player_one` / `player_three` (plain volunteers), in parallel sessions so both
sides of each transition could be observed at once. Generated shifts for a future
event day, auto-filled from availability, watched what the volunteer saw, let the
volunteer acknowledge, then cleared the draft and looked again. Discord DMs were
counted from the `MOCK_DISCORD` DM log. Every number below is measured except
where marked **code-read**.

**Headline:** the coordinator's surface is the best-designed admin page in the
app — availability badges in the picker, a qualification filter, an auto-fill that
reports what it could not fill, a typed-phrase confirmation on the destructive
reset. The volunteer's surface is a receipt. And between the two sits the finding
that matters: **"draft" is a concept only the coordinator's screen honours.** The
autoscheduler's provisional assignments arrive on the volunteer's page as ordinary
shifts, with an Acknowledge button they can press, and vanish without a word when
the coordinator clears the draft.

---

## The measured shape

| | Desktop 1500×1000 | Mobile 390×844 |
|---|---:|---:|
| Coordinator grid (one event day, 4 positions, 20 shifts) | 1,586 px | 4,891 px |
| Volunteer My Shifts (4 shifts) | fits | fits (no horizontal overflow) |
| My Availability (3 windows + effective graph) | 1,000 px | — |
| Roster (5 volunteers, qualifications + availability) | 1,000 px | — |

Coordinator, per action:

| Action | Interactions | What it says |
|---|---:|---|
| Assign one volunteer by hand | 2 (Assign → row Assign) | `Player One has not marked this time as available.` ~ `Assigned Player One.` |
| Auto-fill a day | 1 | `Draft created: 16 assignment(s), 4 slot(s) still open (pool of 5).` |
| Clear the draft | 1 | `Cleared 16 draft assignment(s).` |
| Generate a position's standard shifts | 1 | `Generated shifts for Race Proctor (staggered where configured).` |

The assign picker (274–285 px) is genuinely good: each candidate carries an
availability badge (`Preferred` / `Available` / `Unavailable`), a `Qualified`
badge, and unqualified people are hidden behind a `Show unqualified volunteers`
checkbox that only appears when the position actually defines qualifications.

### The draft, from both sides at once

One auto-fill on 2026-07-31, observed simultaneously in two sessions:

| | Coordinator (`staff_user`) | Volunteer (`player_one`) |
|---|---|---|
| Assignments created | 16 | 4 of them are theirs |
| Marked as provisional? | **16 of 16** — outline chip + "Auto-generated draft" tooltip | **0 of 4.** The word draft/provisional/tentative/unconfirmed appears nowhere on the page |
| Discord DM | — | **none** (0 DMs for 16 drafts; 2 DMs for 2 manual assigns, from the mock DM log) |
| Can act on it? | edit / remove | **yes — "Acknowledge"** → *"Shift acknowledged."* |
| After the coordinator clicks **Clear draft** | `Cleared 16 draft assignment(s).` | 4 shifts → **0**, page reads *"You have no upcoming shifts."*, no notification of any kind |

What the volunteer's page showed, verbatim, for work nobody had told them about:

```
Check-in Desk — Shift 1   2026-07-31 08:00 EDT → 2026-07-31 12:00 EDT   [Acknowledge]
Check-in Desk — Shift 2   2026-07-31 12:00 EDT → 2026-07-31 16:00 EDT   [Acknowledge]
Check-in Desk — Shift 3   2026-07-31 16:00 EDT → 2026-07-31 20:00 EDT   [Acknowledge]
Check-in Desk — Shift 4   2026-07-31 20:00 EDT → 2026-08-01 00:00 EDT   [Acknowledge]
```

That is **16 consecutive hours**, assigned to one person, of which **12 fall
outside the availability they declared** (their roster entry reads
`Available: 2026-07-31 08:00–12:00 ET`).

---

## Root causes

### RC1 — The draft has no publish step, so `auto_generated` is honoured by exactly one widget

`generate_draft` writes assignments with `auto_generated=True`
([`volunteer_autoschedule_service.py:105-108`](../../application/services/volunteer/volunteer_autoschedule_service.py#L105)),
and `assign` skips both the DM and the event publish for them
([`volunteer_schedule_service.py:258-263`](../../application/services/volunteer/volunteer_schedule_service.py#L258)).
Nothing anywhere converts a draft into a confirmed assignment: there is no
publish method, no bulk notify, no flag flip. `clear_draft` is the only other
verb, and it deletes.

Meanwhile every consumer downstream ignores the flag:

| Consumer | Honours `auto_generated`? |
|---|---|
| Coordinator's chip ([`admin_volunteers.py:159-160`](../../pages/admin_tabs/admin_volunteers.py#L159)) | **yes** — outline + tooltip |
| `assignments_for_user` → My Shifts ([`volunteer_assignment_repository.py:67-71`](../../application/repositories/volunteer_assignment_repository.py#L67)) | no filter |
| My Shifts card ([`my_shifts.py:40-62`](../../pages/volunteer_tabs/my_shifts.py#L40)) | no marker |
| `acknowledge` ([`volunteer_schedule_service.py:284`](../../application/services/volunteer/volunteer_schedule_service.py#L284)) | accepts it |
| Reminder worker (`due_for_reminder`, [`:96-110`](../../application/repositories/volunteer_assignment_repository.py#L96)) | no filter — **code-read** |
| `delete_auto_for_window` ([`:80-94`](../../application/repositories/volunteer_assignment_repository.py#L80)) | deletes drafts regardless of acknowledgment |

So the coordinator's mental model ("this is a sketch I will review") and the
volunteer's ("this is my shift") are both correct, and they disagree.

### RC2 — Notification is one-directional (the same shape as crew)

Assigning DMs a well-built embed with an Acknowledge button
([`volunteer_schedule_service.py:360-393`](../../application/services/volunteer/volunteer_schedule_service.py#L360)).
Un-assigning notifies nobody (`:270-282`); clearing a draft notifies nobody;
editing a shift's time notifies nobody. Exactly the asymmetry
[crew-signup-ux RC3](crew-signup-ux.md#rc3--notification-is-one-directional)
found in the crew service, in a different subsystem.

### RC3 — The coordinator's page is a builder; the volunteer's is a receipt

`VolunteerPosition.description` and `VolunteerShift.notes` both exist, both are
editable (the shift dialog has a Notes field,
[`volunteer_shift_dialog.py:47`](../../theme/dialog/volunteer_shift_dialog.py#L47)),
and neither is rendered **anywhere** — not on the coordinator's shift card, not on
the volunteer's. The only place a coordinator can write down what a shift involves
is write-only.

### RC4 — The grid forgets which day you were on

`state = {'day': day_options[0]}` is rebuilt on every page render
([`admin_volunteers.py:54`](../../pages/admin_tabs/admin_volunteers.py#L54)) with
no URL parameter and no session storage. Measured: choose 2026-07-31, reload →
back to 2026-07-29; leave the tab and return → 2026-07-29. The match board solved
this with tenant-namespaced session keys (`_skey`,
[`theme/tables/match.py:105-124`](../../theme/tables/match.py#L105)).

---

## Findings, ranked

### F1 — Blocker · A draft shift is a real commitment to everyone except the coordinator

Measured above, both sides at once. The volunteer is shown four unmarked shifts
they were never told about, can acknowledge them, and then loses them silently
when the coordinator clears the draft — including the one they had just
acknowledged. Three consequences worth separating:

- **The volunteer cannot tell a sketch from a commitment.** No badge, no caption,
  no muted styling; the word "draft" is measured absent from the page.
- **Acknowledgment is meaningless on a draft.** The volunteer's confirmation is
  accepted and then deleted by `delete_auto_for_window`, which does not check
  `acknowledged_at`.
- **The first DM a volunteer receives about a draft shift will be the reminder.**
  `due_for_reminder` filters on `reminder_sent_at IS NULL` and the shift's start
  time only — nothing excludes drafts (**code-read**; the reminder worker was not
  driven). So a provisional assignment's debut in the volunteer's DMs is
  "your shift starts soon".

### F2 — Critical · Auto-fill assigns outside stated availability and without an hours cap, and says neither

`_pick` skips only an explicit `UNAVAILABLE` and otherwise ranks candidates by
`(qualified, availability rank, hours so far, name)`
([`volunteer_autoschedule_service.py:141-164`](../../application/services/volunteer/volunteer_autoschedule_service.py#L141)) —
so "has not said they can work this" is a **tiebreaker**, and `hours` is a
tiebreaker too, not a ceiling. Measured consequence: one volunteer given four
consecutive blocks, 16 hours, 12 of them outside their declared window.

The summary the coordinator gets — `16 assignment(s), 4 slot(s) still open (pool
of 5)` — reports quantity only. The **manual** path surfaces exactly the warning
that is missing here (`_availability_warning`, measured as
*"Player One has not marked this time as available."*), so the service already
computes the sentence the bulk path never shows. Nothing flags a
longest-shift-run either.

### F3 — Critical · A volunteer cannot decline, hand back, or swap a shift

`my_shifts.py` renders exactly one control: **Acknowledge**
([`:55-62`](../../pages/volunteer_tabs/my_shifts.py#L55)). There is no decline, no
"I can't make this", no swap request, and `unassign` is coordinator-only
([`volunteer_schedule_service.py:270-274`](../../application/services/volunteer/volunteer_schedule_service.py#L270)).
A commentator can withdraw from a crew slot in two clicks
([crew-signup-ux F3](crew-signup-ux.md#f3--critical--an-approved-commitment-evaporates-in-two-clicks-and-nobody-is-told)) —
the same person, doing the same kind of favour, through a different door, cannot.
The only exit is to find a coordinator out-of-band, which means the schedule the
grid shows is more confident than the truth.

### F4 — Major · The shift never says what the shift is

Measured card contents: position name, optional label, start → end, badges,
Acknowledge. Not shown: the shift's notes, the position's description, where to
be, who to report to, what to bring, or who else is on with them. Both text
fields exist in the model and are captured by the coordinator's dialogs (RC3).
For a first-time volunteer this card is the entire brief.

### F5 — Major · Removing a volunteer from a shift tells them nothing

`unassign` audits and publishes an event, and sends no DM (RC2). The volunteer's
shift simply disappears from My Shifts on their next visit. Combined with F3, a
volunteer's schedule can change in both directions without a single message
either way.

### F6 — Minor · The event-day selection resets to day one

RC4, measured three times (load → choose last day → reload → day one; navigate
away → return → day one). On a three-day event this is a small tax; on a longer
one, or when combined with auto-fill (which acts on *the selected day's* window),
it is a way to auto-fill the wrong day.

### F7 — Minor · The auto-fill result is a toast, and the only record of what it did

`Draft created: 16 assignment(s), 4 slot(s) still open (pool of 5)` is accurate
and disappears in seconds. `_unfilled_summary` computes per-shift open counts
that the page throws away — the coordinator has to re-read the grid's `n/m`
badges to find the four open slots. The audit log records `created` only.

### F8 — Minor · The coordinator's grid is 4,891 px on a phone

No horizontal overflow (good), but four positions × five shift cards each becomes
a 5.8-screenful vertical scroll with no day-at-a-glance summary and no coverage
strip — the one number a coordinator wants on-site ("how many slots are still
open right now?") is not on the page in any form.

---

## What works

Keep all of this through any remediation:

- **The assign picker** — availability badge per candidate, `Qualified` badge, the
  unqualified filter that only appears when qualifications exist, and
  `No qualified volunteers available.` when the pool is genuinely empty.
- **Soft-vs-hard failures.** `assign` raises on already-assigned and on
  **overlapping shifts**, and returns advisory warnings for overfilled and
  outside-availability. This is the double-booking check the crew path lacks
  entirely; it should be lifted, not reinvented.
- **The auto-fill's honesty about what it could not do** — open-slot count and
  pool size in the same sentence.
- **The reset confirmation**: typing `yes please delete all shifts`, with the
  irreversibility spelled out. The most careful destructive-action UI in the
  codebase.
- **Delete-shift warning** that counts the assignments it will take with it.
- **The availability editor** — `Event window: 2026-07-29 → 2026-07-31
  (US/Eastern)`, an effective-availability graph, and the precedence rule written
  out (*"Where windows overlap, Unavailable beats Preferred beats Available"*).
- **The roster page**, which already shows qualifications and declared
  availability per volunteer — the data F4's card is missing.

## Not covered

The reminder worker's live behaviour (F1's third bullet is code-read), the CSV
export's contents, `VolunteerQualification` management beyond seeing it in the
picker, and the Discord acknowledge-button path.
