# Audit Logging

Every significant admin action is recorded in `AuditLog` as an accountability
trail — who changed what, when. The writing conventions (`verb.object` naming, an
`AuditActions` constant per action, an explicit `actor`, a plain-dict `details`)
are in CLAUDE.md; this doc covers the model, the call, the coverage, and where to
read the trail.

Source: [`models/audit.py`](../../models/audit.py),
[`application/services/audit_service.py`](../../application/services/audit_service.py)
(`AuditService` + the `AuditActions` registry), report at
[`pages/admin_tabs/reports/audit.py`](../../pages/admin_tabs/reports/audit.py).

## Model

`AuditLog` is append-only. Both FKs are **nullable with `SET_NULL`** so the trail
survives a deletion: `tenant` NULL marks a platform-level row (super-admin tenant
CRUD, feature-group edits), and `user` NULL means the actor was deleted — their
identity is snapshotted into `details` at write time. `details` is a `TextField`
holding a JSON-encoded string, not a native JSON column: `write_log` serializes
the dict you pass and the report decodes it for display. Field table:
[data-model.md](../reference/data-model.md#auditlog).

## Writing an entry

`AuditService` is instantiated per service (`self.audit_service = AuditService()`).
The default call is **`write_and_publish`** — it writes the row and fires the
matching [event](event-system.md) in one step, which is what `check_dry_regressions.py`
requires instead of a hand-rolled `write_log` + `event_bus.publish` pair:

```python
await self.audit_service.write_and_publish(
    actor, AuditActions.MATCH_CREATED, {'match_id': match.id},
    EventType.MATCH_CREATED,
    event_extra={'tournament_id': match.tournament_id},  # event-only routing keys
)

# Narrow case: an audited action with no matching EventType.
await self.audit_service.write_log(actor, AuditActions.SYSTEM_CONFIG_UPDATED, details)
```

Both raise `ValueError` when `actor` is `None` — a missing actor is a caller bug,
not a reason to skip the audit.

## Coverage

`AuditActions` namespaces, one per audited domain:

| Area | Namespaces |
|---|---|
| Scheduling | `match.*` (lifecycle, seeds, stages, stations, stream candidates, watchers, stream volunteers), `crew.*`, `tournament.*`, `stage.*` |
| People | `user.*` (creation, login provisioning, role grants, profile, activation, enrollment), `role.*` (Discord-sourced grants), `discord_role.*`, `player.availability_updated` |
| Volunteers & equipment | `volunteer.*` (positions, shifts, assignments, draft scheduling), `equipment.*` (lending, check-out/in) |
| Online play | `bracket.*`, `challonge.*`, `race_room.*`, `race_room_profile.*`, `racetime.*`, `racetime_bot.*`, `sg_sync.*`, `async_qualifier.*`, `preset.*`, `randomizer_credential.*` |
| Community content | `triforce_text.*`, `feedback.*` |
| Integrations & platform | `discord.*` (server link), `discord_event.*`, `webhook.*`, `apitoken.*`, `web_push.*`, `twitch.*`, `system_config.*`, `theme.updated`, `feature_flag.*`, `feature_group.*`, `tenant.*`, `platform.super_admin_*` |

Platform-level rows (`tenant.created` / `.updated` / `.deleted`, `platform.*`,
feature-group and availability grants) carry `tenant=NULL`; everything else is
stamped with the acting tenant — including `tenant.member_*` and `tenant.join_*`,
which a community's own staff (or a would-be member) write inside that community
and which are mirrored as events. `tenant.join_requested` is the one written by
someone who is **not** scoped to its tenant, so the service wraps it in an
explicit `tenant_scope(tenant_id)`; without that the row would land in whatever
community the requester happened to be looking at.

## Viewing the log

Admin dashboard → **Reports → Audit Log**: server-paginated newest-first, with a
date range, a user filter (click through from another report), a substring match
on the action name, and expandable decoded `details`.
