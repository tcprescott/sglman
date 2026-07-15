# SGL On Site - Claude Development Guide

SGL On Site is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for speedgaming live events. It uses Tortoise ORM with PostgreSQL, integrates with Discord for auth and notifications, and runs as a single Docker container.

This file is the lean, always-loaded guide: the behavioral rules to follow on every task. For anything expository (tech stack, full directory map, models, env vars, routes, workflows), read the docs below rather than guessing.

## Documentation map

**Full index: [docs/README.md](docs/README.md)** — start here when unsure where something lives.

| Topic | Doc |
|---|---|
| System overview, tech stack, directory map, startup | [docs/architecture.md](docs/architecture.md) |
| Active feature status, known issues, key files | [docs/current-state.md](docs/current-state.md) |
| Local setup, mock Discord, dev data, tests, CI | [docs/development.md](docs/development.md) |
| Docker, **env-var table**, GHCR, operations | [docs/deployment.md](docs/deployment.md) |
| Three-layer pattern in depth, with examples | [docs/refactoring-guide.md](docs/refactoring-guide.md) |
| All models, ERD, enums, match lifecycle, migrations | [docs/reference/data-model.md](docs/reference/data-model.md) |
| Every service & utility module | [docs/reference/services.md](docs/reference/services.md) |
| Pages, routes, tabs, dialogs, tables, styling | [docs/reference/frontend.md](docs/reference/frontend.md) |
| OAuth mechanics, route protection, `AuthService` | [docs/reference/authentication.md](docs/reference/authentication.md) |
| Bot singleton, DM queue, interaction handlers | [docs/reference/discord-integration.md](docs/reference/discord-integration.md) |
| REST endpoints & schemas | [docs/reference/rest-api.md](docs/reference/rest-api.md) |
| Randomizer integrations & presets | [docs/reference/seed-generation.md](docs/reference/seed-generation.md) |
| In-process event bus (publish/subscribe) | [docs/features/event-system.md](docs/features/event-system.md) |
| Outbound webhooks (event subscriber) | [docs/features/webhooks.md](docs/features/webhooks.md) |
| Datetime/timezone implementation | [docs/timezone-handling.md](docs/timezone-handling.md) |
| Multitenancy (tenant context, `/t/<slug>`, query scoping, `/platform`) | [docs/features/multitenancy.md](docs/features/multitenancy.md) |
| Per-tenant feature flags (two-tier availability + enable, gating) | [docs/features/feature-flags.md](docs/features/feature-flags.md) |
| Engagement telemetry (page views, interactions, event mirror) | [docs/features/telemetry.md](docs/features/telemetry.md) |
| Per-feature docs (auth, crew, notifications, etc.) | [docs/features/](docs/features/) |

## Architecture: three-layer pattern

Respect these boundaries — they are the most-violated and most-important rule in the codebase:

```
Presentation (pages/, theme/)  →  Service (application/services/)  →  Repository (application/repositories/)  →  Models (models/)
```

- **Presentation** renders NiceGUI, handles interaction, calls services, catches their errors and shows `ui.notify()`. No business logic; no ORM *writes*. Read-only ORM lookups for simple display are acceptable but repositories are preferred.
- **Service** enforces rules/validation, coordinates repositories, writes audit logs, sends Discord notifications. Raises `ValueError` for user-facing errors. Must not import NiceGUI.
- **Repository** is pure data access (CRUD, queries, `prefetch_related`). No business logic, audit, or notifications.
- **Entry surfaces** — `api/` (REST routers) and `discordbot/` (Discord interaction handlers) are peers of the web UI presentation layer: they call services and may do read-only *load-or-404* model lookups (the sanctioned shape is `Tournament.get_or_none(...)` in `api/routers/tournament_actions.py`), but must **not** import `application.repositories` or reach through `service.repository.*`. Route reads through a service method (e.g. `get_user_from_discord_id`, `UserService.get_user_by_id`, `MatchService.get_by_id`). `enforce_architecture.py` classifies both as presentation and enforces this.

See [docs/refactoring-guide.md](docs/refactoring-guide.md) for the full pattern and examples.

