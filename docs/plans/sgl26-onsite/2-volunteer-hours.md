# Plan 2 — total a volunteer's hours against the comp tiers

**Read [README.md](README.md) first.**

SGL comps a badge at 8 hours volunteered, with more at 12 and 16. Nothing in
the app adds those hours up, so the coordinator does it by reading a Google
Sheet on a phone. Everything needed is already in the database.

| Task | Size |
|---|---|
| T2.1 | Tier configuration | small |
| T2.2 | The interval fold | small |
| T2.3 | `VolunteerHoursService` | medium |
| T2.4 | Roster column and the volunteer's own total | medium |
| T2.5 | REST | small |
| T2.6 | Seed + docs | small |

**No new model and no migration.** No new feature flag: this sits inside
`FeatureFlag.VOLUNTEERS`, whose spec already declares the whole
`application/services/volunteer/` package as its `service_modules`, so a new
module in that package is gated by construction. No new `AuditActions` and no
new `EventType` — this reads, it does not write, and the service docstring says
so explicitly.

---

## T2.1 — Where the tiers live

`application/services/system_config_service.py`, beside
`KEY_VOLUNTEER_REMINDER_LEAD_MINUTES`, which is the precedent this follows:

```python
KEY_VOLUNTEER_COMP_TIERS = 'volunteer_comp_tiers'
```

with a typed getter returning a sorted list of hour thresholds, defaulting to
`[8, 12, 16]` when unset, and rejecting a malformed blob by falling back to the
default rather than raising — a bad config value must not take the roster page
down.

The editor is a row on `pages/admin_tabs/admin_system_config.py`, next to the
volunteer reminder lead it already renders (line 190, saved at line 313). Same
shape: read on render, `SystemConfigService.set_raw(KEY, value, actor)` on save.

This is per-tenant, which is the point: SGL's 8/12/16 is a policy, not a
constant, and another community will have its own or none at all.

---

## T2.2 — The interval fold

There is no interval-merge helper in the codebase.
`volunteer_autoschedule_service._overlaps` answers a boolean and merges nothing.
Write the fold as a module-level pure function so it is testable without a
database:

```python
def merged_hours(windows: list[tuple[datetime, datetime]]) -> float:
    """Total hours covered by ``windows``, counting overlap once.

    A coordinator can hand-assign overlapping shifts, so 08:00-12:00 plus
    10:00-14:00 is six hours served, not eight. Touching windows
    (``a.end == b.start``) merge into one continuous block, which matters
    because the shift generator produces back-to-back blocks by default.
    """
```

Sort by start, fold forward, extend the open interval while the next start is
`<=` the current end. Zero-length and inverted windows are dropped rather than
subtracting; the shift model should never produce one, and the fold is not the
place to discover that it did.

`# ponytail:` comment naming the ceiling, since this is a deliberate shortcut:

```python
# ponytail: per-user fold in Python over one event's assignments. Move to a
# SQL range aggregate if a tenant ever runs thousands of them.
```

---

## T2.3 — `VolunteerHoursService`

New `application/services/volunteer/volunteer_hours.py`. Exported from
`application/services/volunteer/__init__.py` and from the parent
`application/services/__init__.py`.

Two public methods, both `@requires_feature(FeatureFlag.VOLUNTEERS)`:

- `for_user(user, *, start=None, end=None) -> HoursSummary` — the volunteer's
  own total plus the highest tier cleared and the gap to the next one.
- `roster(*, start=None, end=None) -> list[HoursSummary]` — every opted-in
  volunteer, for the coordinator.

**What counts.** Assignments where `auto_generated is False`. That single
predicate captures both halves of the rule:

- A draft is `auto_generated=True` and gets flipped to `False` by
  `VolunteerScheduleService.publish_assignment`, so unpublished work is
  excluded.
- `release` **deletes** the row rather than flagging it, so a withdrawn shift
  needs no predicate at all.

Acknowledgement is deliberately not required. Someone who turned up and never
tapped the button in the DM still served the hours, and the comp is for the
hours.

The window defaults to the tenant's event window from
`SystemConfigService.get_event_window()` rather than all time, so last year's
shifts do not comp this year's badge. Say that in the docstring; it is the kind
of default that looks arbitrary a year later.

`VolunteerAssignmentRepository` gains `published_for_window(start, end)`
alongside the existing `list_for_window` (line 100), prefetching `shift` and
`user`. Tenant-scoped like its neighbours, not cross-tenant: this one runs from
a page, not a worker.

---

## T2.4 — The two surfaces

**Coordinator.** `pages/admin_tabs/admin_volunteer_roster.py` gains an `hours`
column in `_COLUMNS` (line 24) and a tier chip beside it. That table already
calls `customize_table(table, _COLUMNS, key=TableKeys.ADMIN_VOLUNTEER_ROSTER)`
at line 153, so a new entry in `_COLUMNS` inherits the preference machinery;
check the mobile card renders the new field too.

Sort the column numerically, not on its rendered string. `tournament_health`
had exactly this bug and it was fixed on 2026-07-31; do not reintroduce it.

**The volunteer.** `pages/volunteer_tabs/my_shifts.py` gains a line above the
shift list: hours so far, the tier cleared, and how many hours to the next one.
This is the number the badge depends on and the person it belongs to currently
cannot see it.

Copy follows the writing rules. "You've volunteered 9 hours. Two more and your
badge is comped" beats a labelled statistic.

---

## T2.5 — REST

`api/routers/volunteers.py` gains `GET /api/volunteers/hours` (the roster,
coordinator-gated) and `GET /api/volunteers/hours/me`. The router is already
mounted behind `Depends(require_feature(FeatureFlag.VOLUNTEERS))` in
`api/__init__.py:78`, so the entry-surface gate is inherited; the service
decorator is still required, because the flag's two obligations are independent.

Schemas in `api/schemas/volunteers.py`. The service raises `NotFoundError`, so
no `_load_*_or_404` preload in the router — the DRY hook blocks new ones.

---

## T2.6 — Seed and docs

`scripts/seed_dev.py`: enough published assignments on seeded volunteers that
one clears 16 hours, one clears 8 but not 12, and one sits below 8, so all three
tier states render on a fresh seed. Add **one pair of deliberately overlapping
shifts** on a fourth volunteer, so the union path is visible in the running app
and not only in a unit test. Seed the tiers for the `default` tenant at
`[8, 12, 16]`.

Docs: `docs/reference/services.md` (the service and the fold),
`docs/reference/frontend.md` (both changed surfaces),
`docs/reference/rest-api.md`, `docs/current-state.md`.

There is no `docs/features/volunteers.md`. Writing one is out of scope here, but
note the gap when updating `docs/README.md` so it does not vanish.

---

## Tests

`tests/services/test_volunteer_hours.py`:

- a draft (`auto_generated=True`) contributes nothing
- publishing it makes it count
- an unacknowledged published assignment counts in full
- overlapping shifts 08:00–12:00 and 10:00–14:00 total 6 hours, not 8
- a shift wholly nested inside another adds nothing
- touching shifts 08:00–12:00 and 12:00–16:00 total 8 hours as one block, with
  no double count at the boundary and no lost minute
- a union landing exactly on 8.0 clears the 8-hour tier
- assignments outside the event window are excluded
- flag off raises `FeatureDisabledError`

Test `merged_hours` directly as a pure function for the interval cases; it needs
no database and the failures are easier to read.

No tenancy test and no new isolation file: no new model. The existing volunteer
isolation coverage still applies, and `test_leak_test_coverage.py` will not ask
for more.

Use `tests/factories.py` and the hoisted conftest fixtures.
