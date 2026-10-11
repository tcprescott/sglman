---
title: Building the volunteer schedule
slug: coordinating-volunteers
icon: event_available
order: 210
feature: VOLUNTEERS
roles: STAFF, VOLUNTEER_COORDINATOR
summary: Positions, shifts, the auto-scheduler, drafts and publishing, and covering a dropped shift.
---

This is the coordinator's side of [volunteering](/help/volunteering). It lives on
**Admin → Vol. Schedule**, which staff and anyone with the Volunteer Coordinator
role can open. The roster, hour totals and the export are in
[Volunteer roster, hours and export](/help/volunteer-hours-and-export).

:::snippet vol-schedule
**Vol. Schedule** shows one event day at a time. Pick the day at the top; the
list comes from the event dates in Settings → Event. A day runs from midnight to
6am the next morning, so a shift that ends after midnight still shows on the day
it started.

The chips above the grid answer "how covered is today?": slots filled against
slots needed, how many are still open, how many assigned volunteers haven't
acknowledged yet, and how many draft assignments haven't been published.

Below that, every active position gets a card with its shifts for the day. A
shift's badge reads filled/needed and turns amber while it's short.
:::

## Positions

A position is a job, like Registration or Stage Crew. **Manage positions** lists
them all and opens each one for editing.

| Field | What it does |
|---|---|
| Name and description | What volunteers see on their shift card. |
| Display order | Where the position sits in the grid. Lower comes first. |
| Active | Untick to retire a position. It leaves the grid and the auto-scheduler, and its old shifts stay on record. |
| Shift length and stagger | Leave both blank for the four fixed blocks. Set both to make **Generate standard shifts** produce rolling shifts instead. |

**Generate standard shifts** on a position's card fills the day for you. With no
length or stagger set, you get four blocks on the community's clock: 08:00–12:00,
12:00–16:00, 16:00–20:00 and 20:00–midnight. With both set, you get shifts of that
length starting every stagger interval across the same 08:00 to midnight window,
so people hand over one at a time instead of all at once. Every generated shift
needs one person; edit a shift to ask for more.

### Roles a position grants

A position can hand out an app role to whoever works it, so the people on the
Proctor position get the Proctor role without anyone granting it by hand. Staff
set this up under **Admin → Settings → Discord**, in the Volunteer positions
section at the bottom.

The role arrives when someone's assignment is published and stays while they
hold any published assignment to that position, finished shifts included. A
draft doesn't count. Unassigning, a volunteer giving the shift back, or deleting
the shift or position takes it away again. A role someone was granted by hand is
never touched.

Only operational roles can be mapped: Proctor, Stream Manager, Triforce
Submitter, Equipment Manager, Volunteer and Check-in Desk. Staff and the roles
that run a subsystem are deliberately off the list, because whoever assigns
shifts would otherwise be able to give those out.

## Shifts

**Add shift** on a position's card opens the shift form: the position, start and
end, an optional label, how many people it needs, and optional notes. The
volunteer sees the notes on their shift card, and you see a note icon on the
shift that shows them on hover.

What happens to the people already on a shift depends on what you change:

| You change | What they hear |
|---|---|
| Label, notes or slots needed | Nothing. |
| Start or end time | A DM asking them to acknowledge again. Their old acknowledgment is cleared and the reminder is re-armed for the new time. |
| Delete the shift | A DM saying they're off it, for anyone whose shift hasn't finished. |

Check-ins are never cleared by an edit.

## Assigning someone yourself

**Assign** on a shift opens a picker of the volunteer pool: everyone in this
community with the Volunteer or Staff role. Each name carries what they said
about that time:

| Badge | Means |
|---|---|
| {chip:ok:Preferred} | They'd like this slot. |
| {chip:ok:Available} | They can work it. |
| {chip:cancelled:Unavailable} | They ruled this time out. |
| {chip:neutral:Not stated} | None of their availability windows cover this shift. |

If anyone is qualified for the position, the picker shows only them until you
tick **Show unqualified volunteers**. Qualifications are set per person on the
roster.

