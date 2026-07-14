---
name: add-feature
description: >-
  End-to-end checklist for adding a feature to SGL On Site: new model →
  migration → repository → service → exports → UI → dev seed → tests. Use
  whenever a task adds a model, a service capability, or a new admin/user
  surface — it sequences the three-layer work so nothing (tenant scoping,
  audit, events, seed rows, leak tests) is forgotten, and explains which
  guardrail hooks will fire along the way.
---

# Adding a feature (three-layer walkthrough)

Work the steps **in order** — each layer builds on the one below, and the
guardrail hooks in `.claude/settings.json` assume this sequence (e.g. the Stop
hooks block the turn if a model changed without a migration or a seed row).
Skip steps that don't apply (a service-only feature has no model/migration; a
UI-only change starts at step 5).

## 1. Model (`models/`)

- Add the model to the right per-domain submodule (`models/match.py`,
  `models/volunteer.py`, …) and re-export it from `models/__init__.py`.
- **Tenant-scoped?** Almost everything a community owns is. If so:
  - `tenant = fields.ForeignKeyField('models.Tenant', related_name='...', on_delete=fields.CASCADE)`
  - Make any formerly-global unique constraint composite:
    `unique_together = (('tenant', 'name'),)`
- Enums go in `models/enums.py`.

## 2. Migration

```bash
poetry run aerich migrate && poetry run aerich upgrade
```

Never hand-edit anything under `migrations/models/` (a PreToolUse hook blocks
it). The `check_migration_drift.py` Stop hook blocks the turn if you changed a
model without generating a migration.

## 3. Repository (`application/repositories/`)

Pure data access — no business logic, audit, or notifications.

- New file `foo_repository.py`, class `FooRepository` with static async methods.
- **Tenant scoping is explicit** (no auto-scoping manager). Use
  `application/repositories/_tenant.py`:
  ```python
  from application.repositories._tenant import current_tenant_id, scoped

  return await scoped(Foo.filter(...)).order_by('-created_at')   # read
  return await Foo.create(tenant_id=current_tenant_id(), **kw)   # write
  ```
  The `check_tenant_scoping.py` hook flags unscoped reads/unstamped writes on
  tenant-FK models. A deliberately cross-tenant method (worker scan, global
  lookup) must say **"cross-tenant"**, **"unscoped"**, or **"global"** in its
  docstring/comment — that's both the convention and the hook's escape hatch.
- Export the class from `application/repositories/__init__.py` (import **and**
  `__all__` — `check_layer_exports.py` enforces this).

## 4. Service (`application/services/`)

Rules, validation, coordination. Must not import NiceGUI.

- Raise `ValueError` for user-facing errors (UI catches → `ui.notify`).
- **Audit** every create/update/delete: add a constant to `AuditActions`
  (`verb.object`, e.g. `foo.created`) and call
  `await AuditService().write_log(actor, AuditActions.FOO_CREATED, {...})`.
  Pass `actor: User` explicitly; never guard with `if actor:` (hooks enforce
  both the constant and the unguarded actor).
- **Event** after the commit + audit write, if webhook subscribers should be
  able to react:
  ```python
  from application.events import Event, EventType, event_bus
  event_bus.publish(Event.create(EventType.FOO_CREATED, {...}, actor))
  ```
  New event ⇒ add the constant to `EventType` **and** `EventType.ALL` in
  `application/events/event_types.py` (external webhook contract; the
  `check_event_types.py` hook enforces registry consistency and rejects
  string-literal event names). Tenant-internal config changes usually stay
  audit-only — see the commentary in `event_types.py` for the dividing line.
- Export from `application/services/__init__.py` (import + `__all__`).

## 5. UI (`pages/`, `theme/`) or API (`api/`) or bot (`discordbot/`)

- All three are presentation: call **services**, never
  `application.repositories` or `service.repository.*`
  (`enforce_architecture.py` blocks it). Read-only *load-or-404* model lookups
  are OK but must hand-scope: `Foo.get_or_none(id=x, tenant_id=require_tenant_id())`.
- Catch service errors: `except ValueError as e: ui.notify(str(e), color='warning')`.
- No ORM **writes** in presentation (hook-enforced).
- Protect pages with `@protected_page('/path', roles=[Role.STAFF])`.
- Datetimes: store UTC, display Eastern — use `application/utils/timezone.py`
  helpers only (hook-enforced).
- NiceGUI: `background_tasks.create(...)` not `asyncio.create_task`; capture
  `context.client` before background tasks that touch UI; `@ui.refreshable`
  for dynamic sections; never block the loop (`httpx.AsyncClient`, never
  `requests`/`time.sleep`). Check `nicegui/llms.md` in the installed package
  for the authoritative API before writing nontrivial NiceGUI code.
- New REST endpoints: document in `docs/reference/rest-api.md`.

## 6. Dev seed (`scripts/seed_dev.py`)

Add at least one representative row per new model (and each meaningful state),
idempotent (`get_or_create`) and seeded **per tenant** like the existing rows.
The `check_seed_coverage.py` Stop hook blocks the turn if a new model class
lands without touching the seed — the seed is what `/ui-validation` and every
dev environment run against.

## 7. Tests (`tests/`)

- Service/repo behavior: `tests/services/test_foo_service.py` (the
  `run_related_tests.py` hook auto-runs the file matching your edited module).
- **Tenant-scoped model ⇒ add a leak test.** Pattern: two tenants, write the
  same data under each via `with tenant_scope(a.id): ...`, assert reads under
  tenant B never see tenant A's rows. Canonical examples:
  `tests/test_tenant_isolation.py`, `tests/test_tenant_read_isolation.py`.
- Run locally with `MOCK_DISCORD=true poetry run pytest -q` (the full suite
  also runs at Stop when app code changed).

## 8. Verify in the browser

For any presentation change, run the **/ui-validation** skill — the pytest
suite cannot see client-side Vue/Quasar slot templates; only the headless
browser loop can.

## 9. Docs

Update the matching doc (`docs/reference/data-model.md` for models,
`docs/reference/services.md` for services, `docs/reference/frontend.md` for
pages, feature doc under `docs/features/`). The session-start and Stop doc
hooks report gaps; keep them quiet.
