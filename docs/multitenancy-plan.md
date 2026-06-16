# Multitenancy Plan (proposal)

> Status: **proposed, not implemented.** This is a design/implementation plan for
> making SGLMan logically multitenant. No code in this plan has shipped. When work
> begins, track progress in [current-state.md](current-state.md).

## Context

SGLMan is currently a single-tenant FastAPI + NiceGUI + Tortoise/PostgreSQL app
(single Docker container, single uvicorn worker). The goal is to host **multiple
independent tournament communities** from one deployment, each on its **own
domain**, with a **central, tenant-agnostic management interface** on a separate
domain for provisioning tenants.

This is **logical** multitenancy: one shared database, shared tables, a
`tenant_id` discriminator column on tenant-scoped rows, and a request-time tenant
context resolved from the Host header.

### Scope decisions
1. Shared DB / shared tables / `tenant_id` column. Tenant identified by domain (stored in DB), routed via Host header.
2. **Discord: one bot, many guilds.** A single bot token/process joins every tenant's guild; routing keyed on `guild_id`.
3. **Users: global identity, tenant membership.** One `User` row per `discord_id`; a membership join ties users to tenants; roles become per-tenant.
4. **Central management on its own domain** (e.g. `admin.sglman`); a new **global `SUPER_ADMIN`** role, not tied to any tenant.
5. **Fresh start on data** — existing rows are disposable; schema designed cleanly, aerich migrations regenerated. No backfill.

---

## Architecture additions

- **Tenant context primitive** — `application/tenant_context.py`: a `contextvars.ContextVar[int|None]` with `set/get`, `require_tenant_id()` (raises if absent), and a `tenant_scope(tid)` context manager for background/no-request code. Safe because there is one loop/worker and contextvars propagate across `await` within a task; the **trap** is that NiceGUI background tasks, the Discord bot loop, and the DM-queue worker run in *separate* tasks where the var is unset — those paths must call `tenant_scope` explicitly.
- **Query scoping = explicit + safety net.** The *contract* is explicit `tenant_id` threaded through the repository layer (services read context, repos filter and stamp). A custom `TenantManager(Manager)` that injects `.filter(tenant_id=ctx)` is added as defense-in-depth, but is **not** the sole mechanism: it does not auto-stamp `.create()`, and it is bypassed by `prefetch_related` / related-manager access. Manager defaults to *unscoped when context is None* so super-admin cross-tenant queries still work; `require_tenant_id()` raising is what catches forgotten scopes. The manager is deliberately **not** applied to identity/role tables (`User`, `Tenant`, `TenantMembership`, `UserRole`) because those are queried across tenants — e.g. a global super-admin `UserRole` row has a NULL tenant and must remain visible inside a tenant request.

---

## Phased implementation (each phase independently testable)

### Phase 0 — Tenant context primitive
Create `application/tenant_context.py` (contextvar + `set/get/require` + `tenant_scope`). Unit-test set/get/reset and the context manager. No behavior change.

### Phase 1 — Schema (`models.py`)
- New `Tenant`: `name`, `domain` (unique, indexed), `discord_guild_id` (BigInt, null, indexed — bot routing key), `is_active`, `config` (JSON), timestamps.
- New `TenantMembership(user, tenant)` with `unique_together(user, tenant)`.
- `Role` enum: add `SUPER_ADMIN`. `UserRole`: add nullable `tenant` FK (NULL only for SUPER_ADMIN); `unique_together` → `(user, role, tenant)`. Service-layer enforces "tenant required unless SUPER_ADMIN".
- Add a **denormalized** `tenant` FK to every tenant-scoped model (top-level: `Tournament`, `StreamRoom`, `VolunteerPosition`, `VolunteerProfile`, `VolunteerAvailability`, `PlayerAvailability`, `SystemConfiguration`, `AuditLog`, `ChallongeConnection`, `GeneratedSeeds`, `DiscordRoleMapping`, `ApiToken`; and tournament/match descendants: `Match`, `MatchPlayers`, `MatchAcknowledgment`, `TournamentPlayers`, `TriforceText`, `Team`, `UserTeams`, `Commentator`, `Tracker`, `MatchWatcher`, `ChallongeMatch`, `ChallongeParticipant`, `TournamentNotificationPreference`, `Announcement`, `VolunteerShift`, `VolunteerAssignment`, `VolunteerQualification`). Children carry their own `tenant_id` for single-predicate filtering; service asserts child tenant == parent tenant on create.
- **Composite uniques (per tenant):** `StreamRoom.name`→`(tenant,name)`; `VolunteerPosition.name`→`(tenant,name)`; `SystemConfiguration.name`→`(tenant,name)`; `DiscordRoleMapping`→`(tenant,discord_role_id,app_role)`. Relations already scoped through a parent FK keep their existing unique keys.
- `VolunteerProfile` changes from `OneToOneField(user)` to a tenant-scoped `ForeignKeyField(user)` with `unique_together(tenant, user)` so opt-in is per-tenant (one profile per user *per tenant*). The `User.volunteer_profile` reverse relation becomes `volunteer_profiles` and callers move from single-object to per-tenant lookup.
- **Stays global:** `User` (`discord_id` unique stays global); `ApiToken.token_hash` stays globally unique but `ApiToken` gains a `tenant` FK (token acts within one tenant).
- Add `TenantManager` + per-model `Meta.manager` on each scoped data model (not on the identity/role tables — see above).