### Adding a new feature
0. **Ask the user whether this feature warrants a per-tenant feature flag.** Not every feature needs one — flags exist only for deliberately-gated subsystems (see [Feature flags](#feature-flags)). Always ask; if yes, gate it (page/tab/API/worker) and register the flag. Do **not** add flags retroactively to existing features unless asked.
1. Add/update model in the `models/` package (per-domain submodule; re-export from `models/__init__.py`) → `poetry run aerich migrate && poetry run aerich upgrade`
2. Update/create the repository in `application/repositories/`
3. Update/create the service in `application/services/`
4. Export from each package's `__init__.py`
5. Build/update the UI in `pages/` or `theme/`
6. **Extend `scripts/seed_dev.py`** so the new model/feature has at least one representative row (and, where useful, each meaningful state) in the dev database. The seed script is the fixture set the [`/ui-validation`](docs/development.md) browser loop and every dev environment run against — a feature the seed never creates is a feature no one can see in the running app. Keep it idempotent (`get_or_create`) and tenant-scoped like the existing rows.

## Coding conventions

- **Async everywhere** — all DB calls and UI handlers are `async def`.
- **Type hints throughout.**
- **No direct ORM writes in UI** — always go through the service layer. Read-only display queries are OK.
- **Raise `ValueError` for user errors** in services; catch in UI and show `ui.notify(str(e), color='warning')`.
- **Audit important actions** (create/update/delete) via `AuditService`.
- **No comments explaining what code does** — only for a non-obvious constraint, workaround, or invariant.
- **Keep services stateless** — static methods or per-request instances.

**Audit logging:** action strings are namespaced `verb.object` (e.g. `match.created`) — use a constant from `AuditActions` (add one when introducing a new action), pass `actor: User` explicitly (never guard with `if actor:`), and pass `details` as a plain dict. Full conventions: [docs/features/audit-logging.md](docs/features/audit-logging.md).

**Event publishing:** after a service commits a change (and after its audit write), fire-and-forget an event on the in-process bus so subscribers (webhooks, UI refresh) can react: `event_bus.publish(Event.create(EventType.MATCH_CREATED, {...}, actor))` (`from application.events import Event, EventType, event_bus`). `EventType` names mirror `AuditActions` and are an **external contract** — add a member to `EventType` + `EventType.ALL` for a new event; treat renames as breaking. `publish` is synchronous, never raises, and never blocks. Lives at `application/events/` (a peer of `services/`, so it's exempt from the architecture hook). Detail: [docs/features/event-system.md](docs/features/event-system.md).

## Timezone handling

**All datetimes are stored in UTC; all user-facing times are US/Eastern.** Never store localized datetimes; never display raw UTC. Use `application/utils/timezone.py`:

```python
from application.utils.timezone import (
    parse_eastern_datetime,   # (date_str, time_str) → UTC datetime
    format_eastern_time,      # UTC → "HH:MM"
    format_eastern_date,      # UTC → "YYYY-MM-DD"
    format_eastern_display,   # UTC → "YYYY-MM-DD HH:MM EST"
    now_eastern, to_eastern,
)
```

Detail: [docs/timezone-handling.md](docs/timezone-handling.md).

## Multitenancy

The app is **logically multitenant**: one DB, a `tenant` FK on ~33 models, tenant resolved per request from `/t/<slug>`. **Identity (`User`) is global; almost everything a community owns is tenant-scoped.** There is **no auto-scoping manager** — scoping is explicit:

- **Repositories** scope reads and stamp writes via `application/repositories/_tenant.py`: `scoped(Match.filter(...))` for reads, `Match.create(..., tenant_id=current_tenant_id())` for writes. A direct model read in presentation/service code hand-scopes: `Tournament.get_or_none(id=x, tenant_id=require_tenant_id())`.
- `require_tenant_id()` **raises** when no tenant is in scope — that loud failure is the safety net, not a bug to swallow. Any bot/worker/`background_tasks` path that touches scoped data must wrap it in `tenant_scope(tenant_id)` (`from application.tenant_context import tenant_scope`).
- **Roles are per-tenant** (`UserRole.tenant`); `AuthService` checks evaluate within `get_current_tenant_id()`. `SUPER_ADMIN` is the one global role (`tenant=NULL`) and bypasses the per-tenant role gate. Gated `@protected_page`s authorize on tenant-scoped roles/tournament-admin/super-admin; role-less protected pages need only auth (no separate `TenantMembership` gate).
- When adding a tenant-scoped model: add the `tenant` FK, scope its repo, make formerly-global uniques composite with `tenant`, and add a leak test.

Detail: [docs/features/multitenancy.md](docs/features/multitenancy.md).

## Feature flags

Some subsystems are gated behind **per-tenant feature flags** — disabled by
default. Availability derives from a **live group/tier** (`FeatureFlagGroup` a
super-admin assigns per tenant on `/platform`; ungrouped tenants fall back to the
default group) with a tri-state per-tenant override on top; the community's
**STAFF** control enable (Admin → Features; available ⇒ on by default, opt-out
sticky). A feature is live when it is **available AND enabled**. Flags exist
**only** for deliberately-gated features — not one per feature.

```python
from application.services import FeatureFlagService
from models import FeatureFlag

if await FeatureFlagService().is_enabled(FeatureFlag.ASYNC_QUALIFIERS): ...
live = await FeatureFlagService().enabled_flags()   # set[FeatureFlag], one query
```

Gating is an **authorization-style gate at the entry surfaces**, never a DB read
inside a service transaction: `@protected_page(feature=FeatureFlag.X)` for pages,
`and FeatureFlag.X in live` on admin/home tabs, `require_feature(...)` on REST
routers, and an `is_enabled` skip in background workers. **When adding a feature,
always ask whether it warrants a flag** (step 0 above); do not retrofit existing
features. Detail: [docs/features/feature-flags.md](docs/features/feature-flags.md).

## Authentication

Role-based via the `UserRole` junction table — there is **no** `permission` field on `User`. The `Role` enum has seven members: `STAFF`, `PROCTOR`, `STREAM_MANAGER`, `TRIFORCE_SUBMITTER`, `VOLUNTEER_COORDINATOR`, `EQUIPMENT_MANAGER`, `VOLUNTEER` (canonical list: `models.Role` / [docs/features/role-based-auth.md](docs/features/role-based-auth.md)). Identity lives in `app.storage.user` (`discord_id`). Use `AuthService`:

```python
from application.services import AuthService, get_user_from_discord_id
from models import Role

user = await get_user_from_discord_id(app.storage.user.get('discord_id'))  # User | None
await AuthService.has_role(user, Role.STAFF)        # bool
await AuthService.get_roles(user)                   # set[Role]
await AuthService.can_view_admin(user)              # any admin role / membership
```

Protect routes with `@protected_page('/path', roles=[Role.STAFF])` (the `roles=` kwarg is optional). Detail: [docs/reference/authentication.md](docs/reference/authentication.md), [docs/features/role-based-auth.md](docs/features/role-based-auth.md).

## NiceGUI patterns

Fetch the authoritative API surface from `nicegui/llms.md` inside the installed package before writing NiceGUI code. The critical anti-patterns (from NiceGUI's official list) — keep these in mind:

- **Never `asyncio.create_task()` / `ensure_future()`** — bare tasks get GC'd and swallow exceptions. Use `background_tasks.create(coro())` (`from nicegui import background_tasks`).
- **Capture `context.client` before a background task that calls UI functions** (`ui.notify`, etc.) and restore it inside the task — the slot context is cleared in background tasks. Use `context.client` (`from nicegui import context`), **not** `Client.current` — the latter does not exist in NiceGUI 3.x and raises `AttributeError: type object 'Client' has no attribute 'current'` at runtime:
  ```python
  table.on('evt', lambda e: background_tasks.create(handle(e.args, context.client)))

  async def handle(row, client):
      with client:
          ...
          ui.notify('Done', color='positive')
  ```
  `Client` only supports the sync context manager (`with`), not `async with` — `nicegui.client.Client` has `__enter__`/`__exit__` only, so `async with client:` raises `TypeError: 'Client' object does not support the asynchronous context manager protocol` at runtime.
- **Never block the event loop** — all users share one loop. Use `async with httpx.AsyncClient()` (not `requests`) and `await asyncio.sleep()` (not `time.sleep()`).
- **Use `@ui.refreshable`** for dynamic sections; call `.refresh()` after data changes instead of rebuilding the page.
- **Module-level variables are shared across all users** — never store per-user state at module level; use `app.storage.user` or locals inside the `@ui.page` function.
