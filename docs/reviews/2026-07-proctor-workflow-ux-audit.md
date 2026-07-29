# Proctor & admin match-day workflow — UX audit

**Date:** 2026-07-29
**Scope:** the proctor's on-site match workflow in the volunteer UI (`/volunteer` →
Proctor Station) and the SGL admin's result-verification step that follows it.
**Method:** code read of the whole path plus a live browser pass against the seeded
dev app (`proctor_user` and `staff_user`, desktop 1500px and phone 430px), driving
each dialog and each lifecycle transition.

---

## 1. The workflow as described

1. Check players in once they enter the room, so we know they're present and ready.
2. Assign each player a numbered station (players sit on opposite sides of a room
   that faces inward).
3. Generate the game's seed, if applicable.
4. Confirm both players are ready, count them down, start both runners, mark the
   game started.
5. On a raised hand, verify the win and record the winner.
6. Proctor's workflow is complete.

Then an admin reviews the recorded result, verifies it (resolving any dispute), and
records it officially into the bracket.

Answers gathered while scoping this audit:

- **One proctor per room** — a single proctor is aware of every match in flight, so
  the board is a *room* board, not a per-proctor worklist.
- **Check-in is per match**, once both players are present. The single match-level
  `seated_at` is the right model.
- **Stations are a fixed venue-owned pool with no pairing rule** — the proctor picks
  two of the real stations; which two is their judgment.
