# Feature: Admin Reports

_Added: PR #6 | Status: Stable_

## What It Does

A multi-report framework in the admin dashboard under the "Reports" tab. Reports are rendered as filterable tables with export capability.

## Available Reports

| Report | Module | Description |
|---|---|---|
| Dashboard | `dashboard.py` | Landing page: KPI summary for the event window + cards linking to each report |
| Capacity Forecast | `capacity.py` | Concurrent player count over a date range vs. configured capacity |
| Match Operations | `match_ops.py` | Per-match start delay, duration, confirmation lag; per-tournament aggregates |
| Staff / Crew Activity | `crew.py` | Coverage by match and contribution (hours, assignments) by person |
| Stream Room Utilization | `stream_rooms.py` | Per-stage scheduled hours, gaps, back-to-back transitions |
| Volunteer Coverage | `volunteers.py` | Per-shift filled vs. needed counts over a date range, highlighting understaffed shifts |
| Audit Log | `audit.py` | Searchable/filterable view of all admin actions (expandable detail rows, paginated) |

## Key Files

| File | Role |
|---|---|
| `pages/admin_tabs/reports/__init__.py` | `_REPORT_HANDLERS` registry; `reports_page(report, **params)` dispatcher (unknown/absent report → dashboard) |
| `pages/admin_tabs/reports/<report>.py` | One module per report (see table above) |
| `pages/admin_tabs/reports/shared.py` | Shared helpers: page shell, date-range/tournament filters, CSV export button, URL param navigation |
| `application/services/reports_service.py` | Data aggregation for each report type |
| `application/services/audit_service.py` | `AuditService` + `AuditActions` constants used by all features |

## CSV Security

All CSV exports escape formula-injection characters (`=`, `+`, `-`, `@`). Numerics are not escaped (safe and expected in CSV). The escaping is applied in `application/utils/csv_export.py` and covered by `tests/test_csv_export.py`. See PR #7 for the original security fix.

## Adding a New Report

1. Create `pages/admin_tabs/reports/my_report.py` with an async page coroutine that renders inside `shared.report_page_shell()`.
2. Add aggregation logic to `application/services/reports_service.py`.
3. Register the handler in `_REPORT_HANDLERS` in `pages/admin_tabs/reports/__init__.py` and link it from the dashboard.

## Audit Log

Every meaningful create/update/delete in the application writes to `AuditLog` via `AuditService.write_log(actor, action, details)`. Action strings follow `verb.object` convention — all constants live in `AuditActions`. The audit report renders the `details` dict as expandable JSON.

**See also:** [reference/frontend.md](../reference/frontend.md) — the reports subsystem (handler registry, shared helpers); [reference/services.md](../reference/services.md) — ReportsService methods.
