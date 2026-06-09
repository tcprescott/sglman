# Feature: Audit Logging

_Added: PRs #11 (coverage pass) | Status: Stable_

## What It Does

Records all significant admin actions to an `AuditLog` table viewable in the admin Reports tab. Provides an accountability trail for match changes, user role grants, tournament edits, and crew decisions.

## Model

```python
# models.py
class AuditLog(Model):
    actor = ForeignKeyField(User, related_name='audit_logs')
    action = CharField()       # namespaced verb.object
    details = JSONField()      # arbitrary dict; rendered expandable in UI
    created_at = DatetimeField(auto_now_add=True)
```

## Writing an Audit Log Entry

```python
from application.services.audit_service import AuditService, AuditActions

await AuditService.write_log(
    actor=current_user,
    action=AuditActions.MATCH_CREATED,
    details={'match_id': match.id, 'tournament': tournament.name}
)
```

**`actor` must not be `None`** — `write_log` raises `ValueError` if it is. Do not guard with `if actor:`.

## Action String Conventions

All action constants live in `AuditActions` (in `application/services/audit_service.py`). Pattern: `verb.object`.

Examples:
- `match.created`, `match.updated`, `match.deleted`
- `match.seated`, `match.started`, `match.finished`
- `user.role_granted`, `user.role_revoked`
- `tournament.created`, `tournament.updated`
- `crew.approved`, `crew.rejected`
- `triforce_text.approved`, `triforce_text.deleted`
- `system_config.updated`

When adding a new action, add a constant to `AuditActions` rather than using a literal string.

## Viewing the Audit Log

Admin dashboard → Reports tab → Audit Log report. Supports:
- Filter by actor, action prefix, date range.
- Expand row to see full JSON `details`.
- Pagination (newest first).

## Coverage

As of PR #11, audit entries are written for all major create/update/delete operations across:
- Matches (all lifecycle transitions)
- Users (role grants/revokes, profile updates)
- Tournaments (create/update, admin/crew-coordinator membership)
- Crew (approve/reject/sign-up/undo)
- Triforce texts (submit/approve/reject/delete)
- System configuration changes
