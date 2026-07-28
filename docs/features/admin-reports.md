# Admin Reports

A multi-report framework in the admin dashboard's **Reports** tab: filterable,
URL-driven tables with CSV export. `pages/admin_tabs/reports/__init__.py` holds
the `_REPORT_HANDLERS` registry and the `reports_page(report, **params)`
dispatcher (an unknown or absent `report` falls back to the dashboard); each
report is one module beside it, and `shared.py` supplies the page shell, the
date-range/tournament filters, the export button and the URL-param navigation.

| Report | Module | Shows |
|---|---|---|
| Dashboard | `dashboard.py` | Landing page: KPI summary for the event window + cards linking to each report |
| Insights & Trends | `insights.py` | Crew participation, volunteer hours, tournament health and admin activity trended weekly/monthly across events (`AnalyticsService`) |
| Capacity Forecast | `capacity.py` | Concurrent player count over a date range vs. configured capacity |
| Match Operations | `match_ops.py` | Per-match start delay, duration, confirmation lag; per-tournament aggregates |
| Staff / Crew Activity | `crew.py` | Coverage by match and contribution (hours, assignments) by person |
| Stream Room Utilization | `stream_rooms.py` | Per-stage scheduled hours, gaps, back-to-back transitions |
| Volunteer Coverage | `volunteers.py` | Per-shift filled vs. needed counts over a date range, highlighting understaffed shifts |
| Engagement Telemetry | `telemetry.py` | Page views, interactions and the domain-event mirror over a date window — KPIs, leaderboards, filterable raw log (Staff only; see [telemetry.md](telemetry.md)) |
| Audit Log | `audit.py` | Searchable, paginated view of every audited action with expandable detail rows (see [audit-logging.md](audit-logging.md)) |

Aggregation always happens in a service, never in the page: most reports call
`ReportsService`, Insights calls `AnalyticsService`, and the three that read one
subsystem call its owner (`VolunteerScheduleService`, `TelemetryService`,
`AuditService`).

**CSV exports escape formula injection.** `application/utils/csv_export.py`
prefixes any cell starting with `=`, `+`, `-` or `@`; numerics are left alone
(safe and expected in CSV). Covered by `tests/test_csv_export.py`.

**Adding a report:** create `reports/my_report.py` rendering inside
`shared.report_page_shell()`, put its aggregation in `ReportsService`, then
register the handler in `_REPORT_HANDLERS` and link it from the dashboard.

**See also:** [frontend.md](../reference/frontend.md#reports-subsystem-pagesadmin_tabsreports) —
the reports subsystem's UI internals.
