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

Members ask for an ADA accommodation from their Profile. Staff work the requests
on **Admin → Users → ADA requests**. The number on that tab counts the requests
that still need you.

## The queue

:::snippet admin-ada-queue
The queue lists open requests, oldest first, with the member's own details and
your staff notes side by side. Tick **Show withdrawn** to see requests members
have taken back. Press **Update** on a row to set its status and write notes
only staff can read. Proctors see an icon once it's Arranged, never the notes.
:::

You get a Discord DM when a request opens, with a button that opens it here. The
DM names the member and never what they asked for.

On the Members tab, the **ADA** column shows each member's request status, and
the **Needs ADA accommodation** filter narrows the table to people with one open.

![The ADA requests tab listing four requests with their status, the member's details and staff notes, one marked Changed since arranged](/static/help/staff-ada/queue.webp "The ADA queue, oldest first.")

## Working a request

**Update** on a row opens the request. Set its status and write notes for other
staff:

| Status | Use it when |
|---|---|
| {chip:pending:New} | The member has just asked. Nobody has picked it up |
| {chip:live:Acknowledged} | Someone is on it but it isn't in place yet |
| {chip:ok:Arranged} | It's sorted. Proctors are told to check with staff |
| {chip:neutral:Withdrawn} | The member took the request back. Only they can reopen it |

The member sees the status on their Profile, but never your notes. Nothing DMs
them when you change it.

## What proctors see

Once a request is **Arranged**, the member gets an accessibility icon beside their
name on the Schedule and on the Proctor Station board. Staff who tap it see the
staff notes. Proctors see only that something has been arranged and to check with
staff. Tournament admins and crew coordinators don't get the icon.

So write the notes for whoever is on the floor: what's been set up and where, in a
line or two.

## When a member changes an arranged request

If the member edits their details after you've arranged it, the request stays
Arranged so the proctors don't lose the icon, and it gets a
{chip:pending:Changed since arranged} chip. You get one DM about it.

Open it and you'll see what was arranged next to what they're asking for now.
Check the arrangement still covers it, update your notes if it doesn't, and press
**Save and mark reviewed**.

## Keeping it private

Only this community's staff can read the notes, and the member's details never
leave the app: no webhook, API or export to another service carries them. Even
so, privacy can't be guaranteed, so keep medical and personal detail out of the
notes. If you need to discuss it, talk to the member directly.
