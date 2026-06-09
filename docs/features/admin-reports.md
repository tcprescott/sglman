# Feature: Admin Reports

_Added: PR #6 | Status: Stable_

## What It Does

A multi-report framework in the admin dashboard under the "Reports" tab. Reports are rendered as filterable tables with export capability.

## Available Reports

| Report | Description |
|---|---|
| Crew Hours | Per-crew-member hours worked across matches (commentators and trackers) |
| Match Export | CSV export of all matches with players, times, results, stage |
| Audit Log | Searchable/filterable view of all admin actions (expandable detail rows) |

## Key Files

| File | Role |
|---|---|
| `pages/admin_tabs/reports/` | Sub-package; one file per report |
| `pages/admin_tabs/reports/audit.py` | Audit log report with pagination and expand-row |
| `pages/admin_tabs/reports/crew_hours.py` | Crew hours report |
| `pages/admin_tabs/reports/match_export.py` | Match CSV export |
| `application/services/reports_service.py` | Data aggregation for each report type |
| `application/services/audit_service.py` | `AuditService` + `AuditActions` constants used by all features |

## CSV Security

All CSV exports escape formula-injection characters (`=`, `+`, `-`, `@`). Numerics are not escaped (safe and expected in CSV). The escaping is applied in `application/services/reports_service.py` and covered by tests. See PR #7 for the original security fix.

## Adding a New Report

1. Create `pages/admin_tabs/reports/my_report.py` with a `create()` function that renders a NiceGUI card.
2. Add aggregation logic to `application/services/reports_service.py`.
3. Register the new tab in `pages/admin_tabs/reports/__init__.py` (or equivalent orchestrator).

## Audit Log

Every meaningful create/update/delete in the application writes to `AuditLog` via `AuditService.write_log(actor, action, details)`. Action strings follow `verb.object` convention — all constants live in `AuditActions`. The audit report renders the `details` dict as expandable JSON.
