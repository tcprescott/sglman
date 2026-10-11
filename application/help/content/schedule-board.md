---
title: Reading the schedule board
slug: schedule-board
icon: schedule
order: 20
summary: What every column on the Schedule board means, what each match state tells you, and how to filter it down to what you need.
---

The **Schedule** view on the **Event** tab lists every match in the event. It's
the same board for everyone: players, crew and spectators all see it. The two
other views on that tab read the same matches differently. **On Air** lays out
one day by stage (see [On Air and watching](/help/on-air)), and **Brackets**,
where a community uses them, shows the tournament structure.

## The columns

:::snippet schedule-columns
| Column | What it tells you |
|---|---|
| **Tournament** | Which tournament the match belongs to. |
| **Scheduled At** | When it starts, in your local time. |
| **State** | How far along the match is. See the states below. |
| **Players** | Who's playing, whether each has confirmed they'll play, and their station once they're seated. |
| **Commentators** / **Trackers** | Who has signed up as crew and who's been approved, plus your own **Sign up** or **Withdraw**. |
| **Watch** | The bell. Tap it to get a DM every time this match changes. |
| **Stage** | Which stage it's on. If the stage is streamed, its name links to the stream. |
| **Generated Seed** | The seed for the match, once one exists. |
:::

An empty cell means there's nothing to show yet, not that something's wrong. A
match usually gets its stage, its seed and its crew at different times.

Beside each player's name, a green person icon means they've confirmed they're
playing, and an orange outline means they haven't yet. That's the player answering
a DM, not a check-in: check-in happens at the venue and shows in the State
column. A chair chip with a number is the station they've been seated at.

## Match states

:::snippet match-states
The **State** column moves through five values, in order:

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

Most columns sort when you tap the header. The refresh button reloads the
board, though it also updates by itself when a match changes.

## Watching a match

:::snippet watch-match
**Watch** subscribes you to a match you're not in. You get a Discord DM each
time its state changes: checked in, started, finished, confirmed, rescheduled or
cancelled.

Watching is separate from playing and from crewing. If you're already a player
or approved crew on a match you're told about it anyway, and watching it too
doesn't double your DMs.

Tap the bell in the **Watch** column, or on the match's card on a phone. It
fills in while you're watching. Tap it again to stop, or press **Unwatch** on
any DM it sends you.
:::

Watching a match and the community's **Watch page** are different things. The
page is a link anyone can open to find the streams; see
[On Air and watching](/help/on-air#the-watch-page).

## On a phone

On a phone, a tablet, or a narrow laptop window, the board becomes a stack of
cards instead of a table, one card per match, because a table that wide pushes
its buttons off the screen. The same information is in both; the cards reflow
it. The time and state sit at the top, then the players, then crew, stage and
seed, and the bell at the bottom. A match staff are considering for stream but
haven't given a stage yet shows a **candidate** chip on its Stage line.

![A match card on a phone: the start time and a Started chip, two players with orange outline icons and station numbers, the tournament, the stage, and the bell](/static/help/schedule-board/card-phone.webp "One match, as a card on a phone.")

You can also choose which columns you see and in what order, per device. That
choice is yours alone, and it doesn't change what anyone else sees.
