---
title: Match day queues
slug: staff-match-day
icon: pending_actions
order: 205
audience: staff
summary: For staff. What's waiting on you on Admin → Schedule: reschedule and cancellation requests, results to confirm, disputes, seeds, race rooms and the room screens.
---

**This one is for staff.** On match day most of your work arrives as a queue
on **Admin → Schedule**: players asking to move a match, results a proctor has
recorded, and the odd dispute. This page is how to clear each one. Booking and
editing matches is in [Running the schedule](/help/staff-schedule).

## What's waiting on you

:::snippet staff-queues
Two strips sit above the board when there's something to do, and disappear when
there isn't.

**Reschedule requests** come first, because a player is waiting on an answer.
The strip names up to three requests (who asked, and for what time) and counts
the rest. Press one to open it.

**Results** come next, as up to three counts:

| Chip | Means | What to do |
|---|---|---|
| {chip:cancelled:Flagged for review} | The proctor recorded a winner but the players disagreed | Talk to the proctor, then confirm or correct |
| {chip:cancelled:No result recorded} | The match is {state:Finished} with no winner on it | Record the winner, then confirm |
| {chip:pending:Awaiting confirmation} | A winner is recorded and nobody has disputed it | Check it and confirm |

**Show only these** filters the board down to {state:Finished} matches so you
can work through them. Clear the State filter to get the full board back.
:::

![The top of Admin Schedule with three reschedule requests waiting and counts of flagged, resultless and unconfirmed results](/static/help/staff-match-day/queues-desktop.webp)

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

![A reschedule request: the current and proposed times, the player's reason, the opponent's agreement, and the approve and decline buttons](/static/help/staff-match-day/reschedule-request.webp)

Players can only ask before the match is checked in. Once they're in the room,
it's a conversation with the proctor rather than a request.

## Confirming results

:::snippet staff-confirm
A proctor's job ends at recording the winner. Yours is to confirm it, and that's
what makes the result official. Confirming advances the bracket and pushes the
result to Challonge where the tournament is linked to one.

On a {state:Finished} row, press **Confirm**. The dialog names the winner and the
loser so you can check them against what you were told without closing it.

To fix the winner first, press the pencil beside **Confirm**. A row with no
winner shows **Record Winner** instead. Either way, correcting the result doesn't
re-finish the match or DM anyone again.

If the result has already advanced a bracket, the pencil is refused. Correct it
from the bracket instead (**Results → Override**), so the bracket moves with it.
:::

### Disputes

:::snippet staff-review-flag
A {chip:pending:Needs review} chip on a row means the proctor ticked **Flag for
admin review** because the players disagreed about who won. It's a marker, not a
report. Find the proctor and hear what happened.

The flag doesn't hold anything up. The match stays {state:Finished}, and once
you've decided, confirming it (with the winner corrected if need be) clears the
flag.
:::

## Seeds

:::snippet staff-seeds
The **Seed** column shows each match's seed once it's rolled. **Generate** rolls
it and DMs it to the players. Proctors and tournament admins can press it too.

**Generate** only appears where a roll can help: the tournament has a randomizer
set up, the match has players, it isn't finished, and it isn't a racetime.gg
match (the race room rolls its own).

Some randomizers work through a queue. Those show a spinner for a few minutes,
and the players are DMed as soon as the seed lands, so you can leave the page.

| You see | Means |
|---|---|
| A spinner | The seed is still being generated |
| An error icon next to **Generate** | The last roll failed. Hover over it for the reason, then press **Generate** to try again. |
| A bell with a line through it, after the seed | Someone on the match can't receive DMs from the bot. Hand them the seed in person. |

To roll a new seed, open the match, press **Clear Seed** and **Save**, then press
**Generate** again.
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

The screen is read-only. Rolling a seed still happens on Admin → Schedule or the
Proctor Station.

## Race rooms

Where racetime.gg rooms are switched on and a tournament has a racetime bot, the
match dialog has a **Racetime Room** section. Staff and sync admins can press
**Create racetime room** to open one by hand, whether or not the tournament opens
rooms automatically.

Once a room exists, the dialog links to it and shows its status. **Cancel race
room** tells the app to stop treating it as live, and the match keeps its time.
The room stays open on racetime.gg, so close it there too if nobody should race
in it.

On a racetime.gg match the State column reads "racetime.gg" instead of offering
**Check In**, because the room drives the match from there.
