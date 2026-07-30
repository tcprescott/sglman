# Wave 4 — the three that are small and wrong

**Read [README.md](README.md) first.**

Three independent minor findings, no dependencies between them beyond the shared
helper T4.2 touches. Each is cheap; each is the kind of thing that makes an
otherwise-good reporting surface feel untrustworthy.

| Task | Fixes | Report |
|---|---|---|
| T4.1 | [F3](../../reviews/admin-reports-ux.md#f3--minor--insights-default-window-is-much-wider-than-the-data-so-every-chart-is-one-spike-at-the-right-edge) | insights |
| T4.2 | [F4](../../reviews/admin-reports-ux.md#f4--minor--the-audit-report-shows-50-of-124-entries-with-the-count-in-the-header) | audit + telemetry |
| T4.3 | [F5](../../reviews/admin-reports-ux.md#f5--minor--the-dashboard-is-the-only-report-with-no-export-and-no-filters) | dashboard |
| T4.4 | docs | — |

---

## T4.1 — Insights should open on a window that has data in it

**Why.** Measured on the default view: a ~90-day window bucketed weekly, **13
empty buckets and everything in the last one** — eight charts that are each one
spike at the right edge. The default is a fixed trailing range
([`insights.py:36`](../../../pages/admin_tabs/reports/insights.py#L36)):

```python
DEFAULT_TREND_DAYS = 90
...
    today = now_eastern().date()
    return today - timedelta(days=DEFAULT_TREND_DAYS), today
```

The instinct is already right elsewhere: the crew report defaults to the
**event window** via `default_date_range` → `SystemConfigService.get_event_window()`
([`shared.py:108`](../../../pages/admin_tabs/reports/shared.py#L108)), which is
why its default view has data in it. Insights cannot use the event window — it
trends *across* events — so it needs the data's own extent.

The comment at [`insights.py:34`](../../../pages/admin_tabs/reports/insights.py#L34)
correctly explains why the event window is wrong here. Keep that reasoning;
replace only the fixed number.

### Files

- `application/services/analytics_service.py`
- `pages/admin_tabs/reports/insights.py`
- `tests/services/test_analytics_service.py`
- `docs/features/admin-reports.md`

### Change 1 — the extent, in the service

Aggregation belongs in a service — the feature doc states it and this is the
easy one to get wrong while "just" computing a date. Add:

```python
    async def activity_extent(self, tournament_id: Optional[int] = None) -> tuple[Optional[date], Optional[date]]:
```

returning the earliest and latest **Eastern dates** with any of the activity
this page trends, across the same sources its four sections read
(`crew_participation_trends`, `volunteer_hour_trends`, `tournament_health`,
`activity_trends` — [`analytics_service.py:181`](../../../application/services/analytics_service.py#L181)
onward). Min/max aggregates, tenant-scoped like every other read here, one query
per source and `asyncio.gather` them. Returns `(None, None)` for a community
with no history at all.

Note the existing constraint the page already documents
([`insights.py:110`](../../../pages/admin_tabs/reports/insights.py#L110)):
volunteer shifts and audit logs are **not** tournament-scoped, so when
`tournament_id` is given the extent must come from the sources that *are*
scoped, or the "narrowed" window will silently widen back out.

### Change 2 — the default

`_default_range` uses the extent when the caller supplied no dates:

- extent present → clamp to it, with a floor so a single-day extent still spans
  enough buckets to read as a trend (a week either side), and a ceiling so a
  community with three years of history does not open on 156 weekly buckets —
  cap at roughly a year and take the **most recent** slice.
- extent empty → today − `DEFAULT_TREND_DAYS` → today, exactly as now. Keep the
  constant; it is the honest fallback, not the default.
- Pick the bucket to match: weekly under ~180 days, monthly beyond. `bucket`
  is an explicit param, so only default it — never override what the operator
  chose ([`insights.py:46`](../../../pages/admin_tabs/reports/insights.py#L46)).

The three range shortcuts (`Last 30d / Last 90d / Last year`,
[`:93`](../../../pages/admin_tabs/reports/insights.py#L93)) stay untouched: they
are how the operator overrides this, and the audit called them out as working.

### Verify

- `poetry run pytest tests/services/test_analytics_service.py` — new cases: a
  seeded tenant (extent covers the seeded activity), an empty tenant
  (`(None, None)` → trailing-90 fallback), and a tenant whose only activity is
  a single day.
- In the browser: `?report=insights` with no params now opens on a window whose
  charts have more than one populated bucket. Count the empty buckets and put
  the before/after in the commit message — 13 is the number to beat.
- The empty-window behaviour the audit praised must survive: force
  `2020-01-01 → 2020-01-02` and confirm the KPIs still read `0` / `—` with their
  captions and each chart still says *"No crew activity in the selected
  window."*

---

## T4.2 — A count and a page size that do not disagree

**Why.** The audit log header reads `124 entries` above a table paginated to 50
([`audit.py:137`](../../../pages/admin_tabs/reports/audit.py#L137),
`PAGE_SIZE = 50`), with the pager underneath saying `Page 1 of 3`. Both numbers
are true and together they are misleading: what you are reading is a page, and
the header does not say so. CSV export is the way to get all 124 — that is fine
and should stay.

### Files

- `pages/admin_tabs/reports/shared.py`
- `pages/admin_tabs/reports/audit.py`
- `pages/admin_tabs/reports/telemetry.py`

### Change

`paginated_event_log` already receives `total`, `page` and `page_size`
([`shared.py:297`](../../../pages/admin_tabs/reports/shared.py#L297)) — it has
everything it needs and is handed a pre-formatted `count_label` instead. Replace
that param with a noun (`count_noun='entries'` / `'events'`) and render the range
itself: `Showing 51–100 of 124 entries`. When `total <= page_size`, render the
plain `124 entries` — the range adds nothing on a single page.

Both callers change (audit and telemetry, which has the same shape). This is the
whole task; do not add a page-size selector.

### Verify

Audit report with the seeded ~124 rows: header, table and pager agree on pages 1,
2 and 3, and the CSV filename still carries the page number
(`audit-log-page-2-…`, [`audit.py:136`](../../../pages/admin_tabs/reports/audit.py#L136))
— the export is per-page and its label should not now imply otherwise. Check the
telemetry log the same way, and both at 390 px where the label wraps.

---

## T4.3 — Give the dashboard the one control its numbers demand

**Why.** The dashboard is the only report with no filters and no export. That is
defensible for a landing page — except that its loudest KPI is
`Peak players 14 / 12`, rendered in `negative` because it is over the configured
ceiling ([`dashboard.py:129`](../../../pages/admin_tabs/reports/dashboard.py#L129)),
computed over a window the operator cannot change
([`:82`](../../../pages/admin_tabs/reports/dashboard.py#L82) —
`SystemConfigService.get_event_window()`). The one number most likely to make
someone ask *"over what period?"* is the one with no way to answer.

**Decided: no CSV on the dashboard.** Its four numbers are derived from four
reports that each already export, and wave 2's T2.6 links each KPI to the report
that explains it. A fifth export of the same data is a maintenance cost, not a
feature. Say so in the commit message so F5 does not get re-opened as "still no
export".

### Files

- `pages/admin_tabs/reports/dashboard.py`
- `pages/admin_tabs/reports/__init__.py`

### Change

`dashboard_page(start=None, end=None)`, resolving through the shared
`default_date_range` so an absent pair still means the event window and the
existing `Window: … (US/Eastern)` label
([`:84`](../../../pages/admin_tabs/reports/dashboard.py#L84)) keeps telling the
truth. Render the standard `date_range_filter` above the KPI strip, navigating
with `navigate_with_params(report=None, start=…, end=…)` — `reports_url` already
omits an absent `report` and the dispatcher already falls back to the dashboard
([`reports/__init__.py:61`](../../../pages/admin_tabs/reports/__init__.py#L61)),
so no new routing is needed.

The dispatcher currently calls `await dashboard_page()` with no arguments
([`:63`](../../../pages/admin_tabs/reports/__init__.py#L63)) — pass `start` and
`end` through from `params`, and only those two.

If wave 2's T2.6 has landed, the KPI links must carry the *current* window, not
the configured event window — one source of truth for the dates on this page.

### Verify

- `?start=…&end=…` with no `report` renders the dashboard over that window, the
  window label matches, and `Peak players` changes when the window does.
- Following a KPI link lands on a report showing the same window (this is the
  regression T2.6 is most likely to have introduced).
- Wave 3's scroll restore now applies to the dashboard too, since it finally has
  a filter — check it does the right thing rather than assuming.

---

## T4.4 — Docs

**Files:** `docs/features/admin-reports.md`.

Record what is now true of the framework, in the doc's existing table-and-a-line
style: every report takes a date window (including the dashboard), Insights
defaults to the data's extent rather than a fixed trailing range, and the
event-log card labels its page range. One line each; do not narrate the
implementation.

Then, when this is the last wave to merge, do the teardown listed in
[README.md](README.md#when-this-directory-is-finished) — including deleting the
audit and its rows in `docs/README.md` and `docs/reviews/README.md`.
