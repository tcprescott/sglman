# Multitenancy Plan (proposal)

> Status: **proposed, not implemented.** This is a design/implementation plan for
> making SGLMan logically multitenant. No code in this plan has shipped. When work
> begins, track progress in [current-state.md](current-state.md).
>
> _Revised 2026-07-11: realigned with the current codebase (36 models — event bus,
> webhooks, telemetry, web push, equipment, feedback, and Challonge/Twitch identity
> now exist; `Team`/`UserTeams`/`Announcement` no longer do) and expanded to support
> **both path-based and host-based** tenant addressing._

## Context

SGLMan is currently a single-tenant FastAPI + NiceGUI + Tortoise/PostgreSQL app
(single Docker container, single uvicorn worker). The goal is to host **multiple
independent tournament communities** from one deployment, each addressable **by
path on a shared platform host and/or by its own custom domain**, with a
**central, tenant-agnostic management surface** for provisioning tenants.

This is **logical** multitenancy: one shared database, shared tables, a
`tenant_id` discriminator column on tenant-scoped rows, and a request-time tenant
context resolved from the URL (Host header or `/t/<slug>` path prefix).

### Scope decisions
1. Shared DB / shared tables / `tenant_id` column.
2. **Dual-mode addressing.** Every tenant has a URL-safe `slug` and is always
   reachable path-based at `https://<PLATFORM_HOST>/t/<slug>/…`. A tenant may
   *additionally* attach a custom `domain` for host-based access. Both modes
   resolve to the same tenant context and serve the same routes.
3. **Discord: one bot, many guilds.** A single bot token/process joins every tenant's guild; routing keyed on `guild_id`.
4. **Users: global identity, tenant membership.** One `User` row per `discord_id`; linked Challonge and Twitch identities stay on the global `User`; a membership join ties users to tenants; roles become per-tenant.
5. **Central management on the platform host** at a reserved path (e.g. `/platform`), gated by a new **global `SUPER_ADMIN`** role, not tied to any tenant. A dedicated admin domain is no longer required (path mode makes it unnecessary); one can be layered on later without schema change.
6. **Fresh start on data** — existing rows are disposable; schema designed cleanly, aerich migrations regenerated. No backfill.

---

## Architecture additions

- **Tenant context primitive** — `application/tenant_context.py`: a
  `contextvars.ContextVar[int|None]` with `set/get`, `require_tenant_id()`
  (raises if absent), and a `tenant_scope(tid)` context manager for
  background/no-request code. Safe because there is one loop/worker and
  contextvars propagate across `await` within a task.
  - **The websocket trap (bigger than background tasks):** the HTTP middleware
    only sees the initial page load. Once NiceGUI's websocket takes over, **every
    UI event handler** runs outside any request — no Host header, no path prefix,
    no contextvar. So: during page build (while the middleware's contextvar *is*
    set), the page decorator stashes the tenant id into per-connection storage
    (`app.storage.client['tenant_id']`), and `require_tenant_id()` resolves in
    order: (1) contextvar, (2) the current NiceGUI client's stash (lazy import,
    only when a client context exists), else raise. Explicit `tenant_scope(tid)`
    remains required for the Discord bot loop, the DM queue worker, the event
    dispatch worker, the volunteer reminder loop, and `background_tasks` (capture
    `tid` at page build alongside `context.client` — note: `context.client`, not
    `Client.current`, which does not exist in NiceGUI 3.x).
- **Query scoping = explicit + safety net.** The *contract* is explicit
  `tenant_id` threaded through the repository layer (services read context, repos
  filter and stamp). A custom `TenantManager(Manager)` that injects
  `.filter(tenant_id=ctx)` is added as defense-in-depth, but is **not** the sole
  mechanism: it does not auto-stamp `.create()`, and it is bypassed by
  `prefetch_related` / related-manager access. Manager defaults to *unscoped when
  context is None* so super-admin cross-tenant queries still work;
  `require_tenant_id()` raising is what catches forgotten scopes. The manager is
  deliberately **not** applied to global identity/infrastructure tables (`User`,
  `Tenant`, `TenantMembership`, `UserRole`, `WebPushSubscription`, `ApiToken`)
  because those are queried across tenants — e.g. a global super-admin `UserRole`
  row has a NULL tenant and must remain visible inside a tenant request.
