---
title: Running matches as a proctor
slug: proctor
icon: sports_esports
order: 55
feature: VOLUNTEERS
summary: The Proctor Station board, running a match start to finish, seating players, recording the result, the room's seeds screen and loaner devices.
---

A proctor runs a room. You check the matches in, start the players, and record
who won.

This page is the **app's** manual: the board, the steps you take in it, and what
happens to a result. The floor standard the job is held to (looking after the
room, who checks players in, game integrity, when to fetch an admin, handing over
a shift) is set by the event rather than by the app, so where your community
publishes one it lives under **Event Information** in the sidebar. Read both
before your first shift.

The board is **Volunteer → Proctor Station**. If you cannot see it, you have not
been given the Proctor role yet; ask a coordinator. Being scheduled on a proctor
shift usually gives it to you.

## The board

:::snippet proctor-station
**Proctor Station** is every on-site match, grouped by what it needs from you
next: **Late, check in now**, then **Ready to start**, **In play** and **Up
next**. Each heading says how many matches are under it. Work from the top.
Matches run from a racetime.gg room are left off, since the room drives those,
not you.

Each line is one match: its time (orange when it's late), the players with the
station each is sitting at, the stage, and a button for the next step: **Check
in**, **Start** or **Finish**. Press it and the step's dialog opens, the same as
it does from anywhere else. The time and the stage are what to call out across
the room.

Tap anywhere else on a line to open the match's details. They start with a
**Ready to play?** checklist (players confirmed, stations, stage and seed),
each ticked or flagged, with the fix on the same line: **Change** for the
stations, **Generate** or **Copy** for the seed, and the player's ADA
accommodation if they have one.

It is deliberately not the admin Schedule tab. There is no scheduling here and
no crew: this board is for *running* matches, not booking them.

By default the board shows matches that are still to be played or in play. Use
**Filters** to narrow it to the day and the tournaments your room is running, or
add **Finished** to the State filter to see what you have already recorded, under
**Done**. The search box filters the lines by any text in them, such as a
player's name.
:::

### Reading a line

![A line on the Proctor Station board on a phone: the time in orange, two players, No stations yet, an ADA note, and a Check in button](/static/help/proctor/board-phone.webp "A match waiting to be checked in.")

| You see | Means |
|---|---|
| **Station 4** beside a name | The station they are seated at. |
| **No station** beside a name | They aren't seated yet. Check-in seats them. |
| **ADA:** and a name | Staff have arranged an accommodation for them. Open the match and tap the accommodation to see it. |
| **Live** | The match is in play. |

The accommodation popup tells you an accommodation is arranged and to check
with staff for what it involves. It does not show you the details; those are
written for staff only. Find out before the match starts.

## Running a match

:::snippet proctor-run-match
Four steps, in order. Each one is the button on the match's line, and also
sits at the top of the match's details.

1. **Check the match in** once both players are there. Press **Check In**,
   pick a station for each player (or press **Randomize**), and press **Check in
   & seat**. That stamps the match as {state:Checked In} and records where each
   player is sitting.
2. **Roll the seed** if the match does not already have one. Usually it is
   there already. If not, open the match and press **Generate** on its Seed
   line. A seed can only be
   rolled once per match, and the players get it by DM.
3. **Press Start** when the players actually start, not when you seat them, and
   confirm. From that moment the match reads as {state:Started} to everyone
   watching the board.
4. **Press Finish** when it ends and say who won. Tap the winner, then the
   **Yes** button that names them. Picking a name does not record anything on
   its own, so a mis-tap costs you a **Back**, not a wrong result. (With more
   than two players, choose the winner from the list and press **Submit
   Results**.) That moves the match to {state:Finished}.

Everything between those presses (helping players set up, running a countdown,
keeping the room workable) is the event's to define, not the app's. The app
records what you did; it does not tell you how to run the room.

You do **not** confirm the result. A staff member does that, and it is what
makes the result official; your job ends at recording it. Until they do, the match shows
{chip:pending:To confirm} under **Done**.
:::

![The Check in dialog: a station picker for each player, the Randomize button, and Check in & seat](/static/help/proctor/check-in-phone.webp "Step 1: checking a match in.")

### When the seed is not straightforward

Some randomizers take a few minutes to produce a seed. The Seed line says
**Rolling…** with a clock while it works; you can leave the page, and the
players are DMed when it lands.

If the last roll failed, the Seed line says why. Press **Generate** again.

"Couldn't DM" under a seed names any player who cannot receive Discord DMs.
Read the seed out or show it to them, because the DM will not reach them.

### Which stations to use

:::snippet proctor-stations
There is no pairing rule. Which two stations you seat a match at is your call.
The app only stops you putting two people in the same seat, or seating someone at
a station another match in play is already using. A taken station shows in the
picker as **in use**, with the players sitting there.

**Randomize** draws a free station for each player and puts them on opposite
sides of the room, away from matches already in play where it can. Nothing is
saved until you press the button to confirm, so you can change either seat or
draw again. If the room is too full to honour all of that, it says which part it
could not manage and seats them anyway.

Seated someone in the wrong place? Open the match and press **Change** on its
Stations line to move the seats of a match that is already checked in.

You do **not** need to release a station afterwards. A station frees itself the
moment its match is recorded as finished.
:::

### If you did not see who finished

:::snippet proctor-result
Ask both players. Record what they agree on.

If they **disagree**, record your best call and tick **Flag for admin review**.
Then tell an admin what happened. The flag is a marker, not a report, and the
conversation is what settles it.

Flagging does not hold the match up or change its state. It marks it
{chip:pending:Needs review} so it does not get confirmed on autopilot.
:::

![The Enter match results dialog: one button per player with their station, and the Flag for admin review checkbox](/static/help/proctor/result-phone.webp "Step 4: who won?")

### If you recorded the wrong winner

You cannot change a result once it is recorded; correcting it is an admin's job.
Tell one which match (its `#`) and who actually won.

## The room's seeds screen

A room can have a shared screen that shows the seed for every match about to be
played, so players can read it without anyone signing in. It is a web page
opened from a private link that staff issue for that machine.

It lists matches that have a seed and have not started. A match leaves the
screen the moment you press **Start**, and new seeds appear as they are rolled.
Leave it open; it updates itself.

The screen cannot roll seeds or change anything. If a match is missing from it,
the match has no seed yet, so roll one from the board. If the screen shows a
page-not-found message, its link has been withdrawn or mistyped. Ask staff for a
new one rather than signing in on the machine.

## Lending a device

Where the event lends out equipment, each loaner carries a QR code. The player
who is going to use it scans the code with their phone, signs in, and borrows it
in their own name.

Point them at the code rather than doing it for them. A proctor cannot check a
device out on someone else's behalf, and borrowing it on your own account would
put the loan in your name.

Returns go back to whoever runs the equipment desk. Only they can check a device
back in, so if a player is packing up with a borrowed unit, send them and it to
the desk.

The whole loan, from the player's side and the desk's, is in
[Borrowing equipment](/help/equipment).
