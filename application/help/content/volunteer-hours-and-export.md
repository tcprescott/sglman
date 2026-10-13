---
title: Volunteer roster, hours and export
slug: volunteer-hours-and-export
icon: groups
order: 220
feature: VOLUNTEERS
audience: staff
roles: STAFF, VOLUNTEER_COORDINATOR
summary: Who is in the volunteer pool, qualifications, hours against reward tiers, the settings behind them, and the CSV export.
---

**Admin → Vol. Roster** is the list of people you can schedule. Staff and
Volunteer Coordinators can open it. Building shifts and assigning people is in
[Building the volunteer schedule](/help/coordinating-volunteers).

## The roster

:::snippet vol-roster
The roster is everyone in this community holding the **Volunteer** or **Staff**
role. That role is what puts someone in the pool, so if a volunteer is missing,
check their roles on the Users tab or the Discord role that grants it.

| Column | Shows |
|---|---|
| Hours | Their scheduled hours for the event, with the highest reward tier they've reached. |
| Qualifications | The positions they're qualified for. A dash means none recorded. |
| Availability | Every window they entered, marked Preferred, Available or Unavailable. |

The manage button at the end of a row opens their availability in full and a
checkbox per active position. Tick the positions they're qualified for and
save.
:::

![Vol. Roster: each volunteer's hours with the reward tier reached, qualifications and availability windows](/static/help/volunteer-hours-and-export/roster-desktop.webp)

Qualifications change who the auto-scheduler will place. Someone with at least
one qualification is only placed in those positions, and goes ahead of
unqualified people there. Someone with none can be placed anywhere, behind the
qualified people. The Assign picker also hides unqualified people by default for
any position that has qualified ones.

A volunteer adds and edits their own availability on the Volunteer tab. You
can read it here but not change it.

## Hours and reward tiers

:::snippet vol-hours
**Hours** is the time a volunteer is scheduled for during the event, counted from
published assignments. Drafts don't count. Overlapping shifts count once, so two
shifts covering 08:00–12:00 and 10:00–14:00 make six hours, not eight. Only time
between the event's start and end dates counts, so last year's shifts don't earn
this year's reward.

These are scheduled hours, not hours someone checked in for. A volunteer who
gives a shift back loses those hours straight away.

The chip beside the number is the highest reward tier they've reached. Each
volunteer sees the same total on their own My Shifts, with how far they are from
the next tier.
:::

Staff set the tiers under **Admin → Settings → Volunteers** as hour totals
separated by commas. Blank uses 8, 12 and 16. Enter 0 if your community doesn't
reward hours.

If the event uses check-in with volunteer comps turned on, the lowest tier is
also the line for a comped badge: anyone whose scheduled hours reach it is on
the check-in roster as a volunteer comp.

## Settings that only staff can change

Two things a coordinator will want changed live where only staff can reach them:

| Setting | Where |
|---|---|
| How long before a shift the reminder DM goes out, and the reward tiers | Admin → Settings → Volunteers |
| Which app role each position grants | Admin → Settings → Discord, Volunteer positions section |

## Exporting the data

**Export data** is on Vol. Roster, and in the **Actions** menu on Vol. Schedule. Pick a date range (it
starts as the event dates) and you get a ZIP with a README and six CSV files:

| File | One row per |
|---|---|
| volunteers.csv | Everyone in the pool or on a shift, with their qualifications, available hours and assigned hours. Always the full roster, whatever the dates. |
| availability.csv | Availability window someone entered, including the times they ruled out. |
| positions.csv | Position, with its shift and slot counts. |
| shifts.csv | Shift in the date range. |
| assignments.csv | Person on a shift, whether it's a draft, whether it fits what they said they were free for, and when they acknowledged and checked in. |
| schedule.csv | Slot, open ones included. This is the sheet to draft a schedule on. |

Times are in your own timezone, and every file also has the UTC timestamps for
sorting. The README says which zone was used.

The export is a copy. Editing the files changes nothing in the app; a schedule
you build in a spreadsheet has to be entered back on Vol. Schedule by hand. The
export includes everyone's availability and notes, so treat it as private, and
know that each export is recorded in the audit log.

## Coverage report

For a view across several days, **Admin → Reports → Volunteer Coverage** lists
every understaffed shift in a date range and how many people each still needs.
