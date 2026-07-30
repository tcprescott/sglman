# Wave 2 — an auto-fill you can trust

**Read [README.md](README.md) first.** **Wave 1 must be merged** — T2.3's result
panel sits beside the Publish button the draft banner introduced, and this wave's
whole premise is that a bad draft is now reviewable rather than already sent.

Two findings, one theme: the bulk path is less careful and less honest than the
manual path standing right next to it.
[F2](../../reviews/volunteer-hub-ux.md#f2--critical--auto-fill-assigns-outside-stated-availability-and-without-an-hours-cap-and-says-neither) —
`_pick` treats "has not said they can work this" as a *tiebreaker* and hours-so-far
as another tiebreaker, so one volunteer was measured getting four consecutive
blocks, 16 hours, 12 of them outside their declared window — and the summary
reported quantity only.
[F7](../../reviews/volunteer-hub-ux.md#f7--minor--the-auto-fill-result-is-a-toast-and-the-only-record-of-what-it-did) —
`_unfilled_summary` already computes per-shift open counts and the page throws
them into a five-second toast.

The manual path already writes the missing sentence: `_availability_warning`
produces *"Player One has not marked this time as available."*
([`volunteer_schedule_service.py:345-358`](../../../application/services/volunteer/volunteer_schedule_service.py#L345)).
This wave makes the bulk path obey it and then show it.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T2.1 | F2 (the constraint half) | — | medium |
| T2.2 | F2 (the honesty half), F7 | T2.1 | medium |
| T2.3 | F7 | T2.2 | **large** — new dialog + result panel |
| T2.4 | — (seed) | T2.1 | tiny |

T2.1 and T2.2 are one PR (the policy and the report it produces); T2.3 and T2.4
are a second.

---

## T2.1 — Availability is a constraint; hours are a ceiling

**Why.** F2, measured. In
[`_pick`](../../../application/services/volunteer/volunteer_autoschedule_service.py#L141)
the only hard skips are "already on this shift", "qualified for something but not
this", "explicitly UNAVAILABLE" and "overlaps". Everything else is the sort key
`(qual_priority, avail_rank, hours, name)` — so an undeclared window costs a
candidate one rank, and 12 hours already worked costs them a tiebreak.

**Shape.** A frozen policy object, defaulting to the safe behaviour, passed down
into `_pick`. `_pick` already takes eight positional arguments; adding two more
loose parameters is how that function becomes unreadable, and the policy is
exactly the thing the T2.3 dialog builds.

### Files

- `application/services/volunteer/volunteer_autoschedule_service.py`
- `application/services/volunteer/__init__.py` (export `DraftPolicy`)

### Change 1 — the policy

Module level, beside `_AVAIL_RANK`:

```python
# Per-run limits on what the greedy filler may do. The defaults are the
# conservative reading of a volunteer's declared availability: an undeclared
# window is not consent, and eight hours is a long day on your feet.
DEFAULT_MAX_HOURS = 8.0


@dataclass(frozen=True)
class DraftPolicy:
    """What the coordinator is willing to let the autoscheduler do."""

    max_hours: float = DEFAULT_MAX_HOURS
    fill_outside_availability: bool = False
```

`generate_draft` gains `policy: Optional[DraftPolicy] = None` (keyword-only) and
resolves `policy = policy or DraftPolicy()`. Its existing `position_ids` and
`clear_existing_drafts` keywords are unchanged.

### Change 2 — the two new hard skips

In `_pick`, replacing the availability branch:

```python
            status = VolunteerAvailabilityService.covers(windows, shift.starts_at, shift.ends_at)
            if status == VolunteerAvailabilityStatus.UNAVAILABLE:
                reasons['unavailable'] += 1
                continue
            if status is None and not policy.fill_outside_availability:
                reasons['not_stated'] += 1
                continue
            if self._overlaps(intervals[uid], shift.starts_at, shift.ends_at):
                reasons['overlapping'] += 1
                continue
            if policy.max_hours and hours[uid] + shift_hours > policy.max_hours:
                reasons['at_hour_cap'] += 1
                continue
```

`shift_hours` is already computed by the caller
([`:98`](../../../application/services/volunteer/volunteer_autoschedule_service.py#L98))
— pass it in rather than recomputing. `reasons` is a `Counter` the caller owns per
shift; it is what T2.2 turns into prose, so add it now even though nothing reads
it yet.

Keep the sort key as it is. With `fill_outside_availability=True` the
`_AVAIL_RANK` entry for `None` still puts undeclared candidates last, which is the
right preference order once they are admitted at all.

### Change 3 — record the policy in the audit row

The `VOLUNTEER_DRAFT_GENERATED` details
([`:116-119`](../../../application/services/volunteer/volunteer_autoschedule_service.py#L116))
currently carry `created`, `start`, `end`. Add `open`, `pool_size`, `max_hours`
and `fill_outside_availability`, so the audit log answers "what did that run
actually do" — F7's closing sentence.

### Tests

`tests/services/test_volunteer_autoschedule_service.py`:

- a candidate with **no** window covering the shift is skipped by default and
  chosen when `fill_outside_availability=True`
- a candidate at `max_hours` is skipped even when they are the only qualified,
  preferred, non-overlapping person — and the slot is reported open
- `max_hours=0` (or `None`) disables the cap
- the four consecutive 4-hour blocks from the audit's measurement produce **two**
  assignments for a volunteer with an 8-hour default, not four
- the audit details include the policy

Write the last one as a regression test named after the finding —
`test_does_not_repeat_the_sixteen_hour_draft`.

### Verify

As `staff_user`, auto-fill day 1 with the defaults and confirm from the grid that
nobody holds more than two 4-hour blocks and that no chip belongs to someone whose
roster row shows no availability for that time (cross-check on
`/t/default/admin/vol-roster`).

---

## T2.2 — The result becomes a record

**Depends on T2.1.**

**Why.** F7: `Draft created: 16 assignment(s), 4 slot(s) still open (pool of 5)`
is accurate, disappears in seconds, and is the only place the run's output exists.
The coordinator then re-reads the grid's `n/m` badges to find the four open slots.
And F2's second half: the run must say who it placed outside their stated
availability, because with `fill_outside_availability=True` that is the whole risk
of the run.

### Files

- `application/services/volunteer/volunteer_autoschedule_service.py`

### Change — a richer return value

`generate_draft` returns:

```python
        return {
            'created': created,
            'pool_size': len(pool),
            'policy': policy,
            'unfilled': self._unfilled_summary(shifts, filled_counts, reasons_by_shift),
            'outside_availability': outside,   # [{'user_id', 'name', 'shift_id', 'position', 'starts_at'}]
            'heavy_loads': heavy,              # [{'user_id', 'name', 'hours', 'shifts'}]
        }
```

- `_unfilled_summary` gains the per-shift `Counter` and turns it into a `reason`
  sentence per open slot — the honest version of "still open":

  | dominant reason | sentence |
  |---|---|
  | `not_stated` | `Nobody qualified has marked this time as available.` |
  | `at_hour_cap` | `Everyone eligible is at the {max_hours}-hour limit.` |
  | `unavailable` | `Everyone qualified marked this time unavailable.` |
  | `overlapping` | `Everyone qualified is already on another shift.` |
  | none of the above | `No qualified volunteer in the pool.` |

  Pick the largest count; on a tie prefer the order above. Keep `shift_id`,
  `position`, `open` and add `label` and `starts_at` so the panel can render a row
  without re-reading the shift.

- `outside` is appended inside the fill loop whenever the chosen candidate's
  `covers(...)` status is `None` — only reachable when the policy allows it.
- `heavy` lists any volunteer the run left above `policy.max_hours * 0.75` or
  holding three or more consecutive blocks, with their total. Consecutive means
  the intervals this run knows about (`intervals[uid]`, already maintained)
  touching end-to-start within 15 minutes.

`_pick` returning a reason and the caller aggregating it is deliberately the only
new state: everything above is derived from `intervals`/`hours`, which the method
already maintains.

### Tests

`tests/services/test_volunteer_autoschedule_service.py`:

- each of the five reason sentences, one test per branch, driven by constructing a
  pool that can only fail that way
- `outside_availability` is empty by default and populated under the opt-in
- `heavy_loads` names the volunteer who ends the run on three touching blocks

### Verify

Nothing user-visible yet (T2.3 renders it). Assert the shape from a REPL run
against dev data, and paste the dict into the commit message.

---

## T2.3 — Ask before filling, then show what happened

**Depends on T2.2.**

**Why.** The two halves that need a surface: the policy has to be the
coordinator's choice at the moment of the run, and the report has to survive
long enough to be worked through.

### Files

- `theme/dialog/volunteer_autofill_dialog.py` (new)
- `pages/admin_tabs/admin_volunteers.py`

### Change 1 — the auto-fill dialog

**Auto-fill from availability** ([`:82-83`](../../../pages/admin_tabs/admin_volunteers.py))
stops running immediately and opens `VolunteerAutofillDialog`, built like the
other dialogs in `theme/dialog/` (`dialog_header`, `mobile_sheet`,
`dialog_actions`, `submit_on_enter` from `theme/dialog/_helpers.py`):

| Control | Default | Copy |
|---|---|---|
| `ui.number` **Maximum hours per volunteer** | `8` | hint: `Across this day. Leave blank for no limit.` |
| `ui.checkbox` **Also use volunteers who have not marked this time** | off | caption: `They will be listed for you to review. Anyone who marked the time unavailable is never used.` |
| `ui.select` **Positions** (multiple) | all active | — |
| primary button | — | `Create draft` |

The dialog collects a `DraftPolicy` and the position ids and hands them to the
page's `auto_fill`; it does not call the service itself, so the page keeps owning
refreshes. Keep it under ~120 lines — it is four controls.

### Change 2 — the result panel

A `@ui.refreshable` panel below the draft banner, holding the last run's result in
the page function's `state` (never a module global):

```
Draft: 16 assigned · 4 slots open · pool of 5 · max 8 h/volunteer          [×]

Open slots
  Check-in Desk — Shift 3   16:00–20:00 ET   1 open   Everyone eligible is at the 8-hour limit.   [Assign]
  Race Proctor  — Shift 4   20:00–00:00 ET   1 open   Nobody qualified has marked this time as available.   [Assign]

Placed outside stated availability
  Player Three — Check-in Desk, Shift 2 (12:00 ET)   [Remove]

Heavy loads
  Player One — 8 h across 2 shifts
```

- **Assign** opens the existing picker (`open_assign_dialog`) for that shift — the
  cross-cutting "discovery and action on different pages" theme, fixed in the one
  place this plan can fix it.
- **Remove** unassigns that one assignment and refreshes.
- The panel is dismissible and is replaced by the next run. It does not survive a
  page reload; the audit row is the durable record (T2.1 change 3).
- The toast shrinks to `Draft created — see the summary below.`

Both lists are empty in the default-policy happy path, so the panel is normally
the header line plus open slots.

### Change 3 — the shift card carries its own open count

`_render_shift_card` ([`:130`](../../../pages/admin_tabs/admin_volunteers.py))
already badges `filled/slots_needed`. When a run reported a reason for this
shift's open slots, add its sentence as the badge's tooltip, so the grid and the
panel agree without the coordinator holding the mapping in their head.

### Tests

Presentation. Add `tests/theme/test_autofill_dialog.py` asserting only the
defaults that matter — `DraftPolicy()` built from an untouched dialog has
`max_hours == DEFAULT_MAX_HOURS` and `fill_outside_availability is False` — by
calling the dialog's policy builder directly (extract it as a module-level
function taking the three values, so it is testable without a slot context).

### Verify

Screenshot `/t/default/admin/volunteers` at 1500px and 390px with a populated
panel (auto-fill day 1 with the checkbox on, so all three sections render). Click
an **Assign** in the panel and confirm the picker opens for the right shift. The
panel is the widest new thing in this plan — check it does not overflow at 390px.

---

## T2.4 — Seed a volunteer with nothing declared

**Depends on T2.1.**

**Why.** Every opted-in volunteer in the dev data has availability windows
([`seed_volunteers.py:96-104`](../../../scripts/seed_volunteers.py)), so the
default policy's most important skip — "has not said they can work this" — has
nothing to skip, and neither the checkbox nor the `not_stated` reason sentence can
be seen in a dev environment.

### Files

- `scripts/seed_dev.py`
- `scripts/seed_volunteers.py`

### Change

Grant `player_four` `Role.VOLUNTEER` in `seed_dev.py`'s `role_grants`
([`:195-204`](../../../scripts/seed_dev.py)) and add them to `opted_in` in
`seed_volunteers.py` with a note, but **not** to `avail_specs` — with a comment
saying the omission is the fixture:

```python
        # Deliberately absent from avail_specs below: the auto-scheduler's default
        # policy skips a volunteer who has not declared this time, and that skip
        # needs someone to skip.
        "player_four": "Can help wherever, ask me on the day.",
```

### Verify

`poetry run python scripts/seed_dev.py`, then auto-fill with the defaults and
confirm `player_four` gets nothing; re-run with the checkbox on and confirm they
appear in **Placed outside stated availability**.
