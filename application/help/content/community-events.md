---
title: Community events
slug: community-events
icon: groups
order: 67
feature: COMMUNITY_EVENTS
summary: Finding meetups and side events attendees are running, getting a reminder or RSVPing, and listing your own.
---

Community events are the meetups, panels, side tournaments and board game
nights that attendees run for each other. They aren't official event
programming, and the page says so at the top: staff don't endorse what's
listed, they just give it somewhere to live.

You need to be a member of the community to see the listing or add to it.

## Finding events

Open **Community Events** in the side menu. It lists every event that hasn't
finished yet, grouped by day, soonest first. Each card shows the time and
length, where it is, and who's hosting. An event that's running right now
carries a {chip:live:Happening now} chip.

Tap an event's title for its own page, with the full description.

## Getting a reminder or RSVPing

:::snippet community-events-attend
Each event has a button, and which one depends on the host.

| You see | What it does |
|---|---|
| **Remind me** | Sends you a Discord DM shortly before it starts. The button turns into **Subscribed**; tap that to stop the reminder. |
| **RSVP** | Tells the host you're coming, and gets you the same reminder. The button turns into **Going**; tap that to cancel your RSVP, which cancels the reminder too. |
| **Full** | The host set a cap and every place is taken. If someone cancels, the button comes back. |

If you tapped **Remind me** before the host switched RSVPs on, you keep your
reminder: the card shows **Subscribed** beside **RSVP** so you can still turn it
off.

The card counts how many people are going (and the cap, if there is one) or how
many have subscribed.

You'll also get a DM if the event moves to a new time or is called off. All of
these are DMs, so they only reach you while Discord DMs are on in your
[notification settings](/help/notifications#where-your-settings-live).
:::

![Community Events on a phone: the not-official notice and Submit an event, then events grouped by day. Morning coffee run is Happening now with a Remind me button marked 1, Board game night shows 2 of 6 going with an RSVP button marked 2, and Speedrun trivia shows 2 of 2 going with a greyed-out Full button marked 3. Your events at the bottom lists a cancelled event](/static/help/community-events/listing-phone.webp "**Remind me** (1), **RSVP** (2) and **Full** (3), depending on the event.")

The reminder goes out 30 minutes before the start unless staff have set a
different lead time for the community.

## Submitting your own

:::snippet community-events-submit
Tap **Submit an event** on the Community Events page. Give it a **Title**, when
it **Starts**, and how long it runs (anywhere from 5 minutes to 72 hours).
**Where** and the **Description** are optional, but people are more likely to
turn up when they know where to go and what to bring. The description takes
headings, lists and links.

Switch on **Take RSVPs** if you want to know who's coming. You can set a
**Cap (optional)**; leave it blank for no limit. Once the cap is reached the
button reads **Full** for everyone else.

What happens after **Submit** depends on the community:

- Where staff review events (the default), yours waits until they look at it.
  You'll get a DM when they approve it, or when they turn it down and why.
- Where they don't, it's listed straight away.

The form tells you which applies before you submit.
:::

![The Submit a community event form on a phone, scrolled to Length, Where and Description, with the Take RSVPs switch turned on and its Cap (optional) box marked 1, and the Submit button marked 2](/static/help/community-events/submit-phone.webp "Switch on **Take RSVPs** to set a cap (1), then **Submit** (2).")

Your submissions appear under **Your events** at the bottom of the page, each
with its status:

| Status | Means |
|---|---|
| {chip:pending:Waiting for review} | Staff haven't looked at it yet. Only you and staff can see it. |
| {chip:ok:Listed} | It's on the listing and people can subscribe or RSVP. |
| {chip:cancelled:Not listed} | Staff turned it down, or took it off the listing. Their reason shows underneath as "Staff said: …". |
| {chip:neutral:Cancelled} | You or staff called it off. |

## Seeing who's going

On your own event's page, a **Who's going** list shows everyone who has RSVP'd,
in the order they did. Only you and staff see the names; everyone else sees the
count. The list only appears when the event takes RSVPs.

## Changing or cancelling your event

Open the event's page and tap **Edit** or **Cancel event**.

An edit to a listed event goes live straight away, without another review. If
you move the start time, everyone subscribed or going gets a DM with the new
time and their reminder is reset to match. You can lower the cap, but not below
the number of people already going; if you try, the app tells you how many
that is.

If staff turned your event down, fix whatever their reason asked for and save
it. That sends it back to {chip:pending:Waiting for review} and lets staff know.

**Cancel event** asks first. The event comes off the listing, and everyone who
subscribed or RSVP'd gets a DM saying it's off. A cancelled event can't be
edited or brought back, so submit a new one if plans change again.

## Reviewing events (staff)

This part is for staff. Everyone else can stop reading here.

:::snippet community-events-review
Submissions are in **Admin → Community Events**. You get a DM when a member
submits one, and its button opens the event's review dialog directly. The
**Show** filter starts on *Waiting for review* when anything is waiting.

**Review** on a row opens the event with its description. From there:

| Button | Does |
|---|---|
| **Approve** | Lists it. The host gets a DM. Also puts back an event you took down, though its old subscribers and RSVPs don't come back with it. |
| **Reject** | Turns it down. Write a reason first; the host gets it in a DM and can edit and resubmit. |
| **Take down** | The same as Reject, for an event that's already listed. Anyone subscribed or going is told it's cancelled, and their subscriptions and RSVPs are cleared. |
| **Edit event** (in the ⋮ menu) | Changes the event yourself. It keeps its status. |

Events staff submit are listed straight away, and staff can edit or cancel any
event from its own page, the same as its host.
:::

Two settings live in **Admin → Settings → Community Events**.
**Require staff approval** is on by default; turn it off and members' events
are listed as soon as they're submitted, though you can still take any of them
down. **Reminder lead (minutes)** is how long before an event its subscribers
get their DM. Leave it blank for 30.
