---
title: Running a tournament on Challonge
slug: staff-challonge
icon: account_tree
order: 242
feature: CHALLONGE
audience: staff
roles: STAFF
summary: Connecting Challonge, linking a bracket, matching its entrants to members, and moving it through its stages.
---

When a tournament's bracket lives on Challonge, Wizzrobe mirrors it. The bracket
decides who plays whom, players book their own matchups from it, and confirmed
results go back to Challonge by themselves. The Challonge tab is under Admin →
Challonge, in Online play.

## Connecting the account

Wizzrobe reads and writes brackets through one shared Challonge account. The
connection card at the top of the Challonge tab shows who it's signed in as and
how many API requests it's used this month. The count turns red at 80% of the
quota.

If your brackets belong to a Challonge community (a page like
`speedgaming.challonge.com`), type its subdomain in **Add a community** before you
press **Connect Challonge**, and sign in as one of that community's admins. If you
skip that, Challonge won't show Wizzrobe the community's tournaments.

The card lists every community you've connected with, plus any community a linked
tournament lives on. **Reconnect** asks Challonge about each of them again, with
one approval screen per community, so you only ever type a community once. Remove
one with its ×. You can't remove a community that linked tournaments still use.

If the stage changes in a linked tournament's ⋮ menu are greyed out, press
**Reconnect**. Older connections didn't get permission to change a tournament's
stage. **Disconnect** stops every linked tournament syncing until someone
reconnects, so it asks first.

## Linking a bracket

Open the tournament on Admin → Tournaments and find Challonge under Integrations.
Paste the Challonge tournament's URL or ID and press **Link & Sync**. The
tournament has to be saved first, so you won't see this section while you're
creating one.

The bracket has to belong to the connected Challonge account or live in one of its
communities. Being an admin on someone else's bracket isn't enough, because
Challonge won't show it to Wizzrobe. Ask its owner to move it into your community.

Linking does three things.

- It imports every entrant and match from the bracket.
- It matches each entrant to a member who's linked that Challonge account on their
  Profile.
- It turns off **Players may request matches**, since a bracket-run tournament only
  schedules the matchups its bracket produces.

Players can't sign up for a linked tournament on the Tournaments tab either. Its
entrants are whoever's in the bracket.

A tournament runs on Challonge or on a native Wizzrobe bracket, never both. If it
already has a native bracket, linking is refused.

## Keeping it in sync

:::snippet admin-challonge-sync
Challonge can't tell Wizzrobe when something changes on its site. Wizzrobe
re-reads the bracket when you link it, when you press **Sync** on the Challonge
tab, when you change its stage from Wizzrobe, and after it pushes a result. If you
edit the bracket on Challonge's own site, nothing here changes until one of those
happens.
:::

Each linked tournament on the Challonge tab is a card with its stage, when it last
synced, a **Sync** button (1) and a ⋮ menu (2) for everything else. Press **Sync**
after any change you make on Challonge.

![The Challonge tab: the connected account and request count, then a linked tournament with its stage and last sync time, its Sync button marked 1 and its ⋮ menu marked 2 and open, showing Finalize groups and start bracket, Entrants (marked 3) and Unlink from Challonge](/static/help/staff-challonge/linked.webp "One linked tournament in its group stage, with its ⋮ menu open. **Entrants** (3) is covered below.")

## Matching entrants to members

A player who's linked their Challonge account on their Profile is matched to their
entrant automatically. Anyone added to the bracket by name has no account to match,
and none of their matches can be booked until someone's assigned.

**Entrants**, in the tournament's ⋮ menu on the Challonge tab, lists the bracket's
entrants with the unmatched ones first.

| Chip | Means |
|---|---|
| {chip:pending:Not linked} | Nobody is matched. Their matches can't be booked |
| {chip:live:Assigned by hand} | Staff picked the member. Survives every sync |
| {chip:ok:Challonge account} | Matched through the player's own linked account |

Pick the member under **Wizzrobe user** (1) and press **Assign** (2). **Clear** (3)
removes a hand assignment and falls back to whoever has that Challonge account
linked, if anyone. A hand assignment beats a linked account, and the dialog warns
you when it's overriding one.

![The Entrants dialog listing a name-only entrant marked Not linked, two assigned by hand, and two matched through their Challonge accounts; the first Wizzrobe user picker is marked 1, its Assign button 2, and the first Clear button 3](/static/help/staff-challonge/entrants.webp "Unmatched entrants sort to the top.")

At the desk, the quickest fix is usually to have the player link Challonge on their
Profile, then press **Sync**.

## Moving through stages

The tournament's ⋮ menu on the Challonge tab offers the next stage change the
bracket is ready for, and only that one. Each one asks you to confirm.

| The bracket is | The menu item |
|---|---|
| Not started | **Start tournament**, or **Start group stage** if it has groups |
| Group stage underway | **Finalize groups and start bracket**. Every group match has to be finished first |
| Groups finalized | **Start bracket** |
| Awaiting review | **Finalize tournament** |

Each change re-syncs right away, so the next round's matches are bookable as soon
as it's done. Starting locks the entrant list on Challonge. You can't reset a
bracket from here, because that wipes results. Do it on Challonge.

## Results

When a bracket match is confirmed, the winner goes to Challonge and the bracket
re-syncs, which opens up the next matchups. If a result's wrong, fix it on
Challonge and press **Sync**.

## Unlinking

**Unlink from Challonge**, at the bottom of the tournament's ⋮ menu, asks first,
then removes the mirrored entrants and bracket matches from Wizzrobe. The bracket
on Challonge isn't touched, and linking again re-imports it. Matches that are
already scheduled stay exactly as they are. Unlinking is also how you move a
tournament from Challonge to a native bracket.
