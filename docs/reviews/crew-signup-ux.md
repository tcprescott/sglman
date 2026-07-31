# Crew signup and approval UX — evaluation

**Scope:** the two-party crew loop — a volunteer signing up to commentate or
track a match, an admin approving it, the volunteer acknowledging, and either
side backing out. That is the crew cells of the match table
([`match_slots.py:364-401`](../../theme/tables/match_slots.py#L364),
[`match_grid.py:116-155`](../../theme/tables/match_grid.py#L116)), the handlers
behind them
([`match_handlers.py:105-184`](../../theme/tables/match_handlers.py#L105)),
[`theme/dialog/approve_crew_dialog.py`](../../theme/dialog/approve_crew_dialog.py),
[`application/services/crew_service.py`](../../application/services/crew_service.py),
the volunteer-facing board
([`home_tabs/schedule.py`](../../pages/home_tabs/schedule.py) — titled "Schedule
& Crew Signup") and the coverage report
([`reports/crew.py`](../../pages/admin_tabs/reports/crew.py)). The board these
share with match scheduling is evaluated in
[match-operations-ux.md](match-operations-ux.md).

**Method:** read the service, the auth gates and both slot templates, then drove
the running app against a seeded `default` tenant — signed up as `player_three`,
approved as `staff_user`, looked for the signup from both sides afterwards,
withdrew an approved commitment, and re-measured on mobile. The
crew-coordinator-only case needed a role granted by hand in the dev DB (the seed
has no such user; see [match-operations-ux F9](match-operations-ux.md#f9--minor--the-dev-seed-cannot-reproduce-the-two-role-failures-above)).
Every number is measured.

**Headline:** the service layer models this correctly — signup, approval,
acknowledgment and revocation are four distinct transitions with the right
guards, and approval sends a real Discord DM with an Acknowledge button. The UI
models it as a table cell. Neither party gets a queue, a list of their own
commitments, or a notification when the other party acts; a pending signup is
communicated to staff **by text colour and nothing else**; and the one role whose
entire purpose is approving crew cannot approve crew.

---

## The measured shape

Signing up (as `player_three`, home board → Schedule & Crew Signup):

| Step | Interactions | What it says |
|---|---:|---|
| Click **Sign up** on a row's Commentators cell | 1 | — |
| Confirm | 1 | *"Do you want to sign up as a commentator for match ID 17?"* → No / Yes |
| — | | *"Successfully signed up as a commentator for match ID 17. Awaiting approval."* |
| **Total** | **2** | |

Approving it (as `staff_user`, admin Schedule board):

| Step | Interactions | What it says |
|---|---:|---|
| Find the pending name | — | nothing marks it but `.st-pending` colour |
| Click the name | 1 | dialog: *"Approve Commentator · Name: Player Three · ☐ Approved · Cancel · Save"* (270 px, 5 controls) |
| Tick Approved | 1 | |
| Save | 1 | *"Commentator approval updated."* |
| **Total** | **3, per person** | |

Two more pending signups sat on the same board: 6 more interactions, no bulk path.

Where the work is visible, measured on the seeded tenant:

| Surface | Shows pending crew? | Can approve? |
|---|---|---|
| Admin Schedule board | only as `.st-pending` text colour on the name — the words "pending" / "awaiting approval" appear **nowhere** on the page | yes (staff/TA only) |
| Reports → Staff / Crew Activity, *Pending only* | yes, with a coverage-gap column | **no** — both tables measured 0 buttons and 0 links in their bodies |
| Discord | no DM on signup | — |
| The volunteer's own pages | Withdraw button on one row of a 17-row board | — |

The volunteer's side, measured:

| | Desktop 1500×1000 | Mobile 390×844 |
|---|---:|---|
| Rows / cards on the crew board | 17 | 17 cards, 311 px each |
| Page scroll | 1,542 px | **5,874 px** |
| "Sign up" buttons offered | **28** | 48 buttons in cards |
| Mentions of the volunteer's own signups on the Player tab | **0** | 0 |

Where those 28 offers land, by match state (default filter, so Finished and
Confirmed rows are not shown):

| Row state | Rows | "Sign up" buttons offered |
|---|---:|---:|
| Scheduled | 11 | 20 |
| Checked In | 3 | **6** |
| Started | 3 | **2** |

---

## Root causes

### RC1 — A two-party workflow rendered as a cell

Everything about crew happens inside one `<td>` of a shared, chronologically
sorted board: the volunteer's Sign up / Withdraw buttons, their acknowledge
button, the admin's approval link and every crew member's status icon all live in
`CREW_SLOT` ([`match_slots.py:364`](../../theme/tables/match_slots.py#L364)).
Consequences follow mechanically: neither party can see *their* items without
scanning every row, there is nowhere to put a count, and the same control
(Withdraw) has to serve both "I changed my mind before anyone noticed" and "I am
dropping a commitment staff already approved and announced".

The house already knows the other shape. Volunteers get **My Shifts**
([`volunteer_tabs/my_shifts.py`](../../pages/volunteer_tabs/my_shifts.py)) — a
list of their own commitments with acknowledge and check-in on each card. Staff
get the **review queue** strip for results
([`admin_schedule.py:59-98`](../../pages/admin_tabs/admin_schedule.py#L59)) — a
count of three kinds of work with a one-click filter to them. Crew has neither,
on either side.

### RC2 — Demand is unmodelled, so the UI can never say "wanted" or "covered"

There is no crew capacity anywhere in the data model: `Match` carries
`is_stream_candidate` and nothing else about crew
([`models/match.py:20`](../../models/match.py#L20)); `Commentator` and `Tracker`
are bare join rows. So every row offers signup to everyone, always — 28 offers on
a 17-row board — and no row can distinguish "needs two commentators" from "fully
covered" from "not being streamed". Coverage exists only as a *report-time*
computation (`coverage_gap`, `commentators_approved/total` in
[`reports/crew.py:110-140`](../../pages/admin_tabs/reports/crew.py#L110)), which
is why the only surface that knows about gaps is the one that cannot act on them.

### RC3 — Notification is one-directional — **closed**

Both reverse transitions now speak. Un-approving DMs the crew member
(`_notify_crew_approval_withdrawn`), and withdrawing an *approved* commitment
DMs the people who can refill it — the tournament's admins and crew
coordinators plus whoever approved it — with the hours of notice they have
(`_notify_crew_withdrawal`, the shape
`VolunteerScheduleService._notify_coordinators_of_release` established). An
*unapproved* signup still withdraws silently, on purpose: nobody was told it
existed, so its removal corrects nothing.

The original finding, for the record:

`update_crew_approval` sends a well-built DM — colour-coded embed, match, time,
stage, players, and an Acknowledge button
([`crew_service.py:273-320`](../../application/services/crew_service.py#L273)).
Every other transition is silent to the other party: signup notifies no
coordinator (`:87-94` audits and publishes an event, no DM), withdrawal notifies
nobody (`:133-140`), and un-approving notifies the volunteer of nothing
(`:179-207`). The event bus carries all of them, so webhooks can see what the
humans cannot.

### RC4 — Approval authority is defined in the service and discarded by the board

`can_approve_crew` admits staff, the tournament's admin, **and the tournament's
crew coordinator**
([`auth_service.py:227-232`](../../application/services/auth_service.py#L227)).
The approval link renders only when `__IA__ && __CC__`
([`match_slots.py:386`](../../theme/tables/match_slots.py#L386)), and `__CC__` is
`can_crud = is_staff or is_ta_any` ([`pages/admin.py:121`](../../pages/admin.py#L121)).
Shared root cause with
[match-operations-ux RC1](match-operations-ux.md#rc1--can_crud-is-one-boolean-standing-in-for-six-capabilities).

---

## Findings, ranked

### F1 — Blocker · The crew coordinator cannot approve crew

Measured with a coordinator-only account (crew coordinator of Wizzrobe Cup, no
other role): the admin Schedule board loads all 20 matches, and the crew names in
them are **plain text — 0 approval links**. The service would have allowed every
one of those approvals (RC4). What the board does offer them is 37 lifecycle
controls that all refuse; see
[match-operations-ux F1](match-operations-ux.md#f1--blocker--a-crew-coordinators-board-is-37-controls-that-all-refuse-and-none-they-may-use).

A per-tournament crew coordinator exists in the data model, in `AuthService`, in
the user-edit dialog that grants it
([`user_edit_dialog.py:293`](../../theme/dialog/user_edit_dialog.py#L293)) and in
the admin-tab gate that admits them
([`pages/admin.py:127`](../../pages/admin.py#L127)). The one thing the role is for
is the one thing it cannot do.

### F2 — Critical · Nothing tells anyone that a signup is waiting

Measured on the admin board with three pending signups on it: the strings
"pending", "awaiting approval" and "to approve" appear nowhere in the page text.
The only signal is the CSS class `.st-pending` on the crew member's name — the
same class the overdue-timestamp cell uses
([`match_slots.py:60`](../../theme/tables/match_slots.py#L60)), so six elements on
that board carried it and three of them were not crew. There is no count, no
chip, no filter, and no DM to a coordinator.

The volunteer is told *"Awaiting approval"* once, in a toast that disappears in
seconds, and is then given no way to learn whether it ever happened except to
re-find the row (F5) or wait for a Discord DM that only arrives if someone
happens to notice the colour.

Reports → Staff / Crew Activity has a **Pending only** filter and a coverage-gap
column, and is the right place to *discover* this work — but measured 0 buttons
and 0 links in both table bodies, it is a dead end for acting on it, and it is
date-range scoped rather than "everything outstanding".

### F3 — Critical · An approved commitment evaporates in two clicks, and nobody is told — **fixed**

The withdrawal now reaches the crew owners (RC3), and the dialog stops treating
the two withdrawals as the same act: dropping an approved slot is titled
**Withdraw as commentator**, confirms in the negative tone, and says *"Staff
approved you for this slot — they will be told you have withdrawn so they can
find cover."* Un-approving already confirmed and DMed.

`undo_crew_signup` is allowed until `finished_at` and does not care whether the
signup was approved
([`crew_service.py:96-140`](../../application/services/crew_service.py#L96)).
Measured: after approval, Withdraw → *"Are you sure you want to remove yourself
as a commentator for match ID 17?"* → Yes → gone. Same copy as withdrawing an
unapproved signup, no mention that staff approved it, and no notification to the
admin who did. A commentator can drop a stream match minutes before it starts and
the only trace is an audit row and a webhook.

The reverse is equally silent: un-ticking Approved clears the volunteer's
`acknowledged_at` and saves, with **no DM** telling them they are off the match
(`:179-207`) — while the approval that put them on it did send one. The dialog is
titled "Approve Commentator" and is in fact a two-way toggle.

### F4 — Major · Every message names a database id, not a match — **fixed**

[`application/utils/match_labels.py`](../../application/utils/match_labels.py)
names a match the way the Discord side already did — *"Alice vs Bob (Wizzrobe
Cup, 2025-08-03 19:00)"* in a dialog that has to be decided, the matchup alone
in a toast that answers a click. Every crew, acknowledgment and watch string on
the board and in the match dialog reads from it, and
`test_no_crew_or_watch_copy_quotes_a_match_id` keeps the id from coming back.

Measured strings, verbatim: *"Do you want to sign up as a commentator for match
ID 17?"*, *"Successfully signed up as a commentator for match ID 17. Awaiting
approval."*, *"Are you sure you want to remove yourself as a commentator for match
ID 17?"*, *"You have been removed as a commentator for match ID 17."* The row that
was clicked knows the tournament, the scheduled time and both players; the DM
built by the same service uses exactly those three
([`crew_service.py:288-307`](../../application/services/crew_service.py#L288)).
The web copy is the only place that talks in primary keys.

### F5 — Major · A volunteer has no record of what they signed up for

Measured: the Player tab ("Your Schedule") contains no mention of commentator,
tracker or crew — its board is players-only
([`home_tabs/player.py`](../../pages/home_tabs/player.py)). There is no
My Commitments anywhere. After signing up, the volunteer's only handle on the
commitment is a Withdraw button in one row of a 17-row board — 5,874 px of scroll
on a phone — and their only reminder is the approval DM, if approval happens.

Volunteers who work *shifts* have exactly this page already: My Shifts, with
acknowledge and check-in per card. Commentators and trackers are the same people
doing the same kind of work through a different door.

### F6 — Major · Signup is offered where it cannot help, and never says what is wanted — **half fixed**

Signup now closes when the match *starts*: `CrewService.signup_crew` refuses it
(so the REST route and the Discord button honour it too) and the row carries
`crew_signup_open` — the same predicate, not a second spelling — which both the
table cell and the mobile card gate their Sign up control on. Checked In stays
open deliberately: that is exactly when a stream discovers it still needs a
commentator. **The second half is untouched** — nothing marks a match as
*wanting* crew, because demand is unmodelled (RC2).

Measured: 8 of the 28 offers are on matches that have already begun — 6 on
Checked In rows, 2 on Started rows — because the only ceiling in the service is
`finished_at`
([`crew_service.py:69-70`](../../application/services/crew_service.py#L69)) and
the cell applies no state condition at all (contrast `SEED_ROLLABLE` and
`STATE_SLOT`, which are careful about exactly this). The signup I made for this
audit was on a match in the **Started** state, and it succeeded, and it said
"Awaiting approval" about a match that would be over before anyone read it.

Conversely nothing marks a match as *wanting* crew (RC2): a stream-candidate
match with no commentators looks identical to a non-streamed one with none, and
a fully covered match still shows Sign up. The volunteer cannot tell where help
is needed; the report can, and they cannot see it.

### F7 — Major · Approval is per-person, three clicks, and decided without any context

[`ApproveCrewDialog`](../../theme/dialog/approve_crew_dialog.py) shows one line —
`Name: Player Three` — plus the checkbox. Measured 270 px, 5 controls. It does not
show which match, when, which stage, who else is on it, or whether this person is
already committed to a different match at the same time. **No conflict check
exists anywhere** in the crew path (`crew_service` has none; the only
overlap-aware code in the codebase is `MatchSuggestionService`, for player
availability). A coordinator staffing a stream day approves N people, three
clicks each, from a dialog that tells them nothing they need in order to decide.

### F8 — Minor · The confirmation budget is spent on the reversible action — **fixed**

Revoking an approval now confirms, in the negative tone, and names the
acknowledgment it clears and the DM it sends. Withdrawing an approved commitment
confirms differently from withdrawing an unapproved one (F3). Signing up keeps
its modal — one click on a shared board is easy to hit by accident — but it is
no longer the *heaviest* confirmation on the surface.

The original finding, for the record: signing up — free, reversible, low-stakes
— got a modal confirm. Withdrawing an approved commitment got the same modal,
with the same weight. Revoking someone else's approval got none, and neither did
the acknowledgment-clearing side effect that came with it.

### F9 — Minor · Acknowledge is an unlabelled icon — **fixed**

The control now reads **Acknowledge** in both the table cell and the mobile
card, with the tooltip demoted to the explanation ("Confirm you can cover this
commentator slot") rather than the only label.

Measured buttons on an approved crew row: `undo Withdraw`, **`check`**,
`assignment_ind Sign up`, `notifications_none`. The acknowledge control is a bare
`check` icon whose only explanation is a `q-tooltip`
([`match_slots.py:393-397`](../../theme/tables/match_slots.py#L393)) — and the
proctor-board work already established that tooltips never open on the tablets
this gets read on
([`match_slots.py:349-352`](../../theme/tables/match_slots.py#L349) records
exactly that lesson for the Stations button).

---

## What works

- **The approval DM** — embed with match, players, time and stage, plus an
  Acknowledge button that works from Discord
  ([`crew_service.py:273-320`](../../application/services/crew_service.py#L273)).
  Everything F2–F5 asks for already exists here; it is one transition out of four.
- **The service's guards**: players can't crew their own match, signup closes at
  finish, double-signup is refused, only the assignee may acknowledge,
  acknowledgment requires approval, an unchanged checkbox is a no-op that neither
  audits nor DMs, and approval re-reads the row from the DB to narrow the
  two-admin race.
- **The coverage report's shape** — approved/total per match, coverage gaps,
  contribution per person, CSV export. It is the right data; it is on the wrong
  page.
- **The mobile card's crew line** — `v-if`-gated so an empty crew row collapses
  for admins but still offers signup to a volunteer
  ([`match_grid.py:116-155`](../../theme/tables/match_grid.py#L116)).

## Not covered

Volunteer *shifts* (positions, the auto-scheduler, roster export) — that is a
separate subsystem, audited and since remediated (see
[docs/reference/services.md](../reference/services.md#volunteering) for the
notification matrix this audit's RC3 still needs). Restream/tracker
tooling outside Wizzrobe, and the Discord button path beyond confirming that the
approval DM carries one.
