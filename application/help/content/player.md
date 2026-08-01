---
title: Being a player at the event
slug: player
icon: videogame_asset
order: 40
summary: Your Schedule, acknowledging a match, getting one scheduled, and what happens to your result.
---

This is how the app works for a player. What happens **on the floor** — check-in
and stations, what you can have at your station, stage matches, what to do when
something breaks — is set by the event rather than by the app, so where your
community publishes one it lives under **Event Information** in the sidebar.

## Your Schedule

The **Player** tab shows only your own matches. It is the one to check when you
want to know where you have to be and when — the full board on the Schedule tab
shows everybody's.

Times are shown in your local time.

:::snippet player-schedule
**Your Schedule** lists the matches you are playing in, in your local time. The
Schedule tab shows every match in the event; this one shows only yours.
:::

## Acknowledging a match

When you are scheduled into a match, the bot DMs you with an **Acknowledge**
button. Pressing it tells staff you have seen the time and intend to be there.

It is not a requirement — nobody is stopped from playing for not acknowledging.
It is, though, genuinely useful to the on-call admin and your proctor: it tells
them you know about the match. They work from the unacknowledged list to decide
who to chase, so acknowledging is the difference between being left alone and
being tracked down.

## Getting a match scheduled

There are two ways a match gets on the board, and which one applies depends on
the tournament.

- **You request it.** Use **Submit Match** to propose a tournament, an opponent
  and a time. You have to have opted into the tournament first.
- **It comes from a bracket.** In a bracket-run tournament you do not submit
  matches. Your next matchup appears on the Player tab under *Upcoming matches
  to schedule* — pick a time there and your opponent confirms it.

:::snippet match-request
**Submit Match** proposes a new match: a tournament, your opponent and a time.

You must be opted into the tournament to pick it. If the dropdown is empty,
either you have not opted into anything, or your tournaments are run from a
bracket — in which case you schedule your matchup from **Your Schedule**
instead, not from here.
:::

### Suggest a time

:::snippet suggest-time
**Suggest a time** fills in a slot for you. It looks for a time that sits inside
the availability windows both players entered, falls within the event's operating
hours, and avoids a moment the venue is already busy.

It fills the fields in — it does not book anything. Review what it picked and
change it if it does not suit.

If neither player has entered any availability it still suggests a quiet time; it
just has less to work with. Add your windows under **My Availability**.
:::

## When you can play

:::snippet player-availability
**My Availability** on Home is where you add the windows when you can *play*.

It feeds one thing: **Suggest a time**. When you or your opponent are picking a
slot for a match, that button looks for a time inside the windows both of you
entered, within the event's hours, avoiding a moment the venue is already busy.
The more you enter, the better a time it can find.

It is not a roster staff work from — nobody is reading your windows and
scheduling you into them. If you enter nothing, Suggest a time simply has less
to go on.

This is separate from the availability editor on the Volunteer tab, which is when
you can *work*. Filling in one does not fill in the other.
:::

## Your result

The proctor records the winner when the match ends, and the board goes to
{state:Finished}. That is not the official result yet — a staff member reviews
it and confirms it, which moves the match to {state:Confirmed}.

If the two of you disagree about what happened, tell the proctor before you
leave. They record their best call and flag the match for a staff member to look
at, with a note about what was in dispute. Staff settle it when they confirm the
result.

## If something changes

Rescheduled and cancelled matches DM everyone involved. If your match moves, you
will hear about it — you do not need to keep refreshing the board.
