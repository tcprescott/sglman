---
title: Async qualifiers
slug: qualifiers
icon: timer
order: 37
feature: ASYNC_QUALIFIERS
summary: Playing a qualifier seed on your own time, submitting your finish, and how the leaderboard scores you.
---

An async qualifier lets you play qualifying seeds whenever suits you inside a
window, instead of in a scheduled match. You start a run, play the seed, type in
your finish time, and a reviewer checks it. When the window closes, everyone's
runs are scored against each other on a leaderboard.

## Finding a qualifier

The **Async Qualifiers** page lists every qualifier your community is running,
newest first, with its window (when it opens and when it closes) and a
description. **Open** takes you into one.

There's no menu item for qualifiers yet, so you'll usually arrive from a link:
organisers post one, and every Discord message about a run you've started has a
button straight back to the qualifier. The list itself is at `/qualifiers` on
your community's site.

## Pools and runs

A qualifier is split into pools, and each pool holds a set of seeds. You get the
same number of runs in every pool, and your result is the total across all of
them. A slot you never play counts as zero, so skipping a pool costs you.

## Starting a run

:::snippet qualifiers-start
Under **Start a run**, every pool you can still play has a **Start:** button
with the pool's name, and a count beside it such as *1 of 2 runs used*. Pressing
it draws a seed and starts your timer in the same moment. You only see the seed
once the clock is running, so be ready to play before you press it.
:::

You can have one run going at a time in a qualifier. You're never handed a seed
you already have a counting run on. The draw is random, except that once some
seeds in a pool have been played noticeably more than others, it hands out one
of the least-played, so every seed ends up with enough runs to set a fair par.

When there's no button, the page says why:

| What it says | What to do |
|---|---|
| *This qualifier opens* and a date | Come back then. |
| *This qualifier isn't accepting runs.* | Organisers have switched it off. |
| *This qualifier closed* and a date | Qualifying is over. Your scores and the leaderboard are on the same page. |
| *No pools have been set up yet* | Organisers haven't added seeds. Check back. |
| *You've used all* … *of your runs in every pool.* | You're done. Wait for your reviews and the close. |
| *You've played every seed available in the pools you have runs left in.* | Tell an organiser: they need to add more seeds. |

A pool line that says *no unplayed seeds left* is the last case for that one pool.

## While your run is going

The page shows a card headed **Your run is in progress** with the pool name, a
link to **Your permalink (open the seed)**, and an Elapsed clock.

Every run has a deadline. The card says *Auto-forfeits at* a time, with a
countdown underneath. It's 12 hours after you started unless your organisers set
a different limit. Shortly before it (an hour, unless they changed that too)
you'll get a Discord DM with a **Submit or forfeit** button. If the deadline
passes, the run is forfeited for you: it scores zero, the slot is spent, and My
runs shows it as *Forfeited (ran out of time)*.

If that happened when it shouldn't have, ask an organiser. They can grant you
another attempt, and it doesn't come out of your own reattempts.

## Submitting your time

:::snippet qualifiers-submit
Type your time into **Finish time (H:MM:SS)** with all three parts, so a
52-minute run is `0:52:10`, not `52:10`. The line under the box reads back what
it understood, in words, so you can catch a slip before it counts. Paste a link
into **VoD URL (optional)** if you recorded the run, then press **Submit**.
:::

The app keeps its own clock from the moment you pressed Start. It won't accept a
time longer than that clock (it allows two minutes for lag). If your time is 15
minutes or more shorter than the clock, it asks *Is that the right time?* before
sending. That's normal if you finished a while ago and are only submitting now,
so submit it. If you dropped a digit, choose **Let me fix it**. Reviewers see
both your time and the app's clock.

Once submitted, the run shows *Awaiting review* and you can start your next one
straight away. You don't have to wait for the verdict.

## Forfeiting

**Forfeit** sits beside Submit and asks before it does anything. A forfeited run
scores zero, uses up the pool slot, and can't be undone. If you have reattempts
left, the confirmation says so.

## Reviews

A reviewer approves or rejects each submitted run, and you get a Discord DM
either way. A rejection always carries the reviewer's reason, which also appears
in the **Reviewer note** column of My runs. A rejected run counts as zero and
still uses its slot.

Reviewers can change a verdict later. If one does, the DM says the earlier
result changed, so you're not left with two messages that disagree. Nobody can
review their own run.

## My runs

Every run you've started is listed under **My runs**, with the seed you played so
you can quote it if you disagree with a verdict.

| Column | What it shows |
|---|---|
| Status | *Running*, *Finished*, *Forfeited*, *Forfeited (ran out of time)*, or *Disqualified* (only from a live race) |
| Review | *Awaiting review*, *Approved*, *Rejected*, or *Voided* for a run that no longer counts |
| Against par | While the window is open: *Under par*, *Near par* or *Above par* |
| Score | Replaces Against par once the qualifier closes |
| Reviewer note | The reason behind a verdict, or why a run was voided |

You see a band instead of a number while the qualifier is open because the exact
score, together with your own time, would tell you the seed's par, and par stays
hidden while other people are still running. *Under par* means at least 5%
faster than par, *Above par* more than 5% slower. A forfeit has no time, so it
shows *Above par*.

## Reattempts

:::snippet qualifiers-reattempt
When a qualifier allows reattempts, My runs says how many you have left, and a
**Reattempt** button sits on each finished or forfeited run. Using one voids
that run (its score is thrown away and it stops counting) and frees its pool
slot for a fresh draw. You have to give a reason. It doesn't bring back the run
you voided, so only spend one on a run you'd rather replace.
:::

Reattempts are only offered while the window is open. A reviewer can also void a
run for you, for a bad seed or a mis-clicked forfeit, without touching your own
allowance. You'll get a DM with their reason, and My runs shows *Voided by a
reviewer* beside it.

## Scoring and the leaderboard

:::snippet qualifiers-scoring
Each seed has a par: the average of the fastest approved times on it (the five
fastest, unless organisers changed that). Finishing at par scores 100. Every
percent slower than par costs a point, so twice par scores 0, and the best
possible score is 105. Forfeits, rejected runs and unplayed slots score 0.
:::

Par moves as more runs are approved, so your score can change after you've
finished, when someone else's run on the same seed is approved.

The **Leaderboard** is hidden until the qualifier closes, either at its close
time or when organisers switch it off. A qualifier with no close time stays
hidden until they do. Once it opens up:

- **Score** is your total, with unplayed slots counting zero. Ranking is by Score,
  and tied players share a rank.
- **Estimate** fills your unplayed slots with your own average, so a player who
  didn't finish every pool isn't understated.
- **Slots** shows how many of your slots you used, out of the total.

The board can run to hundreds of players, so use **Find a player…** to jump to
your own line.

## Live races

Organisers can also run a pool's seed as a live race on racetime.gg, where
everyone plays it at once in one room. Your result comes straight from the room
and counts as approved, with no review. It uses one of your runs in that pool. If
you'd already used them all, the result is kept in your history but doesn't
count.

The room only knows your racetime.gg account, so link it under **Connected
accounts** on your Profile before you race, or your result can't be matched to
you. Some seeds are set aside for live races and are never drawn when you start
a run yourself.

## What happens next

When the window closes, My runs switches to exact scores and the leaderboard
opens. What a placing earns you is up to your organisers, so watch their
announcements for how the qualifier feeds the event.