The app refuses two things: putting someone on a shift they're already on, and
putting them on a shift that overlaps one they already have. It warns, but lets
you go ahead, when the shift is already full or the person said they're
unavailable or never said they're free.

A hand assignment is published straight away. The volunteer gets a Discord DM
with an **Acknowledge** button, and their chip on the shift tells you where it
stands:

| Chip | Means |
|---|---|
| {chip:live:Name} | A draft. They haven't been told. |
| {chip:neutral:Name} | Published, not acknowledged yet. |
| {chip:ok:Name} | Acknowledged. |

The **×** on a chip removes that person. If the assignment was published they get
a DM saying so; removing a draft is silent.

When someone turns up, press the check-in button beside their name. A checked-in
volunteer can't give the shift back from their own phone, so they have to come
and talk to you.

## The auto-scheduler

:::snippet vol-autofill
**Auto-fill from availability** drafts assignments for the open slots on the day
you're looking at. It asks three things first:

- **Maximum hours per volunteer**, across this day. It starts at 8. Leave it blank
  for no limit.
- **Also use volunteers who have not marked this time.** Off by default, so only
  people who said they're free are used. Turn it on and people with no stated
  availability are used too, after everyone who did say something. Anyone who
  marked the time unavailable is never used either way.
- **Positions** to fill. Re-running for one position replaces that position's
  drafts and leaves the others alone.

For each open slot it picks, in order: someone qualified for the position, then
Preferred over Available over not stated, then whoever has the fewest hours so
far, then by name. It never double-books anyone and never takes someone past the
hour limit. Hand assignments already on the day count toward both.

A volunteer with qualifications recorded is only placed in those positions. One
with none recorded can go anywhere, behind the qualified people.

Nothing it does is announced. Every assignment it makes is a draft until you
publish.
:::

After a run, a summary sits above the grid until you dismiss it or leave the
page:

- **Open slots** it couldn't fill, each with the main reason (nobody qualified
  said they're free, everyone eligible is at the hour limit, everyone marked it
  unavailable, or everyone is already on another shift) and an **Assign** button
  to fill it by hand. The same reason shows when you hover a short shift's badge.
- **Placed outside stated availability**, when you allowed that, with a
  **Remove** button beside each.
- **Heavy loads**: anyone within a quarter of the hour limit, or working three or
  more blocks back to back.

## Publishing the draft

:::snippet vol-drafts
While a day has drafts, a banner says how many and that the volunteers haven't
been told. Review the grid, move people around by hand if you need to, then:

- **Publish draft** sends every volunteer on a draft assignment a DM asking them
  to acknowledge. You can't take that back quietly: removing someone afterwards
  sends them another DM.
- **Clear draft** throws away every draft on this day. Nobody is told, because
  nobody was told about them in the first place.

A draft that clashes with a shift someone was given by hand in the meantime
stays a draft, and the app lists those after publishing so you can sort them
out.
:::

Publishing works one day at a time, so check the day picker before you press it.

## Reminders

Every published assignment gets one reminder DM before the shift starts. Staff
set how far ahead under **Admin → Settings → Volunteers**; blank means an hour.
If the volunteer hasn't acknowledged yet, the reminder carries the
**Acknowledge** button again. It also carries a **Can't make it** button that
opens their give-back dialog, because the reminder is usually when someone
finds out.

Drafts are never reminded. Moving a shift's time re-arms the reminder for the
new time. Anyone who turned off DMs on their profile gets nothing, so the
"awaiting acknowledgment" chip is worth a look on the morning of each day.

## When someone gives a shift back

A volunteer can give back any shift that hasn't finished and that they haven't
been checked in for. The slot opens immediately, and every coordinator and staff
member gets a DM with who it was, how much notice they gave, their reason if
they left one, and a **Find cover** button. That button opens Vol. Schedule on
the day of the shift.

## Starting over

**Reset all volunteer data** deletes every shift and every assignment on every
day. Positions, availability and qualifications stay. Anyone with a shift still
to come gets a DM that they're off it. You have to type a confirmation phrase,
and there's no undo, so export first if you might want the old schedule back.
