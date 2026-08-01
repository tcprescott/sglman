---
title: Attending the event
slug: attending
icon: how_to_reg
order: 20
summary: Dev fixture — a public event-information article, so the section renders in a local run.
---

Development fixture content for the `default` tenant. It exists so `/event-info`
has something to draw in a dev run and in the browser-validation loop, and so the
help icons that now read from this section have snippets to open. It is not real
event information for anybody.

The snippet names below deliberately match the ones the app wires icons to —
`check-in`, `player-room`, `player-stage`, `player-trouble`, `player-turnover`.
A fixture that used different names would leave the Player tab's icons blank in
every dev run, which is exactly the regression the icons-resolve test exists to
catch.

## Check-in and stations

:::snippet check-in
A **proctor** checks your match in once both players are seated, and the board
flips to {state:Checked In}. They assign your **station** — the seat you play at
— and its number then shows next to your name on the board.

You do not check yourself in and you do not pick your own seat.
:::

## In the tournament room

:::snippet player-room
Bring your console and your controller; the venue provides the display, the seat
and the power.

Keep it quiet, check the TV is actually sending sound out of its headphone jack
before you start, and be careful about power — the plug you pull may be running
the station next to you.
:::

## If your match is on a stage

:::snippet player-stage
You will know in advance: a stage shows on the match DM and in the *Stage* column
on the board.

A stage is not a proctor's room — the broadcast techs run it, and they will tell
you where to sit and when you are live.
:::

## If something goes wrong

:::snippet player-trouble
Tell the proctor. Almost nothing on the floor is a decision they or you get to
make on the spot — an admin does — so raising it early is the fastest route.
:::

## When your match ends

:::snippet player-turnover
Collect your things and leave the seat genuinely free; the next pair are usually
waiting. You do not need to do anything in the app — the station releases itself
once the proctor records the result.
:::