- **All devices** — phone, tablet, and a shared desk laptop all have to work.
- **Confirm is the admin's step, not the proctor's** (today's behaviour is a bug).
- **One winner, one loser** is the only outcome worth modelling; oddities are handled
  verbally.
- **Disputes**: the proctor records their best guess and the admin overrides during
  confirmation.
- **Seeds reach players by Discord DM**; the proctor only needs to know it went out.

## 2. The workflow as built

`/volunteer` → *Proctor Station* renders `pages/admin_tabs/admin_schedule.py:admin_schedule_page`
with `can_crud=False` (`pages/volunteer.py:38-40`). It is the admin Schedule tab — same
page title ("Schedule Management"), same nine columns, same filters — with the create/edit
controls suppressed.

| Step | Control today | Where |
|---|---|---|
| 1. Check in | `Check In` button in the State cell — opens the **Station Assignment** dialog; submitting it assigns stations *and* seats the match | `theme/tables/match_slots.py:87-99`, `pages/admin_tabs/admin_schedule.py:73-96` |
| 2. Assign stations | Same dialog. Two free-text inputs. A separate re-assign button exists but is hidden from proctors | `theme/dialog/station_assignment_dialog.py`, gated at `theme/tables/match_slots.py:287` |
| 3. Generate seed | `Generate` button in the far-right Seed column | `theme/tables/match_slots.py:69-85` |
| 4. Start | `Start` → generic "Are you sure…" confirm | `pages/admin_tabs/admin_schedule.py:98-123` |
| 5. Record winner | `Finish` → result dialog (winner dropdown) → records result, then stamps `finished_at` | `theme/dialog/match_result_dialog.py` |
| 6. — | `Confirm` button is **also on the proctor's row** | `theme/tables/match_slots.py:126-135` |

The five steps exist. What is missing is that they are a *sequence* — nothing on the
board expresses order, progress, or what the proctor should do next.

---

## 3. Findings

### P0 — the role boundary is not enforced

**F1. A proctor can confirm a match, which advances the bracket and pushes to Challonge.**

Verified end to end in the browser: signed in as `proctor_user`, added `Finished` to the
state filter, and match 8 went `Finished → Confirmed` with no error and no warning.

- `AuthService.can_transition_match` (`application/services/auth_service.py:202-207`)
  returns true for a proctor and is the *only* gate on seat / start / finish / **confirm** /
  roll-seed / assign-stations. There is no separate confirm authority.
- `admin_schedule.py:214` passes `on_confirm` unconditionally (unlike `on_edit` and
  `on_edit_stream_room`, which are `… if can_crud else None`), so the Confirm button
  renders for proctors on both desktop (`match_slots.py:126-135`) and mobile
  (`match_grid.py:183-184`).
- `MatchScheduleService.confirm_match` then fires `ChallongeService.push_result_if_linked`
  and `BracketService.advance_if_linked` (`match_schedule_service.py:243-265`).

So a stray tap by a proctor silently performs the admin's verification step *and*
publishes the result to the bracket and to Challonge. Hiding the button is not
sufficient on its own — the REST route `POST /api/v1/matches/{id}/confirm`
(`api/routers/match_actions.py:138-142`) authorises through the same predicate.

**Fix:** split the predicate. `can_run_match` (staff / TA / proctor) for seat, start,
finish, record-result, roll-seed, assign-stations; `can_confirm_match` (staff / TA only)
for confirm. Then gate the button on `can_crud` in both slot templates.

---

### P1 — the proctor's actual job is not what the screen is about

**F2. The surface is the admin's schedule table, not a proctor workflow.**

The page is titled **"Schedule Management"** for a proctor (`admin_schedule.py:22`).
Nine columns, two of which (Commentators, Trackers) the proctor never acts on, and one
(Stage) they can't change. The single most important column for their job — the station
each player is sitting at — is a small grey italic parenthetical inside the Players cell
(`match_slots.py:275`).

There is no "now" anchor, no grouping by day, no sort by urgency, and no count of what's
waiting. On the seeded data, 11 rows span three days with the current hour buried in the
middle.

**F3. Check In quietly does two things and confirms neither.**

Clicking **Check In** opens a dialog whose title is "Assign Stations - Match #11", whose
body header is "Assign Stations to Players:", and whose primary button is **"Assign
Stations"** (`station_assignment_dialog.py:53, 75, 99`). The word *check-in* appears
nowhere. On submit, the only feedback is the toast **"Stations assigned successfully for
match #11"** (`station_assignment_dialog.py:114-117`) — `confirm_seating` in
`admin_schedule.py:86-96` seats the match and notifies nothing at all.

Verified live: the row moved `Scheduled → Checked In` and the proctor was never told.
The inverse also holds — a proctor who only wants to fix a station has no way to do that
without going through a control labelled "Check In".

**F4. Stations are unvalidated free text with no pool and no occupancy awareness.**

Given a fixed venue pool, the current input is a bare text field validated only by a
format regex (`match_service.py:577-583`; `StationFormat` defaults to `FREE`, i.e. any
string up to 50 chars). Nothing knows which stations exist or which are occupied.

Verified live: I typed `12` into **both** players' inputs on match 11. It was accepted
without complaint, and the row now reads `Player One (12)` / `Player Two (12)` — two
people sent to one station. The same holds across matches: two concurrent matches can be
assigned the same station and nothing objects.

This is also the step the "opposite sides of the room" constraint lives in, and the
dialog gives the proctor no help with it — just two stacked identical text boxes.

**F5. A proctor cannot correct a station after check-in.**

The re-assign control (`assign_stations`) is gated on `__IA__ && __CC__` in both the
desktop cell (`match_slots.py:287`) and the mobile card (`match_grid.py:185`), so it is
staff-only — yet `MatchService.assign_stations` authorises through
`can_transition_match`, which *does* admit proctors, and `admin_schedule.py:215` wires the
callback for them. The capability is live and the button is hidden: a proctor who mis-seats
someone has to find staff.

**F6. Recording the winner — the most time-critical action — is a dropdown.**

`MatchResultDialog` (`match_result_dialog.py:69-73`) renders an empty `ui.select` labelled
"Winner". The two players' names are not visible anywhere on the dialog until the select is
opened. Their stations aren't shown either, so a proctor who identified the winner by seat
cannot cross-check. On a phone that is: tap Finish → dialog → tap select → wait for the
menu → tap the name → tap Submit.

For a two-player match this should be two large buttons carrying the player names (and
their stations), one tap.

**F7. The Start confirmation shows raw usernames while every other surface shows preferred
names.**

`admin_schedule.py:100-101` (and `152-153` for confirm) build the message from
`p.user.username`, so the dialog reads *"Are you sure you want to start match ID 2?
player_one, player_two"* while the table behind it says "Player One" / "Player Two" and
the result dialog uses `preferred_name or username`. This lands at the exact moment the
proctor is verifying they have the right two humans in front of them.

The dialog is also the generic `ConfirmationDialog` with a **red** Confirm button —
destructive styling on a benign action — and it carries no seed status, no stations, and
no countdown aid. `started_at` is stamped when the button is pressed, which is after the
countdown, not at "GO".

---

### P2 — board noise and lesser hazards

**F8. racetime.gg matches occupy the proctor's board but offer no proctor action.**
Five of eleven seeded rows are racetime matches showing the italic note "racetime.gg" in
place of a lifecycle button (`match_slots.py:95-98`). They are pure noise for an on-site
proctor. Worse, the **Generate seed button is still offered on them** — neither
`SEED_SLOT` (`match_slots.py:69-85`) nor `_SEED_DETAIL` (`match_grid.py:145-161`) checks
`is_racetime`, unlike the lifecycle and station controls which both do.

**F9. Matches with no players still offer Check In.** Rows 12 and 13 (bracket-scheduled,
entrants not yet resolved) render a Check In button over an empty Players cell. Following
it opens a station dialog that says "No players assigned to this match" but still submits,
seating a match with nobody in it — `seat_match` has no player-count precondition
(`match_schedule_service.py:174-193`).

**F10. The desktop table clips its right-hand columns.** At 1500px the Seed column — the
proctor's step 3 — is cut off at the viewport edge and needs horizontal scrolling to reach.

**F11. The mobile card buries the action.** The card renders headline → players → caption →
commentators → trackers → stage → seed → *then* the lifecycle button
(`match_grid.py:274`). On a phone the proctor scrolls past four rows of crew and stream
metadata to reach "Start".

**F12. Two different green checks mean two different things.** The check_circle beside a
player name is *player self-acknowledgment of the assignment* (`match_slots.py:265-268`),
which is set days in advance and can be `(auto)`. The check_circle in the State cell is
*checked in*. A proctor scanning the Players column will read the first as "this player is
here", which it does not mean.

**F13. The winner is conveyed by colour and font weight only** (`finish_rank === 1` →
`st-ok-strong`, `match_slots.py:273`). No label, no icon, no legend — on a finished row the
only way to know who won is to notice one name is bolder and greener than the other.

---

### The admin's half

**F14. The admin's review queue is hidden behind a filter that excludes it by default.**
`DEFAULT_STATE_FILTER = ['Scheduled', 'Checked In', 'Started']` (`theme/tables/match.py:18`)
— **`Finished` is not in it**. The admin's entire job is the Finished-not-yet-Confirmed set,
and to see it they must notice the State filter and add a chip. There is no queue, no count,
no badge. Verified: `staff_user`'s Schedule tab opens with zero finished matches visible.

**F15. There is no way to correct a recorded result outside a bracket.** `AdminMatchDialog`
(`theme/dialog/match_dialog.py`) edits tournament, stage, players, commentators, trackers,
and racetime — there is **no winner or result field**. Once a match is `Finished`, the
Finish button is gone, so the result dialog is unreachable. For a bracket-linked match
`assert_bracket_result_editable` at least points staff at *Results → Override*
(`application/services/match/bracket_result_guard.py:36-40`); for everything else the only
correction path is the REST endpoint. This directly contradicts the agreed model —
"proctor records best guess, admin overrides at confirmation".

**F16. Confirm validates nothing about the result.** `confirm_match` checks only that
`finished_at` is set (`match_schedule_service.py:227-232`). A match with no `finish_rank`
on any player confirms happily and advances the bracket on an empty result.

**F17. There is no dispute affordance anywhere.** No flag, no note, no "needs review"
state — grep finds nothing; `scripts/seed_dev.py:323` fakes a "Disputed Match" as simply
finished-and-not-confirmed. A proctor who is unsure has nowhere to say so, and the admin
has no signal distinguishing a routine result from a contested one. `Match.comment` exists
and is rendered on the mobile card but is not a column on the desktop table and is not
editable from either the result dialog or the proctor board.

**F18. Seed delivery is fire-and-forget with no visible status.** Seeds reach players by
DM, but `_send_seed_dms` skips any player with `dm_notifications` off or no `discord_id`,
logging a warning and nothing else (`match_schedule_service.py:343-359`). The proctor —
whose job per step 3 is to make sure the players have their seed — sees only that a URL
exists in the Seed column, never whether it reached anyone.

---

## 4. Recommendations, in leverage order

### Wave 1 — close the role boundary (small, mechanical)
1. Split `can_transition_match` into `can_run_match` and `can_confirm_match`; confirm
   becomes staff/TA-only. **(F1)**
2. Gate the Confirm button on `can_crud` in `match_slots.STATE_SLOT` and
   `match_grid._ACTIONS`, matching how edit and stage-assign are already gated. **(F1)**
3. Use `preferred_name or username` in the start/confirm confirmation messages. **(F7)**
4. Add `!props.row.is_racetime` to both seed-generate templates. **(F8)**
5. Add a player-count precondition to `seat_match`. **(F9)**

### Wave 2 — make check-in and stations honest
6. Re-label the check-in path: dialog title "Check in — Match #11", CTA "Check in &
   seat", and a toast that names both effects. **(F3)**
7. Show the Assign Stations control to proctors (drop `__CC__` from that one `v-if`; the
   service already authorises them). **(F5)**
8. Introduce a station pool — a per-tenant list of real stations — and turn the two text
   inputs into pickers that mark stations currently occupied by a checked-in-or-started
   match. Reject duplicate stations within a match at the service layer. **(F4)**
9. Promote the station out of the italic parenthetical into a first-class chip on the
   players line. **(F2)**

### Wave 3 — a purpose-built proctor board
10. Give the tab its own title and its own column set: time, players + stations, state +
    action, seed status. Drop Commentators, Trackers, and (for proctors) Stage. **(F2)**
11. Sort and group around *now*: matches needing action first, a "now" divider,
    day headers. **(F2)**
12. Replace the winner dropdown with two large player buttons showing name and station.
    **(F6)**
13. Reorder the mobile card so the lifecycle button sits directly under the players line.
    **(F11)**
14. Distinguish acknowledgment from presence — different icon or a "confirmed" chip
    rather than a second green check. **(F12)**
15. Label the winner explicitly on finished rows. **(F13)**

### Wave 4 — the admin's review loop
16. Add `Finished` to the default state filter for admins, or give the Schedule tab a
    "Needs review" count. **(F14)**
17. Add an edit-result path to the admin match dialog for non-bracket matches (the
    service and REST route already support re-recording). **(F15)**
18. Make `confirm_match` require a recorded result. **(F16)**
19. Add a lightweight dispute signal — a proctor-set "needs review" flag plus a note that
    surfaces on the admin's queue. This is the one genuinely new capability in the list,
    and the agreed model ("proctor records best guess, admin overrides") only works once
    16-18 exist. **(F17)**
20. Surface seed-delivery status on the row (sent / opted out / no Discord). **(F18)**

Waves 1 and 2 are the ones worth doing first: 1 is a correctness bug in the role model,
and 2 removes the two places where the tool silently does something other than what its
labels say.
