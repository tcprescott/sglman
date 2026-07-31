# Wizzrobe - Claude Development Guide

Wizzrobe is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for Wizzrobe events. It uses Tortoise ORM with PostgreSQL, integrates with Discord for auth and notifications, and runs as a single Docker container.

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
| MCP server (`/mcp`), its OAuth flow & tool catalogue | [docs/features/mcp-server.md](docs/features/mcp-server.md) |
| Randomizer integrations & presets | [docs/reference/seed-generation.md](docs/reference/seed-generation.md) |
| In-process event bus (publish/subscribe) | [docs/features/event-system.md](docs/features/event-system.md) |
| Outbound webhooks (event subscriber) | [docs/features/webhooks.md](docs/features/webhooks.md) |
| Datetime/timezone implementation | [docs/timezone-handling.md](docs/timezone-handling.md) |
| Multitenancy (tenant context, `/t/<slug>`, query scoping, `/platform`) | [docs/features/multitenancy.md](docs/features/multitenancy.md) |
| Per-tenant feature flags (two-tier availability + enable, gating) | [docs/features/feature-flags.md](docs/features/feature-flags.md) |
| Engagement telemetry (page views, interactions, event mirror) | [docs/features/telemetry.md](docs/features/telemetry.md) |
| Discord bot, notifications, role sync, mock mode | [docs/features/discord.md](docs/features/discord.md) |
| Crew signup, match acknowledgment, watching | [docs/features/match-participation.md](docs/features/match-participation.md) |
| Online tournaments (presets, race rooms, qualifiers, SG sync) | [docs/features/online-tournaments.md](docs/features/online-tournaments.md) |
| Single-worker constraint and the way out of it | [docs/scaling-roadmap.md](docs/scaling-roadmap.md) |
| Remaining per-feature docs | [docs/features/](docs/features/) |

## Architecture: three-layer pattern

Respect these boundaries — they are the most-violated and most-important rule in the codebase:

```
Presentation (pages/, theme/)  →  Service (application/services/)  →  Repository (application/repositories/)  →  Models (models/)
```

- **Presentation** renders NiceGUI, handles interaction, calls services, catches their errors and shows `ui.notify()`. No business logic; no ORM *writes*. Read-only ORM lookups for simple display are acceptable but repositories are preferred.
- **Service** enforces rules/validation, coordinates repositories, writes audit logs, sends Discord notifications. Raises `ValueError` for user-facing errors. Must not import NiceGUI.
- **Repository** is pure data access (CRUD, queries, `prefetch_related`). No business logic, audit, or notifications.
- **Entry surfaces** — `api/` (REST routers), `discordbot/` (Discord interaction handlers) and `mcpserver/` (MCP tools) are peers of the web UI presentation layer: they call services and may do read-only *load-or-404* model lookups (the sanctioned shape is `Tournament.get_or_none(...)` in `api/routers/tournament_actions.py`), but must **not** import `application.repositories` or reach through `service.repository.*`. Route reads through a service method (e.g. `get_user_from_discord_id`, `UserService.get_user_by_id`, `MatchService.get_by_id`). `enforce_architecture.py` classifies all three as presentation and enforces this.

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

**Event publishing:** after a service commits a change, fire-and-forget an event on the in-process bus so subscribers (webhooks, UI refresh) can react. When the change is also audited — the usual case — do both in one call rather than hand-rolling the pair (`check_dry_regressions.py` blocks a new `write_log` + `event_bus.publish` sequence):

```python
await self.audit_service.write_and_publish(
    actor, AuditActions.MATCH_CREATED, details, EventType.MATCH_CREATED,
    event_extra={'tournament_id': match.tournament_id},   # event-only routing keys
    # or event_details={...} for a wholly separate event payload
)
```

