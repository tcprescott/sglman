# Brief — Admin reports UX

Lower priority than the four briefs above it. Scope, method and leads for an audit
nobody has run yet; leads are unverified suspicions from reading the code.

## Scope

The eight report pages and their shared shell:
[`pages/admin_tabs/reports/`](../../../pages/admin_tabs/reports/) — `dashboard`,
`crew`, `capacity`, `match_ops`, `stream_rooms`, `volunteers`, `telemetry`,
`insights`, `audit` — over
[`shared.py`](../../../pages/admin_tabs/reports/shared.py) (the shell, the date
range and tournament filters, `navigate_with_params`, `kpi_card`,
`csv_export_button`, `paginated_event_log`, `themed_chart_option`) and
[`ReportsService`](../../../application/services/reports_service.py) /
`AnalyticsService`.

## Why this one, and why it is not first

Reports are staff-only, work today, and are read rather than acted on — so the
blast radius of a bad one is low. Two things still make it worth an audit:

- **There is a known, deliberately-deferred defect.**
  [current-state.md](../../current-state.md) records that every filter change
  triggers a full page reload, because all eight pages route their handlers
  through `navigate_with_params` → `ui.navigate.to`
  ([`shared.py:220`](../../../pages/admin_tabs/reports/shared.py#L220)). The
  deferral reasoning is on the record; an audit's job is to measure what it
  actually costs so the decision can be re-made with a number.
- **The crew audit found reports discovering work they cannot act on.** Reports →
  Staff / Crew Activity can filter to pending crew signups and shows coverage
  gaps, but measured **0 buttons and 0 links** in both table bodies
  ([crew-signup-ux F2](../crew-signup-ux.md#f2--critical--nothing-tells-anyone-that-a-signup-is-waiting)).
  Check whether that is a pattern: how many reports surface a problem with no path
  to the surface that fixes it?

## What to measure

1. **Filter latency, honestly.** For each report: wall-clock time and bytes for a
   single filter change (date range, tournament, and each report's own selects),
   plus whether scroll position, sort order and any expanded rows survive it.
   That number is what the deferral decision is missing.
2. **The discovery→action gap.** For every report, list what it can reveal and where
   the fix lives. Count how many require the operator to memorise an id and
   navigate to a different tab.
3. **Default date range.** `default_date_range` picks a window
   ([`shared.py:108`](../../../pages/admin_tabs/reports/shared.py#L108)) — check
   whether it can hide outstanding work that falls outside it (the crew case:
   "everything still pending" is not a date range).
4. **CSV exports.** Each report builds its own column list twice — once for the
   table, once for `csv_export_button`. Check for drift between what is shown and
   what is exported, and that exports honour the active filters.
5. **Charts.** `themed_chart_option` themes ECharts for light/dark. Verify both
   themes, an empty series, and a single-point series.
6. **Mobile.** Every report table calls `enable_mobile_grid`; verify each renders as
   cards at 390×844 and that KPI rows and charts do not force horizontal body
   scroll (the responsive-tables rule in CLAUDE.md is the standard here).
7. **Zero-data behaviour** on a fresh tenant — overlaps with
   [planned/new-tenant-onboarding-ux.md](new-tenant-onboarding-ux.md); whichever
   audit runs second should reuse the first's inventory rather than redo it.

## Leads to verify

- `clicked_row` exists in the shared shell; check which reports wire it and whether
  a row click goes anywhere useful.
- `paginated_event_log` powers the audit report; check pagination against a large
  log and whether `parse_details` renders every audit `details` shape or only the
  common ones.
- The Insights report is the largest (434 lines) and the only one with three
  tables; check whether it is one report or three wearing a trench coat.
- Telemetry report: confirm it reads the same data the MCP `telemetry_*` tools do,
  and that a tenant with almost no telemetry (the real case today) renders
  something honest rather than empty axes.

## Fixtures and roles

`seed_dev.py` seeds telemetry, audit rows, crew and volunteer data on `default`.
Drive as `staff_user`; also check a **tournament-admin-only** account, since
reports are reachable for `is_ta_any` and the data they show is tenant-wide.

## Deliverable

`docs/reviews/admin-reports-ux.md`. If the measured filter-reload cost turns out to
be small, say so plainly and recommend keeping the deferral — a measurement that
confirms an existing decision is a useful result.