- **URL helpers** — `tenant_path(path)` prepends `/t/<slug>` in path mode and
  nothing in host mode (reads the current request's `root_path` / tenant
  context); `tenant_base_url()` returns the tenant's canonical absolute base
  (`https://<domain>` if a custom domain is attached, else
  `https://<PLATFORM_HOST>/t/<slug>`). Every internally generated URL —
  `ui.navigate.to`, `ui.link`, `RedirectResponse`, OAuth `next` targets, and the
  absolute deep links embedded in Discord DMs and web-push payloads — must go
  through these helpers. This is the main tax of path mode.

---

## Phased implementation (each phase independently testable)

### Phase 0 — Tenant context primitive
Create `application/tenant_context.py` (contextvar + `set/get/require` +
`tenant_scope` + the NiceGUI client-stash fallback described above). Unit-test
set/get/reset, the context manager, and the fallback order. No behavior change.

### Phase 1 — Schema (`models.py`)
- New `Tenant`: `name`, `slug` (unique, indexed, URL-safe — path routing key),
  `domain` (unique, indexed, **nullable** — custom domain is optional),
  `discord_guild_id` (BigInt, null, indexed — bot routing key), `is_active`,
  `config` (JSON), timestamps.
- New `TenantMembership(user, tenant)` with `unique_together(user, tenant)`.
- `Role` enum: add `SUPER_ADMIN` (joining the existing seven roles). `UserRole`:
  add nullable `tenant` FK (NULL only for SUPER_ADMIN); `unique_together` →
  `(user, role, tenant)`; the existing `granted_by`/`source` fields are
  unchanged. Service layer enforces "tenant required unless SUPER_ADMIN".
- Add a **denormalized** `tenant` FK to every tenant-scoped model:
  - Top-level: `Tournament`, `StreamRoom`, `VolunteerPosition`,
    `VolunteerProfile`, `VolunteerAvailability`, `PlayerAvailability`,
    `SystemConfiguration`, `GeneratedSeeds`, `DiscordRoleMapping`, `ApiToken`,
    `Feedback`, `Equipment`, `Webhook`, `ChallongeConnection`,
    `ChallongeApiUsage`.
  - Tournament/match descendants: `Match`, `MatchPlayers`, `MatchAcknowledgment`,
    `TournamentPlayers`, `TriforceText`, `Commentator`, `Tracker`,
    `MatchWatcher`, `ChallongeMatch`, `ChallongeParticipant`,
    `TournamentNotificationPreference`, `VolunteerShift`, `VolunteerAssignment`,
    `VolunteerQualification`, `EquipmentLoan`, `WebhookDelivery`.
  - **Nullable tenant** on the two append-only trails: `AuditLog` and
    `TelemetryEvent` — NULL marks a platform-level row (super-admin tenant CRUD,
    platform page views); everything else is stamped from context.
  - Children carry their own `tenant_id` for single-predicate filtering; service
    asserts child tenant == parent tenant on create.
- **Composite uniques (per tenant):** `StreamRoom.name` → `(tenant, name)`;
  `VolunteerPosition.name` → `(tenant, name)`; `SystemConfiguration.name` →
  `(tenant, name)`; `DiscordRoleMapping` → `(tenant, discord_role_id, app_role)`;
  `Equipment.asset_number` → `(tenant, asset_number)`; `ChallongeApiUsage.period`
  → `(tenant, period)` (per-tenant connections mean per-tenant Challonge quotas).
  Relations already scoped through a parent FK keep their existing unique keys.
- `VolunteerProfile` changes from `OneToOneField(user)` to a tenant-scoped
  `ForeignKeyField(user)` with `unique_together(tenant, user)` so opt-in is per
  tenant. The `User.volunteer_profile` reverse relation becomes
  `volunteer_profiles` and callers move from single-object to per-tenant lookup.
