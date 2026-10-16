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
results go back to Challonge on their own. The Challonge tab is **Admin →
Challonge**, under Online play.

## Connecting the account

Wizzrobe reads and writes brackets through one shared Challonge account. The
connection card at the top of the Challonge tab shows who it is signed in as and
how many API requests it has used this month. The count turns red at 80% of the
quota.

If the brackets belong to a Challonge community (a page like
`speedgaming.challonge.com`), type its subdomain in **Add a community** before you
press **Connect Challonge**, and sign in as one of that community's admins.
Without it, Challonge refuses to show Wizzrobe the community's tournaments.

Wizzrobe remembers every community you've connected with, plus any community a
linked tournament lives on, and lists them on the card. **Reconnect** asks
Challonge for each of them again, one approval screen per community, so you only
type a community once. The last screen names no community: it's the one that
lets Wizzrobe see brackets hosted outside any community, so approve that too.
Remove one with its ×. A community that linked
tournaments still use can't be removed.

If the stage changes in a linked tournament's ⋮ menu are greyed out, press
**Reconnect**. Older connections weren't given permission to change a
tournament's stage. **Disconnect** stops every linked tournament syncing until
someone reconnects, so it asks first.

## Linking a bracket

Open the tournament on **Admin → Tournaments** and find **Challonge** under
Integrations. Paste the Challonge tournament's URL or ID and press **Link &
Sync**. The tournament has to be saved first, so this section doesn't appear while
you're creating one.

Linking does three things:

- imports every entrant and match from the bracket
- matches each entrant to a member whose Challonge account is linked on their
  Profile
- turns off **Players may request matches**, because a bracket-run tournament
  schedules only the matchups its bracket produces

Players can't sign up for a linked tournament on the Tournaments tab either. Its
entrant list is whoever is in the bracket.

A tournament runs on Challonge or on a native Wizzrobe bracket, never both. If it
already has a native bracket, linking is refused.

## Keeping it in sync

:::snippet admin-challonge-sync
Challonge can't tell Wizzrobe when something changes on its site. Wizzrobe
re-reads the bracket when you link it, when you press **Sync** on the Challonge
tab, when you change its stage from Wizzrobe, and after it pushes a result. Edit
the bracket on Challonge's own site and nothing here moves until one of those
happens.
:::

Each linked tournament on the Challonge tab is a card with its stage, when it
last synced, a **Sync** button (1) and a ⋮ menu (2) for everything else. Press **Sync**
after any change you make on Challonge.

![The Challonge tab: the connected account and request count, then a linked tournament with its stage and last sync time, its Sync button marked 1 and its ⋮ menu marked 2 and open, showing Finalize groups and start bracket, Entrants (marked 3) and Unlink from Challonge](/static/help/staff-challonge/linked.webp "One linked tournament in its group stage, with its ⋮ menu open. **Entrants** (3) is covered below.")

## Matching entrants to members

A player whose Challonge account is linked on their Profile is matched to their
entrant automatically. Anyone added to the bracket by name has no account to
match, and none of their matches can be booked until someone is assigned.

**Entrants**, in the tournament's ⋮ menu on the Challonge tab, lists the
bracket's entrants, unmatched ones first:

| Chip | Means |
|---|---|
| {chip:pending:Not linked} | Nobody is matched. Their matches can't be booked |
| {chip:live:Assigned by hand} | Staff picked the member. Survives every sync |
| {chip:ok:Challonge account} | Matched through the player's own linked account |

Pick the member under **Wizzrobe user** (1) and press **Assign** (2). **Clear** (3) removes a
hand assignment and falls back to whoever's Challonge account is linked, if
anyone. A hand assignment wins over a linked account, and the dialog warns you
when it overrides one.

![The Entrants dialog listing a name-only entrant marked Not linked, two assigned by hand, and two matched through their Challonge accounts; the first Wizzrobe user picker is marked 1, its Assign button 2, and the first Clear button 3](/static/help/staff-challonge/entrants.webp "Unmatched entrants sort to the top.")

The quickest fix at the desk is usually to ask the player to link Challonge on
their Profile, then press **Sync**.

## Moving through stages

The tournament's ⋮ menu on the Challonge tab offers the next stage change the
bracket is ready for, and only that one. Each asks you to confirm first:

| The bracket is | The menu item |
|---|---|
| Not started | **Start tournament**, or **Start group stage** if it has groups |
| Group stage underway | **Finalize groups and start bracket**. Every group match has to be finished first |
| Groups finalized | **Start bracket** |
| Awaiting review | **Finalize tournament** |

Each change re-syncs straight away, so the next round's matches are bookable as
soon as it finishes. Starting locks the entrant list on Challonge. Resetting a
bracket isn't offered here because it wipes results; do that on Challonge.

## Results

When a match from the bracket is confirmed, the winner is sent to Challonge and
the bracket re-syncs, which opens the next matchups. If a result is wrong, fix it
on Challonge and press **Sync**.

## Unlinking

**Unlink from Challonge**, at the bottom of the tournament's ⋮ menu, asks first,
then removes the mirrored entrants and bracket matches from Wizzrobe. The
bracket on Challonge isn't touched, and linking again re-imports it. Matches
already scheduled stay exactly as they are. Unlinking is also how a tournament
moves from Challonge to a native bracket.
