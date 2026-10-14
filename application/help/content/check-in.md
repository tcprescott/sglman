---
title: Checking in at the event
slug: check-in
icon: how_to_reg
order: 58
feature: EVENT_CHECK_IN
summary: Checking in when you arrive, and working the check-in desk on your phone: finding people, linking accounts, lanyards, walk-ups, comps and refunds.
---

Checking in at the event is how the event knows you've arrived, and it's where
you pick up your lanyard. It's a different thing from checking a *match* in,
which a proctor does once you're seated to play.

The first section is for everyone. The rest is for the volunteers and staff
working the check-in desk.

## Checking in when you arrive

Go to the check-in desk and give the volunteer the name you bought your badge
under on Matcherino. If they can't find you by name, show them the badge code
from your Matcherino purchase; the desk searches codes too. If someone else
bought your badge for you, give their name or the code.

If your Matcherino purchase isn't connected to your account here yet, the
volunteer asks for your Discord or Twitch name so they can connect the two.
You only do this once: the next event recognises you.

Staff, and volunteers scheduled for enough hours, don't need a badge. You're
already on the desk's list; just give your name.

Once you're checked in, the bot sends you a Discord DM saying so. That DM is a
test as much as a receipt. Match calls, crew asks and shift reminders all arrive
the same way, so if it doesn't reach you, the volunteer will ask you to fix it
on the spot: join the community's Discord server and allow DMs from server
members, or turn Discord DMs back on under
[Profile → Notifications](/help/notifications#where-your-settings-live).

## The desk

:::snippet check-in-desk
The desk is **Check-in Desk** in the menu. It shows there while an event is open, for
anyone with the Check In Desk role and for staff. It's built for a phone.

The top of the desk stays pinned as you scroll: the event name with its sync
button, then the search box, which takes a name or a badge code. The progress bar
reads "212 of 340 checked in" and leaves refunded people out. The filter switch
(All, Not yet, Checked in, Comped, Walk-ups) shows a count on each and wraps onto
a second line on a narrow phone. The sync line says when the roster last came
from Matcherino, which matters when it
[goes amber](/help/check-in#when-the-roster-may-be-out-of-date).

Below that, each person is a card: their name, the account they're linked to and
how, their lanyard, and a big **Check in** button. Someone with no account shows
a **Not linked** button that opens the link dialog. Everything else (changing or
removing a link, undo, the DM retry, removing a walk-up) is in the card's ⋮ menu,
so it's never a stray tap away from the button you use all day. On a screen
1200px wide or more, the desk is a table with the same buttons on each row.
:::

![The check-in desk on a phone: the search box, the progress bar, the filter switch and the sync line, above cards for a Base buyer, a volunteer and someone with no badge; on the first card the Not linked button is marked 1, Check in 2 and the ⋮ menu 3](/static/help/check-in/desk-phone.webp "The desk on a phone: **Not linked** (1), **Check in** (2) and the card's ⋮ menu (3).")

## Finding someone

Search matches the name they bought under, the name of the account they're
linked to, their Discord and Twitch usernames, and every badge code they hold.
It runs on your phone, so results appear as you type even on slow venue wifi.

If nobody matches, try the badge code instead of the name, and check the
filter switch is on **All**. Still nothing means they aren't on the roster: they
may have bought after the last sync, or not bought at all. Send them to staff.

## Checking someone in

:::snippet check-in-lanyard
Tap **Check in**. A bar along the bottom shows "Checked in Sam" and, in bold,
what to give them: "Hand over: VIP lanyard". It stays for eight seconds with an
**Undo** button. After that, undo from ⋮ → **Undo check-in**.

Each person gets one lanyard, the highest they qualify for, in its own colour:

| Lanyard | Colour | Who gets it |
|---|---|---|
| **Staff** | Red | Staff comped for this event |
| **Volunteer** | Purple | Anyone with a published volunteer shift, whether or not they bought a badge |
| **VIP** | Gold | The best badge they hold is a VIP badge |
| **Base** | Blue | The best badge they hold is a Base badge |
| **Day Pass** | Teal | They hold only a Day Pass |

So a staffer who bought a VIP badge still wears Staff.

A note like "+ Base badge" next to the lanyard means they bought more than one
badge, usually one for a friend. The friend isn't on the roster separately, so
hand over a lanyard for each badge.
:::

If two phones tap the same person at once, only one check-in is recorded. The
second phone says who got there first and when.

## Linking an account

:::snippet check-in-link
When someone's Matcherino purchase isn't linked to an account here, tapping
**Check in** opens **Check in** *their name* first. Ask for their Discord or
Twitch name, then pick their account from **Suggestions** or **Search members**.
That links them and checks them in. **Skip, just check in** checks them in
without an account, and **Cancel** records nothing.

Linking is worth the ten seconds. It's what lets the bot reach them during the
event, and it's remembered, so they're recognised automatically next time.
Someone with no account here can still be checked in; skip is fine.

Most buyers are linked before they reach you, matched by the Discord or Twitch
account they bought with. The card says how:

| Card says | Means |
|---|---|
| **via Discord** / **via Twitch** | They bought with the same Discord or Twitch account they use here |
| **seen before** | Linked at an earlier event |
| **via profile handle** | Their profile's Matcherino handle matches the buyer |
| **linked by staff** | Someone at the desk picked the account by hand |
| **Not linked** | Nobody has matched them yet. Tap it to link them; **· 3 suggestions** means the link dialog has accounts with similar names ready to pick |

If a link is wrong, use ⋮ → **Change linked account**, or **Unlink account** if
they have no account here. Someone unlinked on purpose isn't asked again at
check-in.
:::

![The Check in dialog for a buyer with no linked account: no Suggestions for this one, the Search members box marked 1, and the Skip, just check in button marked 2](/static/help/check-in/link-dialog-phone.webp "Checking in someone whose badge isn't linked yet: search for their account (1), or **Skip, just check in** (2).")

## The Discord DM check

:::snippet check-in-dm
Checking in someone with a linked account sends them a short "you're checked in"
DM. A moment later the card shows whether it arrived:

| Card says | What to do |
|---|---|
| **Discord DMs reach them** | Nothing. |
| **Discord won't let us DM them** | Ask them to join the community's Discord server and allow DMs from server members, then ⋮ → **Send the test DM again**. |
| **They've turned Discord DMs off in Wizzrobe** | Ask them to turn DMs on in their Profile. They'll miss match calls otherwise. |
| **Couldn't test their DMs: Discord didn't answer** | A problem on our side, not theirs. Try ⋮ → **Send the test DM again** in a minute. |

Fix it while they're standing at the desk. It's the only time anyone will
notice before they miss a match call.
:::

![A checked-in card saying Discord won't let us DM them, with the fix to ask for](/static/help/check-in/dm-blocked-phone.webp "A DM that didn't get through.")

## Walk-ups

A walk-up is someone checking in without a Matcherino badge. Only staff can add
one, with the add-person button at the top of the desk, beside the sync button.
A desk volunteer sends them to staff.

The **Add walk-up** dialog takes either **A member** (search for their account)
or **Just a name**, and checks them in straight away unless you untick **Check
them in now**. The desk doesn't sell badges, so anyone who needs one buys it on
Matcherino.

Walk-ups are the only rows that can be removed (⋮ → **Remove walk-up**, staff
only, and it asks first). Everyone else comes from Matcherino and would come back on the next sync.

## Comped staff and volunteers

Some people get in without buying a badge. Staff choose who for each event:
everyone with certain roles (usually Staff), and volunteers whose published
shifts add up to the lowest volunteer comp tier. Those hours are *scheduled*
hours, not worked ones, since most shifts haven't happened yet when the desk
opens.

Comped people are already on the roster and show under the **Comped** filter.
Someone comped who also bought a badge is one person, not two, and still gets
the Staff or Volunteer lanyard.

If a volunteer says they should be comped and isn't on the list, their shifts
probably aren't published yet or don't reach the threshold. Send them to staff
or a volunteer coordinator; the desk can't comp anyone. Comped rows also can't
be linked or unlinked at the desk.

## Refunds and people who can't be checked in

:::snippet check-in-withdrawn
A few cards have no **Check in** button, and say why instead:

| Card says | Means |
|---|---|
| **Refunded** | Their badge was refunded on Matcherino |
| **No badge** | Every badge they bought has dropped off the venue's sales |
| **No longer comped** | They were comped and no longer qualify |

These still show under **All**, so a search finds them and you can see what
happened. A desk volunteer sees "No badge to check in with. Send them to staff."
and does just that.

Staff see an outlined **Check in anyway** button instead, behind a confirmation.
:::

![A card marked Refunded with no Check in button, saying No badge to check in with. Send them to staff.](/static/help/check-in/refunded-phone.webp "What a desk volunteer sees for a refunded badge.")

## When the roster may be out of date

:::snippet check-in-sync
The roster comes from Matcherino's badge sales and refreshes itself every few
minutes. The sync line under the filters says how fresh it is:

| Sync line | Means |
|---|---|
| "Synced with Matcherino at 14:05 · 340 with badges" | Normal. |
| "Couldn't reach Matcherino at 14:10, so the roster may be out of date." (in amber) | The last refresh failed. The desk carries on with the last good roster. |
| "Not synced with Matcherino yet." | The event hasn't pulled its first roster. |
| "Comps only" / "Walk-ups only" | This event has no Matcherino venue. That's set up on purpose. |

A stale roster doesn't stop the desk. Every check-in still records, and nothing
already on the list is lost. What it can't show is anyone who bought a badge
since the last good sync, so send them to staff to be added as a walk-up. Tell
staff the line has gone amber too; it usually means the saved Matcherino login
needs replacing.

The round ↻ button beside the event name pulls a fresh roster now.
:::

If the event has been closed, the desk says "This event is closed. You can still
record late check-ins." and works as normal.

## Several phones at once

Every phone on the desk sees the same roster. When someone checks a person in on
another phone, that card updates and flashes on yours. A phone that was locked
catches up when you wake it.

If the venue wifi drops, a banner says "No connection" and taps aren't sent until
it clears. Nothing you tapped while offline was recorded, so tap again once the
banner says you're back online.

**Export CSV** at the bottom downloads the whole roster, whatever the filter.
