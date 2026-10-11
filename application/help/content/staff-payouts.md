---
title: Prize payouts
slug: staff-payouts
icon: payments
order: 246
feature: PAYOUTS
audience: staff
summary: Setting a tournament's prize pool, splitting it by placement, naming the winners, and copying the payout block.
---

:::snippet admin-payouts
**Admin → Payouts** records what each placement of a tournament wins and builds
the block you paste when the money goes out. Staff see every tournament. A
tournament admin sees only their own.
:::

The table shows each tournament's pool, bonus and total, how many places are
paid, how much of the pool is allocated, and a status:

| Status | Means |
|---|---|
| No split | Nobody has set out the places yet |
| {chip:pending:Winners not named} | The split exists but at least one place has no winner |
| {chip:ok:Ready} | Every place has a winner. Safe to copy |

## The pool

The **Prize pool** button on a row (the payments icon) sets the advertised pool
and any bonus on top. Shares come out of the two added together. Leave a field
blank while nobody has decided it; blank and zero aren't the same thing.

Change the pool whenever it moves. Every share is worked out from it each time
it's read, so nothing else needs editing.

## The split

**Edit split** (the leaderboard icon) lists one row per paid place: the place,
its share as a percentage, and the winner. **Add place** adds a row.

Shares can add up to less than 100%. Whatever's left over is unallocated, and the
Allocated column shows it. They can't add up to more.

For a joint placing, add two rows with the same place and give each its own
share. Two players tied for third at 10% each are two 10% rows, not one 20% row
split later.

You can save the split before the tournament finishes and fill in the winners
afterwards. The winner list holds the tournament's entrants, plus anyone already
named.

## Copying the payout block

**Copy for Matcherino** (the copy icon) puts the block on your clipboard, ready to
paste wherever your payouts get sent from. It opens with the total pool and the
bonus, then one line per place:

| Line | Example |
|---|---|
| A named winner | `1st place - Jemgold (jemgold#100234): 50% / $550.00` |
| No handle on file | `3rd place - greenpotion (no Matcherino handle): 10% / $110.00` |
| Nobody named yet | `3rd place - (unassigned): 10% / $110.00` |

Each winner's Matcherino handle comes from their Profile. A winner who hasn't
entered one is called out, so you know who to chase before the run.

Amounts are rounded to the cent per row, so the total paid can come out a cent
under the pool.
