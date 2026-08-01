---
title: Reading the schedule board
slug: schedule-board
icon: schedule
order: 20
summary: What every column on the Schedule tab means, and what each match state tells you.
---

The **Schedule & Crew Signup** tab lists every match in the event. It is the same
board for everyone: players, crew and spectators all see it.

## The columns

:::snippet schedule-columns
| Column | What it tells you |
|---|---|
| **Tournament** | Which tournament the match belongs to. |
| **Scheduled At** | When it starts, in your local time. |
| **State** | How far along the match is, see below. |
| **Players** | Who is playing. |
| **Stage** | Which stage (stream room) it is on. If it is being streamed, the name links to the stream. |
| **Generated Seed** | The seed for the match, once one exists. |
| **Commentators** / **Trackers** | Who is signed up as crew, and whether they have been approved. |
| **Watch** | Subscribe to updates on this match. |
:::

An empty cell means there is nothing to show yet, not that something is wrong. A
match usually gets its stage, its seed and its crew at different times.

## Match states

:::snippet match-states
The **State** column moves through five values, in order:

| State | Meaning |
|---|---|
| {state:Scheduled} | A time is booked. Nobody has arrived yet. |
| {state:Checked In} | Both players are at their stations and a proctor has checked the match in. |
| {state:Started} | The match is under way. |
| {state:Finished} | Someone has recorded a result. It is not official yet. |
| {state:Confirmed} | A staff member has confirmed the result. This is the official record. |

The gap between {state:Finished} and {state:Confirmed} is normal and often takes
a while, since staff confirm results in batches. A finished match whose result looks
wrong to you is worth mentioning to staff before it is confirmed.
:::

## Watching a match

:::snippet watch-match
**Watch** subscribes you to a match you are not in. You get a Discord DM each
time its state changes: checked in, started, finished, confirmed, rescheduled
or cancelled.

Watching is separate from playing and from crewing. If you are already a player
or approved crew on a match you are told about it anyway, and watching it too
does not double your DMs.

You turn watching on from the board or the match dialog; you can turn it off
from either of those or from the **Unwatch** button on any DM it sends you.
:::

## Filters and sorting

Most columns sort; tap the header. The filter controls above the board narrow
it down, and what you pick is remembered for next time, so a board that looks
emptier than you expect usually has a filter still applied from your last visit.

## On a phone

Below tablet width the board becomes a stack of cards instead of a table, one
card per match, because a table that wide pushes its buttons off the screen. The
same information is in both; the cards just reflow it.

You can also choose which columns you see and in what order, per device. That
choice is yours alone, and it does not change what anyone else sees.
