---
title: Reading the schedule board
slug: schedule-board
icon: schedule
order: 20
summary: What each line on the Schedule board tells you, what each match state tells you, and how to filter it down to what you need.
---

The **Schedule** view on the **Event** tab lists every match in the event. It's
the same board for everyone: players, crew and spectators all see it. The two
other views on that tab read the same matches differently. **On Air** lays out
one day by stage (see [On Air and watching](/help/on-air)), and **Brackets**,
where a community uses them, shows the tournament structure.

## The columns

:::snippet schedule-columns
Each match is one line, grouped under **Live now**, **Up next**, **Waiting for
players** and, if you've brought them back with the State filter, **Finished**.

| Column | What it tells you |
|---|---|
| **Time** | When it starts, in your local time. A date under it means it isn't today. |
| **Match** | Who's playing, and the tournament. **You** marks a match you're playing in. |
| **Stage** | Which stage it's on. If the stage is streamed, its name links to the stream. **Candidate** means staff are thinking about streaming it but haven't picked a stage. |
| **Commentators**, **Trackers** | Approved crew against how many the match needs, your own **Sign up** or **Withdraw** under that, then the names of everyone signed up. |
| **Status** | Where the match is, plus **Acknowledge** on a match you play that you haven't confirmed yet. |
| **Watch** | The bell. Tap it to get a DM every time this match changes. |
:::

Tap a match's name, or anywhere on its line, for its details. Before the match
starts they open on a **Ready to play?** checklist: whether each player has
confirmed, the stations they're seated at, the stage and its stream link, the
seed once one exists, and how much crew is still needed. Under that is everyone
signed up as crew.

An empty cell or a "None" means there's nothing to show yet, not that something's
wrong. A match usually gets its stage, its seed and its crew at different times.
"needs crew" in orange means a role is still short of approved crew while signup
is open.

## Match states

:::snippet match-states
A match moves through five states, in order:

| State | Meaning |
|---|---|
| {state:Scheduled} | A time is booked. Nobody has arrived yet. |
| {state:Checked In} | Both players are at their stations and a proctor has checked the match in. |
| {state:Started} | The match is under way. |
| {state:Finished} | Someone has recorded a result. It isn't official yet. |
| {state:Confirmed} | A staff member has confirmed the result. This is the official record. |

The gap between {state:Finished} and {state:Confirmed} is normal and often takes
a while, since staff confirm results in batches. If a finished match's result
looks wrong to you, tell staff before it's confirmed.
:::

## Finding what you're after

**The board hides finished matches by default.** The **State** filter starts on
Scheduled, Checked In and Started, so a match drops off the list once its result
is recorded. Add Finished and Confirmed to the State filter to bring them back.

Above the board there are four filters:

| Filter | Narrows the board to |
|---|---|
| **Day** | All dates, Today, Tomorrow, or the next 7 days. "Today" is your today. |
| **Tournament** | One or more tournaments. |
| **Stage** | One or more stages, handy for following one stream. |
| **State** | The match states you pick. |

Your choices are remembered for next time, on this board only. If the board
looks emptier than you expect, a filter from your last visit is usually still
applied.

On a phone the filters fold away behind a **Filters** button. A number beside it
counts how many are set to something other than the default, so a "2" there
means two filters are narrowing what you see.

![The board's filters opened on a phone: Day set to All dates, Tournament and Stage empty, and State set to Scheduled, Checked In and Started](/static/help/schedule-board/filters-phone.webp "The filters on a phone, at their defaults.")

**Needs crew**, the switch above the board, is separate from the filters. It
shows only matches still short of an approved commentator or tracker that
haven't started yet. It's the list to open if you came to crew;
[Signing up as crew](/help/crew#signing-up) has the rest.

The board keeps its own order, so the columns don't sort. The refresh button
reloads it, though it also updates by itself when a match changes.

## Watching a match

:::snippet watch-match
**Watch** subscribes you to a match you're not in. You get a Discord DM each
time its state changes: checked in, started, finished, confirmed, rescheduled or
cancelled.

Watching is separate from playing and from crewing. If you're already a player
or approved crew on a match you're told about it anyway, and watching it too
doesn't double your DMs.

Tap the bell in the **Watch** column, or at the top right of the match on a phone. It
fills in while you're watching. Tap it again to stop, or press **Unwatch** on
any DM it sends you.
:::

Watching a match and the community's **Watch page** are different things. The
page is a link anyone can open to find the streams; see
[On Air and watching](/help/on-air#the-watch-page).

## On a phone

On a phone, a tablet, or a narrow laptop window, each line becomes a short card:
the time on the left, the players and tournament beside it, and the bell at the
top right. Your **Acknowledge** and each crew role's **Sign up** or **Withdraw**
sit underneath, so you don't have to open the match to use them. Tap the names
for the details.

![A match on a phone: its start time, Player One vs Player Two, Wizzrobe Cup on Stage 3, a Live chip, the bell, and Commentary 0/2 underneath](/static/help/schedule-board/card-phone.webp "One match, as a card on a phone.")

On a computer, the gear beside **Export CSV** lets you choose which columns you
see and in what order. That choice is saved to your account, and it doesn't
change what anyone else sees.