### Phase 2 — Repository scoping
- Add helper `application/repositories/_tenant.py` (`scoped(qs, tenant_id)`).
- Every repo method in `application/repositories/` that calls `Model.all()/.filter()` gains a leading `tenant_id: int` param and applies `scoped(...)`. Create methods take `tenant_id` and stamp it (non-default param so it can't be forgotten); child-create methods inherit `tenant_id` from the parent instance.
- Services read `tid = require_tenant_id()` once and pass down. Repos stay context-free / unit-testable.
- Add `tenant_repository.py` (lookups by id/domain/guild_id — intentionally NOT tenant-scoped) + `tenant_membership_repository.py` (not auto-scoped; membership is queried across tenants).

### Phase 3 — Tenant resolution middleware (`middleware/tenant.py`)
- `TenantMiddleware(BaseHTTPMiddleware)`: lowercases Host (strip port). If `Host == ADMIN_DOMAIN` → set `request.state.is_admin_domain`, no tenant context. Else look up `Tenant` by domain (cached in `TenantService`); unknown/inactive → 404. Set context for the request, reset in `finally`.
- **Ordering** in `frontend.py`: add `AuthMiddleware` first, then `TenantMiddleware` (Starlette runs last-added outermost), so tenant context is set before auth/page handlers run.
- NiceGUI websocket events / `background_tasks`: capture `tid` at page build and re-enter `tenant_scope(tid)` inside the task (mirrors the existing `Client.current` capture pattern).
- **Dev tenant override (no hosts-file editing).** When `ENVIRONMENT=development` (or a dedicated `MOCK_TENANT=true`, matching the existing `MOCK_DISCORD` pattern), the middleware resolves the tenant from, in priority order: (1) `X-Tenant-Domain` / `X-Tenant-Id` request header, (2) `?__tenant=<domain|id>` query param (persisted into the NiceGUI session so it survives navigation within a tab), (3) a `DEV_DEFAULT_TENANT` env var. The admin domain is reachable via `?__admin=1` (or `X-Admin-Domain`) in dev. **Overrides are hard-disabled in production** — production resolves strictly by Host. A small `_resolve_tenant_dev()` helper isolates this so the prod path stays clean.

### Phase 4 — Auth
- `AuthService`: role checks take `tenant_id` (default to `require_tenant_id()`); add `is_super_admin(user)` (`UserRole role=SUPER_ADMIN, tenant=None`). Super-admin bypasses role/membership checks. `is_tournament_admin`-style checks add `tenant_id` filter (PKs are now global so same-id collisions across tenants are possible).
- `@protected_page`: gains a membership gate (authenticated-but-not-a-member of this tenant → denied even with no role requirement). Add `current_membership()` helper. `current_user_from_storage()` stays global.
- **Session isolation:** keep identity keys flat (`discord_id`, `username`, `avatar`, `authenticated`, `oauth_state`) so switching domains needs no re-login. Namespace tenant-scoped UI state (filters, theme, referrer, challonge state) under `app.storage.user['by_tenant'][str(tid)]` via a `tenant_session()` helper. Audit writes in `theme/` and OAuth-state writes.
- **OAuth across domains:** use a **single central callback domain** (admin/auth domain) registered as the lone redirect URI in the Discord & Challonge OAuth apps. Tenant `/login` → central `/oauth/start?next=<tenant url>` → central callback completes OAuth → redirect back to tenant domain with a short-lived signed token the tenant exchanges to set its session. Replace the startup-built `OAUTH_URL`/`REDIRECT_URL` with a function using the central callback.
- **API:** `api/dependencies.py` resolves the PAT by hash (no tenant context yet), then sets tenant context from the token's `tenant_id`; role checks run within that tenant.

### Phase 5 — Central management app (`pages/superadmin.py` + `application/services/tenant_service.py`)
- Same process; guard checks `request.state.is_admin_domain` AND `is_super_admin(user)`. Admin domain has **no** tenant context, so its queries pass an explicit `tenant_id` (the selected tenant) — the manager won't auto-scope (intended cross-tenant capability).
- Manages: Tenant CRUD (name, domain, guild_id, is_active, config JSON), per-tenant Challonge status, Discord role-mapping overview, bootstrap first STAFF per tenant, grant/revoke SUPER_ADMIN. Register via `frontend.py`.

### Phase 6 — Discord one-bot-many-guilds
- `TenantService.get_by_guild_id(guild_id)` (cached). In `discord_service` role sync, replace single-guild `SystemConfigService.get_discord_sync_guild_id()` with `get_by_guild_id`; ignore unknown guilds; wrap work in `tenant_scope(tenant.id)`. `DiscordRoleMappingService` keeps filtering mappings by `guild_id` (now correctly per tenant).
- `on_interaction` handlers resolve tenant from the referenced entity's `tenant_id` (or `guild_id`) and wrap DB work in `tenant_scope`.
- DM queue stays stateless: producers (which hold tenant context) close their coroutine over `tenant_scope(tid)` before enqueuing.
- `application/services/volunteer_reminder.py` currently iterates globally — make it iterate tenants and scope each.

### Phase 7 — Challonge per-tenant
- `ChallongeConnection` gains `tenant` FK ("most recent row per tenant authoritative"); `ChallongeService` reads/writes scoped to `require_tenant_id()`.
- OAuth redirect uses the central callback; extend the existing `state`/`next` to carry the originating tenant domain so the callback returns to the right tenant and stores the connection under it. `User.challonge_user_id` stays global.

### Phase 8 — Migrations & seed
- Fresh start: delete `migrations/models/*` (keep `tortoise_config.py`), regenerate one clean initial migration against an empty DB (`aerich init-db`). No connection change (logical multitenancy = same DB).
- New `scripts/seed_tenant.py`: create first `Tenant` (domain, guild_id), locate/create `User` by discord_id, insert `UserRole(SUPER_ADMIN, tenant=None)` + per-tenant `STAFF` + `TenantMembership`.
- New env vars `ADMIN_DOMAIN`, `AUTH_CALLBACK_DOMAIN`; document in [deployment.md](deployment.md) env table.

---

## Critical files
- `models.py` — Tenant/TenantMembership, `tenant` FK on ~25 models, `Role.SUPER_ADMIN`, `UserRole` change, `TenantManager`, composite uniques.
- `application/repositories/*` — `tenant_id` param + filter + create-stamp; new `_tenant.py`, `tenant_repository.py`, `tenant_membership_repository.py`.
- `application/services/auth_service.py` — tenant-aware roles, super-admin, membership.
- `middleware/tenant.py` (new), `middleware/auth.py`, `frontend.py` — middleware order, membership gate, session namespacing, central OAuth.
- `application/services/discord_service.py`, `discord_queue.py`, `discord_role_mapping_service.py`, `volunteer_reminder.py` — guild→tenant routing, `tenant_scope`.
- `middleware/challonge_oauth.py`, `application/services/challonge_service.py` — per-tenant connection, central callback.
- `api/dependencies.py` — set tenant context from token.
- New: `application/tenant_context.py`, `application/services/tenant_service.py`, `pages/superadmin.py`, `scripts/seed_tenant.py`.
- `migrations/` — regenerated.

## Key risks / gotchas
1. **Contextvar lost in background tasks** (bot loop, DM-queue worker, volunteer reminder, NiceGUI bg tasks) — must wrap in explicit `tenant_scope`.
2. **Global PKs collide across tenants** — every `*_admin(user, id)` check must also filter `tenant_id`.
3. **Reverse relations from global `User`** (`user.tournament_players`, etc.) span tenants — filter by `tenant_id` explicitly; the manager doesn't touch related managers / prefetch.
4. **`.create()` not auto-stamped** by the manager — explicit `tenant_id` on every create.
5. **NiceGUI session bleed** — one browser, multiple domains; namespace tenant UI state, keep identity flat.
6. **OAuth redirect churn** — use one central callback domain, not per-tenant registration; `STORAGE_SECRET` shared across domains (single process) validates the handoff token.
7. **Manager fail-open when context None** — intentional for super-admin; relies on `require_tenant_id()` raising to catch missed scopes.
8. **`SystemConfiguration` globals** (e.g. discord sync guild id) re-homed to `Tenant`/`Tenant.config` — grep all `SystemConfigService` callers before removing.

---

## Verification
- **Per-phase unit tests** (contextvar; schema migrate clean; middleware Host→tenant 404 on unknown).
- **Core leak test (Phase 2/4):** create data under tenant A, assert invisible under tenant B across every repo; same Discord user has STAFF on A and nothing on B.
- **Local multi-domain (no hosts editing):** run the dev server and switch tenants with the dev override — `?__tenant=<domain>` in the browser (persisted in session) or `X-Tenant-Domain` header via curl; admin domain via `?__admin=1`. Seed two tenants and confirm each shows only its own data on the same host. A unit test asserts overrides are ignored when `ENVIRONMENT=production`.
- **Integration mocks:** use `MOCK_DISCORD` / `MOCK_CHALLONGE` to test two-guild routing and per-tenant Challonge without live credentials.
- **Seed script** creates first tenant + super-admin; admin domain reachable and gated to SUPER_ADMIN.
- Run the existing test suite (`poetry run pytest`) after the repo-scoping phase to catch unscoped-query regressions.