Use bare `event_bus.publish(Event.create(EventType.X, {...}, actor))` (`from application.events import Event, EventType, event_bus`) only where there is no audit row to pair with — a worker observation, or a publish that must fire on a path the audit deliberately skips. `EventType` names mirror `AuditActions` and are an **external contract** — add a member to `EventType` + `EventType.ALL` for a new event; treat renames as breaking. `publish` is synchronous, never raises, and never blocks. Lives at `application/events/` (a peer of `services/`, so it's exempt from the architecture hook). Its narrow sibling `application/events/match_live.py` is **not** the same thing: that one carries only `(match_id, change_type)` to nudge open UI views. Publish domain events on `event_bus`; use `match_live` only for UI refresh. Detail: [docs/features/event-system.md](docs/features/event-system.md).

## Timezone handling

**All datetimes are stored in UTC; user-facing times render on a per-request local clock.** Never store localized datetimes; never display raw UTC. Every conversion goes through `application/utils/timezone.py` (`parse_local_datetime`, `combine_local`, `local_day_bounds`, `format_local_time`/`_date`/`_display`, `now_local`, `today_local`, `to_local`, `to_utc_aware`, `timezone_label`).

Which clock is resolved once per page build and read back synchronously from `application/timezone_context.py` — the same contextvar + client-stash shape as `tenant_context.py`. A community either **pins** one zone (`Tenant.config['timezone']`, Admin → Timezone) or **follows each viewer** (their `User.timezone`, else the browser's zone from the `wiz_tz` cookie, else the community default).

Three rules that are easy to get wrong:
- **Every builder takes an optional `tz`; `tz=None` means "the current viewer".** Output that is *not* for the request's viewer must pass one explicitly — a cached/shared page, a tenant-anchored rule (tournament hours), a worker render. Use `TimezoneService.tenant_timezone_name()` + `tz_scope(...)`.
- **Discord gets native `<t:unix:F>` markup** (`discord_embeds.time_field`), never a formatted string — each recipient's client localizes it. **REST and webhooks stay UTC.**
- **A date derived from an instant moves with the zone.** Never bare `datetime.combine` (naive → read as UTC) or `date.today()`; use `combine_local` / `local_day_bounds` / `today_local`.

Full table, DST edges (nonexistent times raise), and storage notes: [docs/timezone-handling.md](docs/timezone-handling.md).

## Multitenancy

The app is **logically multitenant**: one DB, a `tenant` FK on nearly every model a community owns, tenant resolved per request from `/t/<slug>`. **Identity (`User`) is global; almost everything a community owns is tenant-scoped.** There is **no auto-scoping manager** — scoping is explicit:

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

Gating a subsystem is **two obligations, and UI-only gating is not gating**:

1. **Hide it at the entry surfaces** — `@protected_page(feature=FeatureFlag.X)`
   for pages, `and FeatureFlag.X in live` on admin/home tabs,
   `require_feature(...)` on REST routers, an `is_enabled` skip in workers, and
   `AuthService.can_view_volunteer`-style resolution for any nav link *to* a
   gated page (never offer a link the gate will reject).
2. **Enforce it in the owning service** — `@requires_feature(FeatureFlag.X)`
   (from `application.feature_flags`) on the service's public entry methods:
   every mutation, plus the top-level reads that return the feature's data. It
   raises `FeatureDisabledError` (a `NotFoundError`, so REST 404s and UI
   `except ValueError` notifies). Without this the UI hides the feature while
   every other caller — a new page, a Discord handler, a worker, an un-mounted
   router — still reaches it.

Still an **authorization-style gate at the boundary**, never a DB read inside a
transaction; the guard reads a per-request cache, so repeated checks cost one
pass. Two deliberate carve-outs: a **soft integration point** called from an
unrelated flow (`push_result_if_linked`, the triforce-text embed) returns a
neutral value instead of raising, and a **worker** skips the tenant rather than
raising. Each flag declares its owning `service_modules` in its
`FeatureFlagSpec`; `check_feature_flag_gating.py` enforces both halves. A
super-admin does **not** bypass a flag.

**When adding a feature, always ask whether it warrants a flag** (step 0 above);
do not retrofit existing features.
Detail: [docs/features/feature-flags.md](docs/features/feature-flags.md).

## Authentication

Role-based via the `UserRole` junction table — there is **no** `permission` field on `User`. The `Role` enum has eleven members: the seven per-tenant community roles `STAFF`, `PROCTOR`, `STREAM_MANAGER`, `TRIFORCE_SUBMITTER`, `VOLUNTEER_COORDINATOR`, `EQUIPMENT_MANAGER`, `VOLUNTEER`; three per-tenant online-tournament admin roles `PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN` (each gates a management surface/worker the way STAFF gates the rest); and the one global platform role `SUPER_ADMIN` (its `UserRole` row carries `tenant=NULL`, checked via `AuthService.is_super_admin`, and bypasses the per-tenant role gate). Canonical list: `models.Role` / [docs/reference/authentication.md](docs/reference/authentication.md#roles). Identity lives in `app.storage.user` (`discord_id`). Use `AuthService`:

```python
from application.services import AuthService, get_user_from_discord_id
from models import Role

user = await get_user_from_discord_id(app.storage.user.get('discord_id'))  # User | None
await AuthService.has_role(user, Role.STAFF)        # bool
await AuthService.get_roles(user)                   # set[Role]
await AuthService.can_view_admin(user)              # any admin role / membership
```

Protect routes with `@protected_page('/path', roles=[Role.STAFF])` (the `roles=` kwarg is optional). A spectator surface that must work signed out uses `@public_page('/path')` instead — same tenant resolution and feature gate, but the route never joins `protected_routes`, so `AuthMiddleware` does not redirect to `/login`; the page body must tolerate `user is None` and everything it renders is world-readable (currently the bracket views). Detail: [docs/reference/authentication.md](docs/reference/authentication.md).

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
- **Every `ui.table` needs a mobile card view** — a bare table overflows a phone and hides its row-action buttons off-screen. Call `enable_mobile_grid(table, columns, actions=…, field_slots=…)` (`from theme.tables.mobile_grid import enable_mobile_grid`) right after building the table; it adds `:grid="Quasar.Screen.lt.md"` + a `.wiz-grid-card` `item` slot. The four family tables (match/user/tournament/equipment) keep bespoke `item` slots; a table that must stay a table opts out with a `# mobile-grid: exempt` comment. The `check_table_grid` hook enforces this. Detail: [docs/reference/frontend.md](docs/reference/frontend.md#responsive-tables--the-mobile-grid-rule).