- **Stays global:** `User` (`discord_id`, `challonge_user_id`, `twitch_user_id`
  uniques stay global — identity links are to the person, not the community);
  `WebPushSubscription` (a device belongs to a user; pushes inherit tenancy from
  the DM producer's context); `ApiToken.token_hash` stays globally unique but
  `ApiToken` gains a `tenant` FK (a token acts within one tenant).
- Add `TenantManager` + per-model `Meta.manager` on each scoped data model (not
  on the global tables — see above).

### Phase 2 — Repository scoping
- Add helper `application/repositories/_tenant.py` (`scoped(qs, tenant_id)`).
- Every repo method across the ~29 modules in `application/repositories/` that
  calls `Model.all()/.filter()` gains a leading `tenant_id: int` param and
  applies `scoped(...)`. Create methods take `tenant_id` and stamp it
  (non-default param so it can't be forgotten); child-create methods inherit
  `tenant_id` from the parent instance.
- Services read `tid = require_tenant_id()` once and pass down. Repos stay
  context-free / unit-testable.
- Add `tenant_repository.py` (lookups by id/slug/domain/guild_id — intentionally
  NOT tenant-scoped) + `tenant_membership_repository.py` (not auto-scoped;
  membership is queried across tenants).

### Phase 3 — Dual-mode tenant resolution (`middleware/tenant.py`)
- `TenantMiddleware(BaseHTTPMiddleware)` resolves, in order (host lowercased,
  port stripped):
  1. **Host mode:** Host matches a `Tenant.domain` → set tenant context; paths
     are unprefixed. Inactive tenant → 404.
  2. **Path mode:** Host == `PLATFORM_HOST` and path matches `/t/{slug}(/…)` →
     resolve slug (unknown/inactive → 404), set tenant context, then **rewrite
     the ASGI scope**: strip `/t/<slug>` from `scope['path']` and append it to
     `scope['root_path']`. One set of registered routes serves both modes;
     redirects and `url_for` built from `root_path` keep the prefix.
  3. **Platform surface:** Host == `PLATFORM_HOST`, no `/t/` prefix → no tenant
     context; serves the landing page and `/platform` (super-admin).
  4. Unknown host → 404.
  Context is set per request and reset in `finally`. Lookups cached in
  `TenantService`.
- **Transport exclusions:** `/_nicegui/*` (websocket + assets), `/static/*`,
  `/sw.js`, and `/api/*` are tenant-agnostic transport/API paths — skip path
  rewriting and tenant-404s for them (the API derives tenant from the token,
  Phase 4; UI events get tenant via the client stash, Phase 0).
- **Ordering** in `frontend.py`: `AuthMiddleware` is added at import time via
  `app.add_middleware`; add `TenantMiddleware` *after* it (Starlette runs
  last-added outermost) so tenant context and the path rewrite happen before
  auth. `middleware/security_headers.py` ordering is unaffected.
  `AuthMiddleware`'s `referrer_path` and its `/login` redirect must be built from
  `root_path + path` so path-mode logins round-trip back to `/t/<slug>/…`.
- **Canonical redirect (optional, per-tenant config):** a tenant with a custom
  domain may opt into 301 from `/t/<slug>` to the domain. Default: both work.
- **Dev story:** path mode removes the hosts-file problem — `localhost:8000/t/a`
  and `/t/b` just work, and the platform surface is the bare host. Host-mode
  resolution is testable with an `X-Tenant-Domain` header override, honored only
  when `ENVIRONMENT=development` (matching the `MOCK_DISCORD` pattern);
  **hard-disabled in production**, asserted by a unit test.

### Phase 4 — Auth, sessions, OAuth
- `AuthService`: role checks take `tenant_id` (default `require_tenant_id()`);
  add `is_super_admin(user)` (`UserRole role=SUPER_ADMIN, tenant=None`).
  Super-admin bypasses role/membership checks. `is_tournament_admin`-style
  checks add a `tenant_id` filter (PKs are global, so same-id collisions across
  tenants are possible). `can_view_admin` / `allow_tournament_membership`
  evaluate within the current tenant.
- `@protected_page` (`middleware/auth.py`): gains a membership gate
  (authenticated-but-not-a-member of this tenant → denied even with no role
  requirement); stashes `tenant_id` into `app.storage.client` at page build
  (Phase 0 fallback); its page-view telemetry capture stamps the tenant. Add a
  thin `public_page` wrapper (or extend the decorator) so *public* tenant pages
  also stash the client tenant id. `get_user_from_discord_id()` stays global.
- **Session isolation:** path-mode tenants share one cookie on `PLATFORM_HOST`,
  so namespacing is mandatory, not defensive. Keep identity keys flat
  (`discord_id`, `username`, `avatar`, `authenticated`, `oauth_state`) so one
  login works across every tenant (this is the intended "global identity"
  behavior); namespace tenant-scoped UI state (filters, theme, referrer,
  challonge state) under `app.storage.user['by_tenant'][str(tid)]` via a
  `tenant_session()` helper. Audit all `app.storage.user` writes in `theme/` and
  `pages/`.
- **OAuth (three providers: Discord in `pages/auth.py`, Challonge in
  `pages/challonge_oauth.py`, Twitch in `pages/twitch_oauth.py`):**
  - Path-mode tenants and the platform surface share `PLATFORM_HOST`, so a
    **single redirect URI per provider on the platform host** works natively —
    no handoff needed. The `state`/`next` param carries the tenant return path
    (`/t/<slug>/…`).
  - Custom-domain tenants use the same platform-host callback as a **central
    callback with handoff**: tenant `/login` → platform `/oauth/start?next=<tenant url>`
    → callback completes OAuth → redirect back to the tenant domain with a
    short-lived signed token the tenant exchanges to set its session (single
    process + shared `STORAGE_SECRET` validates it).
  - `pages/auth.py` currently builds `REDIRECT_URL`/`OAUTH_URL` **at import
    time** — replace with request-time builders on `tenant_base_url()` /
    `PLATFORM_HOST`.
- **API (`api/dependencies.py`):** resolve the PAT by hash (no tenant context
  yet), then set tenant context from the token's `tenant_id`; role checks run
  within that tenant. If the request URL also names a tenant (host or path) that
  differs from the token's, reject with 403. `api/rate_limit.py` keys by
  token/IP, which already isolates tenants' clients; no change required.

### Phase 5 — Event bus, webhooks, telemetry
The event system (`application/events/`) postdates the original plan and needs
its own tenancy pass:
- `Event` gains a `tenant_id: Optional[int]` snapshotted in `Event.create()`
  from the ambient context (None for platform-level events); include it in
  `to_wire()`. `EventType` names are an external contract and are unchanged —
  adding the tenant field to the envelope is additive.
- `dispatch_queue`'s worker runs outside any request: wrap each async
  subscriber's coroutine in `tenant_scope(event.tenant_id)` at enqueue (in
  `bus.publish`) so subscribers can use scoped services safely.
- The **webhook subscriber** delivers only to the event's tenant's `Webhook`
  rows (`Webhook`/`WebhookDelivery` are tenant-scoped in Phase 1); webhook admin
  UI and `api/routers/webhooks.py` scope to the current tenant.
- The **telemetry mirror** stamps `TelemetryEvent.tenant` from the event;
  page-view/interaction rows stamp from the request context (NULL on the
  platform surface). `AnalyticsService` (Reports → Insights) and the engagement
  report scope every aggregate by tenant.
- **Web push** stays deployment-global for VAPID keys and per-user
  subscriptions; pushes mirror Discord DMs, whose producers already hold tenant
  context — deep links inside payloads use `tenant_base_url()`.

### Phase 6 — Platform management surface (`pages/platform.py` + `application/services/tenant_service.py`)
- Same process, served on `PLATFORM_HOST` at `/platform`; guard checks *no
  tenant context* AND `is_super_admin(user)`. Its queries pass an explicit
  `tenant_id` (the selected tenant) — the manager won't auto-scope (intended
  cross-tenant capability).
