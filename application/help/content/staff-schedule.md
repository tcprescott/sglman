---
title: Running the schedule
slug: staff-schedule
icon: edit_calendar
order: 200
roles: STAFF
summary: For staff. Admin → Schedule, creating and editing matches, cancelling one, rewinding a match, stages and stream candidates, and approving crew.
---

**This one is for staff.** It covers **Admin → Schedule**, the board you book and
run matches from. What players, crew and proctors see of the same matches is in
[the player guide](/help/player), [crew signup](/help/crew) and
[the proctor guide](/help/proctor).

The answers to "what's waiting on me" (reschedule requests, results to confirm,
disputes, seeds and race rooms) have their own page:
[Match day queues](/help/staff-match-day).

## The board

:::snippet staff-schedule-board
**Admin → Schedule** lists every match in the community. Out of the box it hides
{state:Confirmed} matches, because a confirmed match needs nothing more from you.
Change that with the **State** filter, and narrow by day, tournament or a search
the same way as [the public board](/help/schedule-board).

The pencil at the start of a row opens the match. **Create Match** adds one.

The row is also where most match-day work happens without opening anything:
**Check In**, **Start** and **Finish** in the State column, **Generate** in the
Seed column, the Stage dropdown, and the approval circle beside each commentator
and tracker.

A clock icon beside the time means the match is past its scheduled time and
nobody has checked it in yet.
:::

### Who sees what

You aren't the only one on this board. Each role gets the controls it can use and
nothing else.

| Role | What they can do here |
|---|---|
| Staff | Everything below |
| Tournament admin | Everything, but only for their own tournaments. The board shows them nothing else. |
| Stream manager | Set the Stage on any match |
| Crew coordinator | Approve commentators and trackers on their tournaments |
| Proctor | Check in, start, finish and roll seeds, from Volunteer → Proctor Station rather than here |

Only staff and tournament admins confirm results. A proctor records the winner,
and you make it official.

## Creating a match

Press **Create Match**, pick the tournament, the players, a date and a time, and
press **Create**. Everything else is optional.

- **Players** lists only people enrolled in that tournament. Tick **Include
  players not enrolled in this tournament** to pick anyone in the community.
  Doing that enrols them, and the dialog names who it's about to enrol before
  you save.
- **Suggest a time** fills in the date and time for you. It picks a quiet slot
  in the tournament room over the next few hours that none of the players has
  blocked out, so it also spreads the load across the room.
- **Commentators** and **Trackers** you add here are approved on the spot. They
  get a DM asking them to acknowledge.
- **Stage** puts it on a stream straight away. **Stream candidate** marks it as
  "probably streamed, stage not decided".

Saving DMs the players and asks each of them to acknowledge the match.

## Editing a match

Open the pencil. The top of the dialog says where the match is now (its state,
the winner, and whether it's flagged), then everything below edits it.

Moving the date or time tells everyone on the match and asks the players to
acknowledge again. If a player or crew member changes, the people added and the
people removed both get a DM.

A match synced from SpeedGaming carries a **Synced from SpeedGaming** badge. Its
tournament, players and time are locked, because the next sync would overwrite
any change you made. Edit those on SpeedGaming.

At the bottom, **Player Acknowledgments** shows who has confirmed they'll play
and when. "(auto)" means the app acknowledged for them, usually because they
requested the match themselves.

### Seed settings

When a tournament offers a second, harder preset, the dialog shows **Seed
settings** until the seed is rolled. Leave it on **Let the players decide** and
the harder preset is used only when every player opts in. Pick **Force** either
way to make the call yourself. Both players are DMed whichever you choose.

### Rewinding a match

**Rewind the lifecycle** undoes steps that shouldn't have happened: a match
checked in by mistake, a winner confirmed too soon, a seed rolled for the wrong
pair. Each button (**Clear Check In**, **Clear Started**, **Clear Finish**,
**Clear Confirmed**, **Clear Seed**) is armed by one press and disarmed by a
second. Nothing changes until you press **Save**, and the line under the buttons
says exactly what will be undone.

Clearing a seed is how you re-roll one. The Seed column offers **Generate** again
once it's gone.

To correct only the winner, don't rewind. Use the pencil beside **Confirm** on
the row instead (see [Match day queues](/help/staff-match-day)).

## Calling a match off

The match dialog has two red buttons, and they aren't the same.

| Button | What it does | Use it when |
|---|---|---|
| **Cancel match** | Removes the match, DMs its players and crew, and closes any open race room | The match was real and people were planning around it |
| **Delete** | Removes the match and tells nobody | It should never have existed: a duplicate, a test, a typo |

If a player asked to call it off, approve their request instead (see
[Match day queues](/help/staff-match-day)). That cancels it the same way and
answers them in one step.

## Stages and streams

:::snippet staff-stage
The **Stage** column is a dropdown on every row. Click the stage name, or the
empty cell, to change it.

- A stage name puts the match on that stream. Its link icon opens the stream.
- **Candidate** means "this is going out, we haven't picked a stage yet". It's
  what you set while you're still planning, and the coverage report counts it.
- **No Stage** takes it off.

Picking a real stage over Candidate keeps the match counted as a stream match in
the reports, so you don't have to untick anything.

When a player offers their match for stream, the dialog names them under
**Stream candidate**. That's advisory. It doesn't make the match a candidate
until you tick the box or pick Candidate on the row.
:::

The stages themselves (name, stream URL, and whether they're active) live on
**Admin → Stages**. Staff and stream managers can add and edit them there. Untick
**Active** on a stage you've stopped using.

## Approving crew

:::snippet staff-crew-approval
Commentators and trackers who sign up themselves arrive unapproved. On the board
each one has a circle beside their name: empty means waiting for you, a green
tick means approved. Click the circle to approve or un-approve.

Approving asks you to confirm first, and warns you if that person is already
committed somewhere else at the same time. Once you approve, they're DMed and
asked to acknowledge. Un-approving clears their acknowledgment and tells them.

After approval the icon beside the name tracks them: a clock while you're
waiting for their acknowledgment, a tick once they've confirmed.

Click a name to see that person's profile.
:::

### Finding gaps in coverage

**Admin → Reports → Staff / Crew Activity** is where you find matches that are
short of crew. **Coverage by match** counts approved against total signups for
each role, set against what the tournament needs, and marks every match that's
short with **GAP**. Filter it to **Pending only** to see signups still waiting on
you. Each row opens that match on the board, where you can approve someone.

**Contribution by person** shows how much each volunteer has covered, which helps
when you're choosing between two people for the same slot.
