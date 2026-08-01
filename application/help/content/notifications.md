---
title: Notifications and Discord DMs
slug: notifications
icon: notifications
order: 70
summary: What the bot DMs you, what each button does, and what to do when nothing arrives.
---

Wizzrobe tells you things by Discord DM. There is no email and no SMS.

## What you get DMed

| You are | You hear about |
|---|---|
| A player | Being scheduled, rescheduled or cancelled; your match being confirmed |
| Crew | Your signup being approved, and approval being withdrawn |
| A volunteer | Being assigned a shift, and a reminder before it starts |
| Watching a match | Every state change on it |

## The buttons on a DM

:::snippet dm-buttons
DMs carry buttons so you can answer without opening the site.

| Button | What it does |
|---|---|
| **Acknowledge** | On a match DM: tells staff you have seen the time. On a crew approval DM: confirms you can cover the slot. |
| **Unwatch** | Stops the updates for that match. |

Pressing a button in Discord does exactly what the equivalent control on the site
does, same record, same result. Use whichever is in front of you.
:::

You can start watching a match only from the site. Discord can stop it, not start
it.

## When DMs do not arrive

Almost always one of three things:

1. **Your Discord privacy settings block DMs from server members.** Open the
   community's server settings in Discord and allow direct messages.
2. **You have blocked the bot**, or it shares no server with you. Rejoin the
   community's server.
3. **You are not the person the app thinks you are.** Check that the Discord
   account you are signed in with is the one you actually use.

If you fix your settings, DMs resume from the next event, but the ones you
missed are not resent. Check the schedule board for anything you might have
missed.

## Where your settings live

Everything is on the **Profile** tab, under *Notifications*.

:::snippet notification-settings
**Send me notifications about match updates** is the master switch. Turn it off
and nothing is sent, neither Discord DMs nor device notifications, whatever
else is set below it.

**Devices** adds browser push on the device you are holding. It mirrors the same
DMs rather than replacing them, and it is still governed by the master switch.

**Match alerts by tournament** is a *follow*, not a consequence of playing. Pick
a level per tournament:

| Level | You hear about |
|---|---|
| None | Nothing from that tournament |
| Streamed only | Its streamed matches being scheduled |
| Streamed & Candidates | The above, plus matches that *may* be streamed |
| All matches | Every match it schedules |

You do not have to be enrolled in a tournament to follow it.
:::

## Turning it down

If one tournament is noisier than you want, set its level to **None** rather than
blocking the bot. Blocking the bot also cuts off the DMs you do want: being
told your match moved, or that you have been approved for a slot.