- Manages: Tenant CRUD (name, slug, domain, guild_id, is_active, config JSON),
  per-tenant Challonge status, Discord role-mapping overview, bootstrap first
  STAFF per tenant, grant/revoke SUPER_ADMIN. Register via `frontend.py`.
- The `/t/` namespace means tenant slugs can never collide with app routes; the
  platform surface reserves only its own top-level paths.

### Phase 7 — Discord one-bot-many-guilds
- `TenantService.get_by_guild_id(guild_id)` (cached). Replace the global
  `SystemConfigService.get_discord_sync_guild_id()` at its two call sites
  (`discord_service.py` login role-sync, `discord_role_mapping_service.py`) with
  guild→tenant lookup; ignore unknown guilds; wrap work in
  `tenant_scope(tenant.id)`. `DiscordRoleMappingService` keeps filtering
  mappings by `guild_id` (now correctly per tenant); role sync writes
  (`RoleSource.DISCORD`) stamp the tenant on `UserRole`.
- `discordbot/` interaction handlers (`crew_signup`, `crew_acknowledgment`,
  `match_acknowledgment`, `volunteer_acknowledgment`, `watch_buttons`) resolve
  tenant from the referenced entity's `tenant_id` and wrap DB work in
  `tenant_scope`.
- DM queue stays stateless: producers (which hold tenant context) close their
  coroutine over `tenant_scope(tid)` before enqueuing. All DM deep links move to
  `tenant_base_url()`.
