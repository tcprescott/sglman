# Match operations UX — evaluation

**Scope:** the admin Schedule board and the match dialog — creating, editing and
role-gated operation of a `Match`. That is
[`pages/admin_tabs/admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py),
[`theme/tables/match.py`](../../theme/tables/match.py) with its slot modules
([`match_slots.py`](../../theme/tables/match_slots.py),
[`match_grid.py`](../../theme/tables/match_grid.py)), the handler mixin
([`match_handlers.py`](../../theme/tables/match_handlers.py)), the lifecycle
callbacks ([`match_lifecycle.py`](../../theme/tables/match_lifecycle.py)) and
[`theme/dialog/match_dialog.py`](../../theme/dialog/match_dialog.py) — the
largest file under `pages/` + `theme/`. Crew signup and approval share this board
and are evaluated separately in
[crew-signup-ux.md](crew-signup-ux.md); the proctor's board and result recording
were audited previously and shipped (PR #146), so they appear here only where
the schedule board depends on them.

**Method:** read the match services, the auth gates and every slot template,
then drove the running app in a headless browser against a seeded `default`
tenant — created a match from scratch, probed the required-field, no-enrolled-players
and concurrent-edit paths, opened the edit dialog on a finished-and-disputed
match, and re-measured every board as **four different roles**: `staff_user`,
`sm_user` (STREAM_MANAGER), `proctor_user`, and a crew-coordinator-only account
(granted temporarily in the dev DB, since the seed has no such user — see F9).
Every number below is measured at 1500×1000 desktop and 390×844 mobile.

**Headline:** the service layer knows exactly who may do what — `can_run_match`,
`can_confirm_match`, `can_assign_match_stream`, `can_approve_crew` are four
separate, carefully-reasoned gates. The board compresses all four into one
boolean, `can_crud`, and then renders controls off callback presence. The result
is not a board that shows too little; it is a board that shows the **wrong set**
to everyone except staff. A crew coordinator is handed 37 controls that every
one of them refuses, and none of the one they are authorized for. The
Stream Manager — the role `assign_stage` names in its own docstring — cannot
reach the board at all.

---

## The measured shape

Admin Schedule as `staff_user`, seeded `default` tenant, default state filter:

| | Desktop 1500×1000 | Mobile 390×844 |
|---|---:|---:|
| Rows / cards | 20 | 20 |
| Page scroll | 1,709 px (1.7 screenfuls) | 6,912 px (**8.2 screenfuls**) |
| Interactive controls in the table body | 53 buttons + 35 links | 48 buttons in cards |
| Per row | ≈4.4 controls | 451 px of card |

Creating one match (2 players, default date/time, no stage, no crew, no comment):

| Step | Interactions |
|---|---:|
| Open Create Match | 1 |
| Tournament select + option | 2 |
| Players select + 2 players + dismiss menu | 4 |
| Create | 1 |
| **Total** | **8** |

The dialog itself, measured:

| | Create | Edit |
|---|---:|---:|
| Card scroll height | 853 px in an 846 px card | **1,008 px in an 846 px card** |
| Inputs / selects / checkboxes / textareas | 10 / 6 / 2 / 1 | 10 / 6 / 2 / 1 |
| Buttons | 4 | **11** |

The edit dialog scrolls on a 1000 px desktop: the five Clear buttons, the Player
Acknowledgments block and the racetime section are all below the fold on open.
Its footer is `Delete · Cancel match · Cancel · Save` — two destructive actions,
one of which is one word away from the button that closes the dialog.

### The same board, by role

| Role | Schedule tab? | ID/edit link | Crew approval links | Lifecycle buttons offered | Of those, permitted |
|---|---|---:|---:|---:|---:|
| `staff_user` (STAFF) | yes | 20 | 3 | all | all |
| crew coordinator only | yes | **0** | **0** | **37** | **0** |
| `sm_user` (STREAM_MANAGER) | **no tab at all** | — | — | — | — |
| `proctor_user` (PROCTOR) | 403 on `/admin` | — | — | — | — (uses `/volunteer` → Proctor Station) |

The coordinator's 37 = 15 `Stations` + 12 `Generate` + 7 `Check In` + 3 `Start`.
Two were clicked to verify rather than inferred:

- `Generate` → *"You do not have permission to roll a seed for this match"*
- `Check In` → opens the full check-in dialog, station pickers and all; only
  after filling it in and confirming: *"User cannot assign stations for match 15"*

---

## Root causes

### RC1 — `can_crud` is one boolean standing in for six capabilities

[`pages/admin.py:121`](../../pages/admin.py#L121) computes
`can_crud = is_staff or is_ta_any`, and
[`match_lifecycle.py:80-99`](../../theme/tables/match_lifecycle.py#L80) uses it
to decide, in one go, whether to pass `on_edit`, `on_confirm`, `on_edit_result`
and `on_edit_stream_room`. The slot templates then key off callback presence
([`match.py:307-322`](../../theme/tables/match.py#L307)) and off `__CC__`
directly ([`match_slots.py:161`](../../theme/tables/match_slots.py#L161),
`:386`).

Meanwhile the services distinguish:

| Service gate | Admits | Board control |
|---|---|---|
| `can_run_match` ([`auth_service.py:203`](../../application/services/auth_service.py#L203)) | staff, **proctor**, tournament admin | Check In / Start / Finish / Generate |
| `can_confirm_match` (`:215`) | staff, tournament admin | Confirm |
| `can_assign_match_stream` | staff, **stream manager**, tournament admin | Assign stage |
| `can_approve_crew` (`:227`) | staff, tournament admin, **crew coordinator** | crew name link |
| `is_staff` only ([`station_service.py:44`](../../application/services/station_service.py#L44)) | staff | Stations |

Four distinct audiences, one boolean. Every mismatch in the role table above
falls out of this single line, and none of them is a bug in the service layer.

### RC2 — Controls are rendered from what the service *exposes*, not from what this match *is in*

The board is state-aware exactly once — `STATE_SLOT`
([`match_slots.py:107-207`](../../theme/tables/match_slots.py#L107)) is a
genuinely careful state machine, and the recently-shipped proctor work added the
`No result` / `Needs review` chips to it. The **dialog** is state-blind: nothing
in `AdminMatchDialog.open()`
([`match_dialog.py:373-556`](../../theme/dialog/match_dialog.py#L373)) reads
`state`, `finished_at`, `needs_review` or the recorded winner. Opening the edit
dialog on match 8 — Finished, flagged **NEEDS REVIEW**, with a winner already
recorded and a proctor's dispute note — shows none of those four facts. What it
does show is a Comment field, five Clear buttons, and the sentence *"No players
assigned."*

### RC3 — Enrollment is the dialog's hidden precondition, and it is enforced after submit

The Tournament select is fed by `get_all_tournaments()`
([`match_dialog.py:376`](../../theme/dialog/match_dialog.py#L376)); the Players
select is fed by the tournament's *enrolled* players (`:436-485`). Nothing
reconciles the two, so a tournament with nobody enrolled is offered, selectable,
and silently un-schedulable. `UserMatchDialog` already solved the same problem
for players with `list_player_requestable` (`:650`) and even explains itself in a
comment: *"this keeps the dropdown from offering a choice that can only fail."*
The admin dialog never got that treatment.

### RC4 — The two read-only board copies were never migrated to the shared slots

[`match_slots.py:232-312`](../../theme/tables/match_slots.py#L232) defines
`SEED_SLOT_READONLY` and `state_readonly_slot()` explicitly *"so pages can drop
their inline templates"*. **Both have zero callers.** The home schedule
([`home_tabs/schedule.py:41-108`](../../pages/home_tabs/schedule.py#L41)) and the
player dashboard ([`home_tabs/player.py:191-245`](../../pages/home_tabs/player.py#L191))
each still carry their own copy of the same two cells — three divergent copies of
one state cell, in a layer with no automated coverage.

---

## Findings, ranked

### F1 — Blocker · A crew coordinator's board is 37 controls that all refuse, and none they may use

Measured above. `is_cc_any` grants the Schedule tab
([`pages/admin.py:127`](../../pages/admin.py#L127)) but not `can_crud`, so:
`on_edit` is omitted → no ID link, no edit dialog; `__CC__` is false → the crew
name is plain text instead of the approval link, which is
[the one action `can_approve_crew` grants them](crew-signup-ux.md#f1--blocker--the-crew-coordinator-cannot-approve-crew). What
*is* passed unconditionally is `on_generate_seed`, `on_seat`, `on_start`,
`on_finish` and `on_assign_stations` — every one of which `can_run_match` /
`is_staff` then refuses. The Check In refusal arrives only after the operator has
filled in a station for each player.

The board is also unscoped: the coordinator sees all 20 matches across all ten
tournaments (`get_query` is `Match.filter(tenant_id=...)`,
[`admin_schedule.py:40-41`](../../pages/admin_tabs/admin_schedule.py#L40)), not
the ones they coordinate.

### F2 — Blocker · The Stream Manager cannot assign a stage anywhere

`assign_stage`'s own docstring reads *"Stream Managers globally; TAs within their
tournaments"*
([`match_service.py:521-533`](../../application/services/match/match_service.py#L521))
and `can_assign_match_stream` implements exactly that. But the Schedule tab is
granted to `is_staff or is_ta_any or is_cc_any`
([`pages/admin.py:127`](../../pages/admin.py#L127)) — STREAM_MANAGER is not in
that list, and `sm_user`'s admin drawer contains one item: Stream Rooms, which
manages the *venues*, not their assignment. Verified in the browser: no Schedule
tab, no board, no Assign button. The role exists for this job and has no surface
that does it.

### F3 — Critical · Concurrent edit is an unrecoverable dead end

Two staff sessions opened match 8; the second saved first. The first then saved:

> This match has been modified by another admin. Please reload and try again.

Measured state of that dialog afterwards: still open, the typed comment still
present, **no reload, discard or overwrite affordance anywhere in it**, and every
subsequent Save repeats the same refusal indefinitely (the guard compares against
`_initial_updated_at`, captured at open —
[`match_dialog.py:53`](../../theme/dialog/match_dialog.py#L53), checked at
`:276-281`). The only path forward is to select the text by hand, copy it out,
close, reopen and retype. The optimistic lock is right; the recovery is missing.
Worth noting the board *does* live-update the row underneath via `match_live`
([`match.py:391-399`](../../theme/tables/match.py#L391)) — the data to offer
"reload with their changes / keep mine" is already arriving.

### F4 — Critical · Two-thirds of the tournament dropdown cannot be scheduled, and you find out after submitting

Measured, every option in the Create dialog:

| Tournament offered | Player options |
|---|---:|
| Bracket Demo — Cancelled | **0** |
| Bracket Demo — Double Elimination | **0** |
| Bracket Demo — Draft | 4 |
| Bracket Demo — Groups to Playoff | **0** |
| Bracket Demo — Round Robin | **0** |
| Bracket Demo — Single Elimination | **0** |
| Bracket Demo — Swiss | **0** |
| Wizzrobe Cup | 2 |
| Wizzrobe Dev Tournament | 4 |
| Wizzrobe Online Series | 5 |

Six of ten open an empty menu with no message. Pressing Create then yields
*"Match must have at least one player"* — a true statement that names neither the
cause (nobody is enrolled) nor the fix (enroll them, or tick "Choose any
players"). A **cancelled** tournament is offered on equal footing with a live
one, and so are the bracket-run tournaments whose matches are supposed to come
from the bracket.

### F5 — Critical · The edit dialog reports "No players assigned." for a match with two players

Match 8 has two players (visible as chips in the same dialog's Players select)
and zero `MatchAcknowledgment` rows, so `list_acknowledgments`
([`match_service.py:113`](../../application/services/match/match_service.py#L113))
returns `[]` and the section renders its empty-state
([`match_dialog.py:539-540`](../../theme/dialog/match_dialog.py#L539)). The copy
describes the wrong thing: the players are assigned, their *acknowledgment rows*
are absent.

The app path that produces this state is the SpeedGaming ETL, which syncs players
without seeding acknowledgments — deliberately, and documented as such
([`speedgaming_etl_service.py:328-336`](../../application/services/speedgaming_etl_service.py#L328)).
The UX consequences were not: on an SG-sourced match, the players cell renders
neither the confirmed nor the pending ack icon, the player's self-acknowledge
button never appears (it is gated on an ack row existing —
[`match_slots.py:341`](../../theme/tables/match_slots.py#L341)), and the admin
dialog says nobody is assigned. 12 matches in the dev DB are currently in this
state, so `/ui-validation` has been screenshotting it all along.

### F6 — Major · The five Clear buttons are an arming mechanism with no label, no summary and no undo

[`_render_clear_buttons`](../../theme/dialog/match_dialog.py#L132) renders Clear
Check In / Started / Finish / Confirmed / Seed. Measured behaviour of a click: the
button sets a private flag and **disables itself** (`disabled` class added) — no
confirmation, no text, nothing else on screen changes, and the actual clearing
happens on Save. There is no way to un-arm one short of closing the dialog and
losing every other edit, no summary at Save of what is about to be rewound, and
nothing anywhere says these five buttons will roll a match's lifecycle backwards.
Contrast the same file's `_confirm_cancel` (`:215-226`), which spells out exactly
who gets DMed.

Adjacent, same footer: `Cancel match` (notifies players and crew, closes the
race room) sits immediately left of `Cancel` (closes the dialog). The code
carries a comment acknowledging the collision (`:314-317`); the labels still
differ by one word.

### F7 — Major · Mobile is 8.2 screenfuls of board and a dialog that scrolls inside the sheet

390×844: the admin board is 20 cards, 451 px each, 6,912 px total. The create
dialog renders as a full-height sheet (998 px of content in an 843 px card), so
Create sits below the fold from the moment it opens. Per
[current-state.md](../current-state.md), no physical-device pass has ever run —
these numbers are emulated too, but the ratio is the point: an operator standing
at a venue scrolls ~8 screens to find a match by eye, because the cards carry
every detail and the board has no day/now anchor.

### F8 — Minor · "Choose any players" silently enrolls someone in the tournament

`ensure_players_enrolled` → `ensure_enrolled`
([`match_participants.py:51-61`](../../application/services/match/match_participants.py#L51))
enrolls any player who is not already enrolled, with no warning and no mention in
the dialog. `TournamentPlayers` is otherwise something a player opts into
themselves, from Profile → Tournament enrollment
([`home_tabs/player_edit_info.py:305-360`](../../pages/home_tabs/player_edit_info.py#L305)) —
so scheduling a match ticks a checkbox on someone else's profile page. The
repository's other enrollment entry point, `enroll_player`, has no callers at all;
this is the only write path.

### F9 — Minor · The dev seed cannot reproduce the two role failures above

[`scripts/seed_dev.py:265`](../../scripts/seed_dev.py#L265) makes **staff** the
crew coordinator, and no seeded user holds STREAM_MANAGER without also being able
to reach the board another way. Both F1 and F2 are therefore invisible to every
`/ui-validation` run and to every dev environment; measuring them here required
granting a coordinator role by hand. Per CLAUDE.md step 6 the seed should carry
each meaningful state — a coordinator-only user and a stream-manager-only user
are two rows.

### F10 — Minor · The board's identity is a database id

The ID column, the edit link, every crew confirmation and every notification
identifies a match by primary key: *"match ID 17"*. The row already knows the
tournament, the time and both players. Same copy problem as
[crew-signup-ux.md F4](crew-signup-ux.md#f4--major--every-message-names-a-database-id-not-a-match).

### F11 — Minor · Three divergent copies of the read-only state cell

RC4. `state_readonly_slot()` and `SEED_SLOT_READONLY` are dead code; the home
schedule and player dashboard keep inline duplicates of both. Any fix to the
shared cell reaches one of the three boards.

---

## What works

Worth keeping intact through any remediation:

- **The review queue strip** ([`admin_schedule.py:59-98`](../../pages/admin_tabs/admin_schedule.py#L59))
  is the model the rest of this board should follow: it counts three distinct
  kinds of work, distinguishes "needs a decision" from "needs a click", and
  offers a one-click filter to them. Crew approval has no equivalent.
- **`STATE_SLOT`'s refusal to offer impossible actions** — the `awaiting players`
  and `racetime.gg` notes, the `No result` chip that leads with the pencil rather
  than a Confirm button that would only error.
- **The SpeedGaming read-only contract** — badge plus disabled ETL-owned inputs,
  with the service as the actual enforcement.
- **`SEED_ROLLABLE`'s gate** and the reasoning recorded above it: a seed rolls
  once, so the button is hidden where it would burn the roll.
- **Live row updates with a flash**, and the per-board filter namespacing
  (`_skey`) that stopped four boards sharing one filter.

## Not covered

Result recording and the proctor board (audited and shipped in #146), racetime
room lifecycle, the bracket→match scheduling seam beyond the link cell,
SpeedGaming sync itself, and stream-room management. Crew signup and approval are
in [crew-signup-ux.md](crew-signup-ux.md).
