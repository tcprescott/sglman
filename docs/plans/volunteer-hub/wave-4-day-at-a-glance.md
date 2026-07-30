# Wave 4 — the coordinator's day at a glance

**Read [README.md](README.md) first.** **Waves 1–3 must be merged** — the coverage
strip counts the draft and acknowledgment states those waves made meaningful, and
the phone layout has to accommodate the banner and result panel they added.

The two small findings that bite hardest on the day itself.
[F6](../../reviews/volunteer-hub-ux.md#f6--minor--the-event-day-selection-resets-to-day-one) /
[RC4](../../reviews/volunteer-hub-ux.md#rc4--the-grid-forgets-which-day-you-were-on) —
`state = {'day': day_options[0]}` is rebuilt on every render, so choosing day 3 and
reloading returns you to day 1, and auto-fill acts on *the selected day's* window.
[F8](../../reviews/volunteer-hub-ux.md#f8--minor--the-coordinators-grid-is-4891-px-on-a-phone) —
4,891 px on a 390×844 phone, and the one number a coordinator wants on-site ("how
many slots are still open right now?") is not on the page in any form.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T4.1 | F6, RC4 | — | small |
| T4.2 | F8 (the missing number) | — | medium |
| T4.3 | F8 (the 5.8 screenfuls) | T4.2 | medium |

One PR for the wave; it is the smallest of the four.

---

## T4.1 — Remember the day

**Why.** RC4, measured three times: load → choose the last day → reload → day one;
navigate away → return → day one. The match board solved this already with
tenant-namespaced session keys (`_skey`,
[`theme/tables/match.py:105-124`](../../../theme/tables/match.py#L105)) — four
boards share one session, and before that a filter change on one retargeted the
others.

### Files

- `pages/admin_tabs/admin_volunteers.py`

### Change

Replace the unconditional default
([`:54`](../../../pages/admin_tabs/admin_volunteers.py)) with a stored choice,
validated against the current event window:

```python
    from application.utils.tenant_session import tenant_session_get, tenant_session_set

    _DAY_KEY = 'volunteers:day'

    default_day = day_options[0] if day_options else event_start.isoformat()
    stored = tenant_session_get(_DAY_KEY)
    # A stored day from a previous event is not a day of this one.
    state = {'day': stored if stored in day_options else default_day}
```

and persist on change ([`:77-79`](../../../pages/admin_tabs/admin_volunteers.py)):

```python
                def on_day_change(e):
                    state['day'] = e.value
                    tenant_session_set(_DAY_KEY, e.value)
                    grid.refresh()
                    draft_banner.refresh()
```

The key is namespaced `volunteers:` for the same reason the match board namespaces
its filters, and `tenant_session_*` scopes it per tenant, so a coordinator working
two communities does not carry day 3 of one into the other.

No URL parameter. The tab is reached through `BaseLayout`'s section routing, which
owns the path segment; adding a query string here would be a second source of truth
for the same selection.

### Tests

`tests/theme/` cannot exercise `app.storage.user` without a client. Test the
precedence rule instead by extracting it:

```python
def stored_or_default_day(stored: str | None, day_options: list[str], fallback: str) -> str:
```

module-level in `admin_volunteers.py`, mirroring
`MatchTableView._stored_or_default_states`'s reason for existing, with tests for
stored-in-window wins, stored-out-of-window falls back, `None` falls back, and an
empty `day_options` returns the fallback.

### Verify

As `staff_user`: choose the last event day, reload, and confirm it holds; switch to
`/t/second/admin/volunteers` and confirm that tenant opens on its own day one.

---

## T4.2 — One number: how much of today is uncovered

**Why.** F8's second half. The grid shows per-shift `n/m` badges and nothing
aggregate, so the coordinator's headline question is answered by scrolling 5.8
screenfuls and adding up. `coverage()`
([`volunteer_schedule_service.py:325-341`](../../../application/services/volunteer/volunteer_schedule_service.py#L325))
already computes the per-shift rows this needs and has no caller in the page.

### Files

- `application/services/volunteer/volunteer_schedule_service.py`
- `pages/admin_tabs/admin_volunteers.py`

### Change 1 — `coverage()` reports the states the waves added

Each row gains `acknowledged` and `drafts` counts alongside `filled` / `needed` /
`understaffed`, and the method gains a companion returning the day's totals:

```python
    async def day_summary(self, start: datetime, end: datetime) -> Dict:
        """Aggregate coverage for a day: the numbers the coordinator's strip shows."""
        rows = await self.coverage(start, end)
        return {
            'shifts': len(rows),
            'needed': sum(r['needed'] for r in rows),
            'filled': sum(r['filled'] for r in rows),
            'open': sum(max(0, r['needed'] - r['filled']) for r in rows),
            'drafts': sum(r['drafts'] for r in rows),
            'unacknowledged': sum(r['filled'] - r['drafts'] - r['acknowledged'] for r in rows),
            'understaffed_shifts': sum(1 for r in rows if r['understaffed']),
        }
```

One query's worth of work, and it is the page's only new read. The MCP
`volunteer_coverage` tool and the admin reports both call `coverage()` — adding
fields to its rows is additive, but check
`mcpserver/schemas.py`'s coverage model and the reports page for a strict shape
before you ship.

### Change 2 — the strip

A `@ui.refreshable` row directly under the page's caption, above the controls card,
rendering four chips from `day_summary`:

```
[ 14/20 slots filled ]  [ 6 open ]  [ 3 awaiting acknowledgment ]  [ 4 draft ]
```

- `6 open` is `warning` when non-zero, `positive` when zero (`Fully staffed`).
- `awaiting acknowledgment` counts published-but-unacknowledged only — that is why
  `day_summary` subtracts drafts.
- The draft chip is `secondary` outline, matching the draft chips in the grid, and
  is hidden at zero.
- Each chip is `clickable` and scrolls to the first shift card matching it
  (`ui.run_javascript` on an anchor id) — cheap, and it is the difference between
  a number and a way in.

Refresh it wherever `grid.refresh()` and `draft_banner.refresh()` are called; by
this wave that is a fixed set of handlers, so extract one
`async def refresh_all()` the whole page calls instead of three refreshes at nine
sites.

### Tests

`tests/services/test_volunteer_scheduling.py` (DB-backed): a day with one
2-slot shift holding one published-acknowledged and one draft assignment reports
`filled=2, open=0, drafts=1, unacknowledged=0`; an empty day reports zeroes without
raising.

### Verify

Both widths. On a phone the four chips must wrap, not scroll horizontally — the
audit's one unambiguous win on this page is that it has no horizontal overflow, and
this is the change most likely to break it.

---

## T4.3 — Make the phone version a day, not a scroll

**Depends on T4.2.**

**Why.** F8: four positions × five shift cards = 4,891 px, with no day-at-a-glance
summary and no way to skip the positions that are done. T4.2 supplies the summary;
this task supplies the skipping.

### Files

- `pages/admin_tabs/admin_volunteers.py`

### Change

Per position, on small screens only, collapse the shift cards behind the position
header when that position is **fully staffed for the day**, and leave it expanded
otherwise:

```python
                    open_slots = sum(
                        max(0, s.slots_needed - len(s.assignments)) for s in pos_shifts)
                    header = f'{position.name}'
                    with ui.expansion(header, value=bool(open_slots)) \
                            .classes('full-width lt-md wiz-position-expansion'):
                        ...
```

with the desktop path unchanged (`gt-sm`), so the two layouts share the card
renderer and only differ in their wrapper. The header carries the position's own
`filled/needed` badge and its open count, so a collapsed position still states its
state — collapsing must never hide work, only work that is done.

Two things to keep:

- **The action buttons stay in the header row**, outside the expansion. *Generate
  standard shifts* and *Add shift* are how an empty day gets populated, and a
  position with no shifts renders no expansion at all.
- **The draft banner and result panel stay above everything**, un-collapsed. They
  are the wave 1 and 2 outputs a coordinator is acting on.

Re-measure and record the new phone height in the commit message against the
audit's 4,891 px — that number is the finding, so the fix has to quote its
replacement.

### Tests

None (layout). The `lt-md` / `gt-sm` pair is a Quasar class switch that only a
browser can prove, which is what `Verify` is for.

### Verify

390×844 screenshots of: a day where every position is fully staffed (all collapsed,
strip reads `Fully staffed`), a day with two positions short (those two expanded),
and a day with no shifts at all (per-position *"No shifts for this day yet."* plus
both buttons reachable). Then 1500px, to confirm the desktop grid is byte-for-byte
the layout it was before this wave.