- `application/services/volunteer_reminder.py` iterates due assignments
  globally; rather than iterating tenants, derive the tenant from each
  assignment row's `tenant_id` and wrap that assignment's work (config read +
  DM enqueue) in `tenant_scope`. The reminder lead-time config becomes a
  per-tenant `SystemConfiguration` read.

### Phase 8 — Challonge & Twitch per-tenant
- `ChallongeConnection` gains its `tenant` FK ("most recent row per tenant
  authoritative"); `ChallongeService` reads/writes scoped to
  `require_tenant_id()`; `ChallongeApiUsage` tallies per `(tenant, period)` so
  each tenant's service-account quota is tracked separately.
- Challonge OAuth uses the platform-host callback (Phase 4); the existing
  `state`/`next` carries the originating tenant so the callback returns to the
  right tenant and stores the connection under it.
- Identity links stay global: `User.challonge_user_id` / `User.twitch_user_id`
  are one-time identity captures for the person. Their OAuth flows just adopt
  the platform-host callback + tenant return path.

### Phase 9 — Migrations, seed, env
- Fresh start: delete `migrations/models/*` (keep `tortoise_config.py`),
  regenerate one clean initial migration against an empty DB (`aerich init-db`).
  No connection change (logical multitenancy = same DB).
- New `scripts/seed_tenant.py` (following `scripts/grant_staff.py`'s pattern):
  create a `Tenant` (name, slug, optional domain, guild_id), locate/create
  `User` by discord_id, insert `UserRole(SUPER_ADMIN, tenant=None)` + per-tenant
  `STAFF` + `TenantMembership`. Extend `scripts/seed_dev.py` to seed **two**
  tenants so the leak tests and manual dev checks have cross-tenant data from
  day one.
- New env var `PLATFORM_HOST` (shared host for path-mode tenants, the platform
  surface, and the OAuth callbacks); document in the
  [deployment.md](deployment.md) env table alongside the existing
  `REDIRECT_URL`/`OAUTH_URL` overrides it supersedes.

---

## Critical files
- `models.py` — `Tenant`/`TenantMembership`, `tenant` FK on ~33 models,
  `Role.SUPER_ADMIN`, `UserRole` change, `TenantManager`, composite uniques.
- `application/repositories/*` (~29 modules) — `tenant_id` param + filter +
  create-stamp; new `_tenant.py`, `tenant_repository.py`,
  `tenant_membership_repository.py`.
- `application/services/auth_service.py` — tenant-aware roles, super-admin,
  membership.
- `middleware/tenant.py` (new), `middleware/auth.py`, `pages/auth.py`,
  `frontend.py` — middleware order, path rewrite, membership gate, session
  namespacing, request-time OAuth URLs.
- `application/events/` (`event.py`, `bus.py`, `dispatch_queue.py`) +
  `application/services/webhook_service.py`, `telemetry_service.py`,
  `analytics_service.py` — tenant on the event envelope, scoped dispatch,
  scoped delivery/aggregation.
- `application/services/discord_service.py`, `discord_queue.py`,
  `discord_role_mapping_service.py`, `volunteer_reminder.py`, `discordbot/*` —
  guild→tenant routing, `tenant_scope`.
- `pages/challonge_oauth.py`, `pages/twitch_oauth.py`,
  `application/services/challonge_service.py`, `twitch_service.py` — per-tenant
  connection, platform-host callback.
- `api/dependencies.py` — set tenant context from token; mismatch rejection.
- New: `application/tenant_context.py`, `application/services/tenant_service.py`,
  `pages/platform.py`, `scripts/seed_tenant.py`.
- `migrations/` — regenerated.

Note: `api/` and `discordbot/` are classified as presentation by
`.claude/scripts/enforce_architecture.py` — tenant resolution there must go
through `TenantService`/middleware, never `application.repositories`.

## Key risks / gotchas
1. **Tenant context lost outside HTTP requests** — NiceGUI UI event handlers
   (websocket), `background_tasks`, the bot loop, DM-queue worker, event
   dispatch worker, and volunteer reminder all run with the contextvar unset.
   The client-stash fallback covers UI handlers; everything else must wrap in
   explicit `tenant_scope`. (Capture `context.client` for UI work in background
   tasks — `Client.current` does not exist in NiceGUI 3.x.)
2. **Path-mode link leakage** — any absolute-path link or redirect not built via
   `tenant_path()`/`root_path` silently drops the `/t/<slug>` prefix and lands
   on the platform surface. Audit `ui.navigate`, `ui.link`, `RedirectResponse`,
   `referrer_path`, OAuth `next`, and DM/web-push deep links; test every page in
   *path mode first*, since host mode can't expose this bug.
3. **Global PKs collide across tenants** — every `*_admin(user, id)` check must
   also filter `tenant_id`.
4. **Reverse relations from global `User`** (`user.tournament_players`, etc.)
   span tenants — filter by `tenant_id` explicitly; the manager doesn't touch
   related managers / prefetch.
5. **`.create()` not auto-stamped** by the manager — explicit `tenant_id` on
   every create.
6. **Session bleed on the shared host** — path-mode tenants share one cookie;
   identity staying flat is intentional, but any tenant-scoped UI state written
   outside `tenant_session()` leaks between tenants in the same browser.
7. **Import-time OAuth URLs** — `pages/auth.py` builds `REDIRECT_URL`/`OAUTH_URL`
   at module import; per-tenant/per-mode URLs must be built per request.
8. **Manager fail-open when context None** — intentional for super-admin; relies
   on `require_tenant_id()` raising to catch missed scopes.
9. **`SystemConfiguration` globals** (discord sync guild id, volunteer reminder
   lead) re-homed to `Tenant`/per-tenant config — grep all `SystemConfigService`
   callers before removing.
10. **Event envelope is an external contract** — webhook consumers will start
    receiving a `tenant_id` field; additive, but document it in
    [webhooks.md](features/webhooks.md) and keep `EventType` names stable.

---

## Verification
- **Per-phase unit tests** (contextvar + client-stash fallback; schema migrates
  clean; middleware resolution: custom domain, `/t/<slug>` rewrite +
  `root_path`, platform surface, unknown host/slug → 404).
- **Core leak test (Phase 2/4):** create data under tenant A, assert invisible
  under tenant B across every repo; same Discord user has STAFF on A and nothing
  on B; the same tenant reached via its custom domain and via `/t/<slug>` sees
  identical data.
- **Dual-mode navigation test:** crawl every registered page in path mode and
  assert all emitted links/redirects retain the `/t/<slug>` prefix (catches
  risk #2 mechanically).
- **Event/webhook isolation (Phase 5):** publish an event under tenant A and
  assert only A's webhooks receive a delivery and the telemetry mirror row is
  stamped with A.
- **Local multi-tenant (no hosts editing):** seed two tenants via `seed_dev.py`,
  switch between `localhost:8000/t/a` and `/t/b`; host mode via the dev-only
  `X-Tenant-Domain` header; a unit test asserts the override is ignored when
  `ENVIRONMENT=production`.
- **Integration mocks:** use `MOCK_DISCORD` / `MOCK_CHALLONGE` to test two-guild
  routing and per-tenant Challonge without live credentials.
- **Seed script** creates first tenant + super-admin; `/platform` reachable and
  gated to SUPER_ADMIN.
- Run the existing test suite (`poetry run pytest`) after the repo-scoping phase
  to catch unscoped-query regressions.

---

## Changes in this revision (2026-07-11)

- **Dual-mode tenancy added:** tenants addressable by `/t/<slug>` path on a
  shared `PLATFORM_HOST` *and* optionally by custom domain; `Tenant.slug` added,
  `Tenant.domain` now nullable; resolution middleware redesigned around ASGI
  path rewrite + `root_path`; URL helpers introduced; dev overrides simplified
  (path mode works on localhost natively).
- **Realigned with current schema:** dropped `Team`, `UserTeams`, `Announcement`
  (models no longer exist); added tenancy treatment for `Feedback`, `Equipment`,
  `EquipmentLoan`, `Webhook`, `WebhookDelivery`, `TelemetryEvent`,
  `ChallongeApiUsage`, `WebPushSubscription`, and the Twitch identity fields.
- **New Phase 5** for the event bus / webhooks / telemetry subsystems, which
  didn't exist when the plan was first written.
- **Admin domain dropped as a requirement** — the platform surface lives at
  `PLATFORM_HOST/platform`; `ADMIN_DOMAIN`/`AUTH_CALLBACK_DOMAIN` env vars
  replaced by a single `PLATFORM_HOST`.
- **Corrected stale references:** auth pages now live in `pages/auth.py` (not
  `middleware/`); `protected_page` also captures telemetry and supports
  tournament-membership gating; role sync writes carry `granted_by`/`source`;
  volunteer reminders now derive tenant per assignment row instead of iterating
  tenants; `Client.current` replaced with `context.client` (NiceGUI 3.x).
