---
title: Setting up a tournament
slug: staff-tournaments
icon: emoji_events
order: 240
audience: staff
summary: Creating a tournament, its signup window and match hours, entrants, and who can run it.
---

Every match, signup, seed and payout hangs off a tournament, so this is the first
thing to get right before an event. Tournaments live on **Admin → Tournaments**.

## Creating one

:::snippet admin-tournaments
**Add Tournament** opens the editor. Only the name is required. Everything else
starts collapsed with a working default, so you can save a name now and come back
to the rest. When you reopen a tournament to edit it, every section starts
expanded.

Click a tournament's name in the table to edit it. Click its player count to
manage who is entered.
:::

Leave **Active** ticked while the tournament is running. Unticking it keeps the
history but takes the tournament out of every picker, including the player's
Tournaments tab.

## What each section sets

| Section | What lives there |
|---|---|
| Scheduling | Average and maximum match length, players per match, the signup window, and per-day match hours |
| Entry & administration | Whether players may request matches, the rules link, format and randomizer notes shown to players, how many commentators and trackers a streamed match needs, and the stage reminder |
| Seeds & randomizer | The seed preset, an optional harder preset, and the triforce text access message |
| Integrations | The bracket link, Challonge, and racetime.gg room settings |
| Danger zone | Deleting the tournament. Staff only |

**Commentators needed** and **Trackers needed** decide when the coverage reports
count a streamed match as covered. Set a role to 0 if this tournament doesn't use
it. Otherwise every streamed match shows a gap and the schedule keeps offering a
signup nobody will fill.

**Remind about the stage** is how many minutes before the match a second DM tells
the players and approved crew which stage to walk to. Assigning a stage already
DMs them once, straight away. Set it to 0 to skip the reminder.

## The signup window

**Signups open** (1) and **Signups close** (2) decide when players can enter themselves on
the Tournaments tab. Leave both blank and signups stay open until you make the
tournament inactive. The close has to be after the open.

The **Signups** column on the table tells you where each tournament stands and
when that changes, for example "Not open yet — 2026-10-20 09:00 EDT" or
"Open — 2026-10-22 18:00 EDT".

The window only limits players. You can add or remove an entrant at any time.

![The Add Tournament dialog with Scheduling open, showing the Player signups section with Signups open marked 1 and Signups close marked 2, then the Tournament Days section](/static/help/staff-tournaments/signup-window.webp "The signup window and match days, under Scheduling.")

## Match hours

**Tournament Days** overrides the community's event dates and daily hours for this
one tournament. Set a start and end date and a row appears for each day, with an
open and close time. Leave a day blank for any time.

Hours are read on the community's clock, and they bind everyone: a match can't be
created, requested or rescheduled to start outside them, by staff included. If a
tournament needs a late finals slot, widen that day's close time first.

Leave the dates blank to use the community-wide hours under **Settings → Event**.

## Entrants

Click the player count to open the tournament's entrant list. Pick someone in
**Enrol a member** and press **Enrol** to add them. **Remove** beside a name
takes them out, after asking first. Only staff can change entrants. The person
has to be a member of the community already, so add them on **Admin → Users**
first if they aren't.

A match can only be scheduled between entrants, so a missing entrant is the usual
reason a match won't save.

A tournament linked to Challonge takes its entrants from the bracket instead. See
[Running a tournament on Challonge](/help/staff-challonge).

## Who can run it

Two per-tournament jobs are set on a person, not on the tournament. On
**Admin → Users**, open the person's **⋮** menu, choose **Edit member**, and pick
tournaments under **Tournament Admin of** or **Crew Coordinator of**. A Discord role mapping under **Settings →
Discord** can grant either one as well.

| Job | What they get for their tournaments |
|---|---|
| Tournament admin | The Schedule, editing the tournament, running and confirming its matches, rolling seeds, linking it to Challonge, and its payouts |
| Crew coordinator | The Schedule, approving commentators and trackers |

Neither can create or delete a tournament or change its entrants. Those stay with
staff.

The **Roles** filter on Admin → Users has **Tournament Admin** and **Crew
Coordinator** options for finding everyone who holds either job.

## Deleting a tournament

Deleting removes the tournament and everything attached to it: matches, entrants,
brackets and triforce texts. There is no undo. Only an inactive tournament can be
deleted, so untick **Active**, save, then reopen the editor and use the **Danger
zone**. The confirmation lists what will go, and **Delete forever** stays greyed
out until you type `permanently delete`.

Deactivating is almost always what you want. It keeps the results.
