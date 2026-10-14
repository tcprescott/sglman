---
title: ADA accommodation requests
slug: staff-ada
icon: accessible
order: 248
feature: ADA_ACCOMMODATIONS
audience: staff
roles: STAFF
summary: Working the ADA request queue, what proctors see once a request is arranged, and keeping the notes private.
---

Attendees ask for an ADA accommodation from their Profile. Staff work the requests
on **Admin → Members → ADA requests**. The number on that tab counts the requests
that still need you.

## The queue

:::snippet admin-ada-queue
The queue lists open requests, oldest first, with the attendee's own details and
your staff notes side by side. Tick **Show withdrawn** to see requests attendees
have taken back. Press **Update** on a row to set its status and write notes
only staff can read. Proctors see an "ADA:" line on the match once it's
Arranged, never the notes.
:::

You get a Discord DM when a request opens, with a button that opens it here. The
DM names the attendee and never what they asked for.

On the Members tab, the **ADA** column shows each person's request status, and
ticking **Needs ADA** under **Filters** narrows the table to people with one open.

![The ADA requests tab listing four requests with their status, the attendee's details and staff notes, one marked Changed since arranged, with Show withdrawn marked 1 and the first row's Update button marked 2](/static/help/staff-ada/queue.webp "The ADA queue, oldest first: **Show withdrawn** (1), and **Update** (2) on each row.")

## Working a request

**Update** on a row opens the request. Set its status and write notes for other
staff:

| Status | Use it when |
|---|---|
| {chip:pending:New} | The attendee has just asked. Nobody has picked it up |
| {chip:live:Acknowledged} | Someone is on it but it isn't in place yet |
| {chip:ok:Arranged} | It's sorted. Proctors are told to check with staff |
| {chip:neutral:Withdrawn} | The attendee took the request back. Only they can reopen it |

The attendee sees the status on their Profile, but never your notes. Nothing DMs
them when you change it.

## What proctors see

Once a request is **Arranged**, each of the attendee's matches on the Admin →
Schedule and Proctor Station run sheets carries an "ADA:" line with their name.
Open the match and its **Ready to play?** checklist has a
*name: ADA accommodation* button under the players. Staff who tap it see the
staff notes. Proctors see only that something has been arranged and to check with
staff. Tournament admins and crew coordinators don't see any of it.

So write the notes for whoever is on the floor: what's been set up and where, in a
line or two.

## When an attendee changes an arranged request

If the attendee edits their details after you've arranged it, the request stays
Arranged so the proctors don't lose the "ADA:" line, and it gets a
{chip:pending:Changed since arranged} chip. You get one DM about it.

Open it and you'll see what was arranged next to what they're asking for now.
Check the arrangement still covers it, update your notes if it doesn't, and press
**Save and mark reviewed**.

## Keeping it private

Only this community's staff can read the notes, and the attendee's details never
leave the app: no webhook, API or export to another service carries them. Even
so, privacy can't be guaranteed, so keep medical and personal detail out of the
notes. If you need to discuss it, talk to the attendee directly.
