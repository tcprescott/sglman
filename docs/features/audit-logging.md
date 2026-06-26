# Feature: Audit Logging

_Added: PRs #11 (coverage pass) | Status: Stable_

## What It Does

Records all significant admin actions to an `AuditLog` table viewable in the admin Reports tab. Provides an accountability trail for match changes, user role grants, tournament edits, and crew decisions.

## Model

```python
# models.py
class AuditLog(Model):
    user = ForeignKeyField('models.User', related_name='audit_logs')  # the actor
    action = CharField(max_length=255)  # namespaced verb.object
    details = TextField(null=True)      # JSON string (encoded dict); rendered expandable in UI
    created_at = DatetimeField(auto_now_add=True)
```

`details` is a `TextField` holding a JSON-encoded string, not a native dict/JSON column. `write_log` serializes the dict you pass before storing it, and the Reports UI decodes it back for display.

## Writing an Audit Log Entry

`write_log` is an **instance method** — instantiate `AuditService` (services typically hold `self.audit_service = AuditService()` and reuse it):

```python
from application.services.audit_service import AuditService, AuditActions

audit_service = AuditService()
await audit_service.write_log(
    actor=current_user,
    action=AuditActions.MATCH_CREATED,
    details={'match_id': match.id, 'tournament': tournament.name}
)
```

**`actor` must not be `None`** — `write_log` raises `ValueError` if it is. Do not guard with `if actor:`. The `actor` argument is stored on the `AuditLog.user` field.

## Action String Conventions

All action constants live in `AuditActions` (in `application/services/audit_service.py`). Pattern: `verb.object`.

Examples:
- `match.created`, `match.updated`, `match.deleted`
- `match.seated`, `match.started`, `match.finished`
- `user.role_granted`, `user.role_revoked`
- `tournament.created`, `tournament.updated`
- `crew.signup_created`, `crew.signup_removed`, `crew.approval_changed`
- `triforce_text.approved`, `triforce_text.deleted`
- `system_config.updated`

When adding a new action, add a constant to `AuditActions` rather than using a literal string.

## Viewing the Audit Log

Admin dashboard → Reports tab → Audit Log report. Supports:
- Filter by user, action prefix, date range.
- Expand row to see the decoded JSON `details`.
- Pagination (newest first).

## Coverage

Audit entries are written for all major create/update/delete operations across these `AuditActions` namespaces:
- Matches (all lifecycle transitions, seed rolls, stage/station assignment, stream candidates, watchers)
- Users (role grants/revokes, profile updates, activation, tournament enrollment)
- Tournaments (create/update/delete, admin/crew-coordinator membership)
- Crew (signup created/removed, approval changed, acknowledged)
- Triforce texts (submit/approve/reject/delete)
- Stream rooms (create/update/delete)
- Discord role mappings & role sync grants/revokes
- API tokens (create/revoke)
- In-app feedback (submit/review)
- Equipment lending (create/update/delete, check-out/check-in)
- Player & volunteer availability, volunteer positions/shifts/assignments and draft scheduling
- Challonge integration (connect, player/tournament linking, bracket sync, result push, webhooks)
- System configuration changes

**See also:** [reference/services.md](../reference/services.md) — AuditService API and AuditActions namespaces.
