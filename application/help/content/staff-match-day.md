---
title: Match day queues
slug: staff-match-day
icon: pending_actions
order: 205
audience: staff
summary: For staff. What's waiting on you on Admin Schedule: reschedule and cancellation requests, results to confirm, disputes, seeds, race rooms and the room screens.
---

**This one is for staff.** On match day most of your work arrives as a queue
on **Admin Schedule**: players asking to move a match, results a proctor has
recorded, and the odd dispute. This page is how to clear each one. Booking and
editing matches is in [Running the schedule](/help/staff-schedule).

## What's waiting on you

:::snippet staff-queues
**Needs you** sits beside the board on a computer and above it on a phone. Each
item carries its own buttons, so most of it clears without opening anything.
Each group shows three items; **Show 2 more** (or however many are left) lists the rest. Results and Running late are read off the board, so they only count matches the board's filters are showing.

**Reschedule requests** come first, because a player is waiting on an answer.
Each names who asked, the match, and the time it moves from and to.
**Approve** moves it at the time they asked for. **Decline** opens the request
so you can write the note they'll see. A cancellation, or a request with no time
in it, has **Review** instead, which opens the request in full.

**Results** come next, disputed ones first:

| Chip | Means | What to do |
|---|---|---|
| {chip:cancelled:Flagged} | The proctor recorded a winner but the players disagreed | **Review**, after talking to the proctor |
| {chip:cancelled:No winner} | The match is {state:Finished} with no winner on it | **Record winner**, then confirm |
| none | A winner is recorded and nobody has disputed it | Check the line ("Player One beat Player Two") and press **Confirm**, or **Change** to fix the winner |

**Running late** lists matches past their start that nobody has checked in.
**Check in** does it from there.

**Open** on a result or a late match opens the match.
:::

![Needs you: reschedule requests with Approve and Decline, the first Approve marked 1; results to confirm, the Flagged chip marked 2 and a Confirm button marked 3; and matches running late](/static/help/staff-match-day/queues-desktop.webp "**Approve** (1) a request, **Review** anything **Flagged** (2), and **Confirm** (3) an undisputed result.")

You'll also get a Discord DM for each new reschedule request. Its button opens
the request on this page directly. If someone else has already answered it, the
page says so instead.

## Reschedule and cancellation requests

:::snippet staff-reschedule
Players can't move or call off their own matches. They ask, and you decide.
Requests go to staff and to the admins of that tournament, and whoever answers
first settles it.

The request shows the match, its current time, the time they want (or that they
just can't make this one, or that they want it called off), their reason, and
whether their opponent has agreed. If either player has blocked out the proposed
time on their availability, that shows as a warning.

You don't need the opponent's agreement to decide. It just saves you asking.

- **Approve and move it** moves the match. The date and time start on what they
  asked for. Change them to approve a different time, and they're told which time
  they got. Everyone on the match is told it moved, and the players are asked to
  acknowledge again.
- **Cancel the match** appears instead on a cancellation request. It calls the
  match off and DMs everyone, the same as cancelling it yourself.
- **Decline** needs a note. The note is the only thing the player sees, so say
  why.

A note on an approval is optional, and they see that too.
:::

![A reschedule request: the current and proposed times, the player's reason, the opponent's agreement, the new date and time, the Note to the player box marked 1, Decline marked 2 and Approve and move it marked 3](/static/help/staff-match-day/reschedule-request.webp "Write a note (1) before you **Decline** (2); it's optional for **Approve and move it** (3).")

Players can only ask before the match is checked in. Once they're in the room,
it's a conversation with the proctor rather than a request.

## Confirming results

:::snippet staff-confirm
A proctor's job ends at recording the winner. Yours is to confirm it, and that's
what makes the result official. Confirming advances the bracket and pushes the
result to Challonge where the tournament is linked to one.

Press **Confirm** on the result in **Needs you**, or open the match and press
**Confirm result**, where a dialog names the winner and the loser before you
commit.

To fix the winner first, press **Change** (**Change result** in the match). A
match with no winner shows **Record winner** instead. Either way, correcting the
result doesn't re-finish the match or DM anyone again.

If the result has already advanced a bracket, the change is refused. Correct it
from the bracket instead: on **Admin → Brackets**, open the stage's **Results**,
pick the match and use **Override result**, so the bracket moves with it.
:::

### Disputes

:::snippet staff-review-flag
A {chip:cancelled:Flagged} chip on a match means the proctor ticked **Flag for
admin review** because the players disagreed about who won. It's a marker, not a
report. Find the proctor and hear what happened.

The flag doesn't hold anything up. The match stays {state:Finished}, and once
you've decided, confirming it (with the winner corrected if need be) clears the
flag.
:::

## Seeds

:::snippet staff-seeds
Open a match to see its seed on the **Seed** line of the checklist. **Generate**
rolls it and DMs it to the players. Proctors do the same from the match they
open on the Proctor Station.

The button only appears where a roll can help: the tournament has a randomizer
set up, the match has players, it isn't finished, and it isn't a racetime.gg
match (the race room rolls its own).

Some randomizers work through a queue. Those take a few minutes, and the players
are DMed as soon as the seed lands, so you can leave the page.

| You see | Means |
|---|---|
| "Rolling…" with a timer | The seed is still being generated |
| The reason in red | The last roll failed. Fix the cause, then roll again. |
| "Couldn't DM" and a name | That person can't receive DMs from the bot. Hand them the seed in person. |

To roll a new seed, open the match, press **Edit match**, then **Clear Seed** and
**Save**, then **Generate** again.
:::

### Room screens

A shared PC in the tournament room can show every match whose seed is rolled but
which hasn't started, without anyone signing in on it. Set one up under **Admin →
Settings → Venue → Room screens**: give the machine a label (say, "Room A desk
PC") and press **Issue token**.

The link is shown once. Copy it and bookmark it on that machine, because only a
fingerprint of it is kept and a lost link can't be shown again. Revoke it and
issue a new one instead. The list shows when each token was last used, so you can
spot a machine that's stopped using its own.

The screen is read-only. Rolling a seed still happens on Admin Schedule or the
Proctor Station.

## Race rooms

Where racetime.gg rooms are switched on and a tournament has a racetime bot, the
**Edit Match** dialog (open the match, then **Edit match**) has a **Racetime
Room** section. Staff and sync admins can press
**Create racetime room** to open one by hand, whether or not the tournament opens
rooms automatically.

Once a room exists, the dialog links to it and shows its status. **Cancel race
room** tells the app to stop treating it as live, and the match keeps its time.
The room stays open on racetime.gg, so close it there too if nobody should race
in it.

On a racetime.gg match the match says "Runs on racetime.gg" instead of offering
**Check in**, because the room drives the match from there.
