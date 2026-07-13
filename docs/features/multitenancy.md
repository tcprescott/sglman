# Multitenancy

SGL On Site is **logically multitenant**: one process and one database serve many
independent tournament communities ("tenants"). Every request resolves to a
tenant, and the data layer scopes reads and stamps writes to that tenant so
communities never see each other's data. This doc describes the *implemented*
system; the original design rationale (and deferred host-mode addressing) lives
in [multitenancy-plan.md](../multitenancy-plan.md).

The unifying rule: **identity, the tenancy machinery, and singleton runtime
resources are global; everything a community owns or produces is tenant-scoped.**

## The model at a glance

| Concern | Where | Notes |
|---|---|---|
| Tenant context | [`application/tenant_context.py`](../../application/tenant_context.py) | Request-time `tenant_id` in a `ContextVar` + per-client fallback |
| Addressing | [`middleware/tenant.py`](../../middleware/tenant.py) | Path mode `/t/<slug>`; rewrites the ASGI scope |
| Resolution & CRUD | [`TenantService`](../reference/services.md#tenant_servicepy--tenantservice) | Cached slug/guild/domain lookup; `/platform` CRUD |
| Read scoping / write stamping | [`_tenant.py`](../../application/repositories/_tenant.py) | `scoped(qs)` and `current_tenant_id()` used by every scoped repo |
| Schema | [data-model.md § Multitenancy](../reference/data-model.md#multitenancy) | `Tenant`, `TenantMembership`, `tenant` FK on 33 models |
| Roles & membership | [`AuthService`](../reference/authentication.md) | Per-tenant roles; global `SUPER_ADMIN`; tenant-scoped authorization |
| Platform surface | [`pages/platform.py`](../../pages/platform.py) | `/platform` super-admin tenant management |

## Addressing: path mode

Every tenant is reachable at `https://<PLATFORM_HOST>/t/<slug>/…`. `TenantMiddleware`
resolves `<slug>` to a `Tenant`, sets the tenant context, and **rewrites the ASGI
scope**: `/t/<slug>` is stripped from `scope['path']` and appended to
`scope['root_path']`. So the app's single set of unprefixed routes (`/admin`,
`/equipment`, …) serve both the tenant and the platform surface, while redirects
and links built from `root_path` keep the `/t/<slug>` prefix.

- **Unknown or inactive slug → 404.**
- **No `/t/` prefix → no tenant context.** That is the *platform surface*: the
  landing/community-picker page, `/platform`, and the shared OAuth callbacks.
- **Excluded (tenant-agnostic) paths:** `/_nicegui`, `/static`, `/api`, `/sw.js`.
  The REST API derives its tenant from the bearer token; websocket/asset traffic
  carries no tenant of its own.
- **NiceGUI prefixing is automatic.** Because the page is served with the
  `root_path` prefix, NiceGUI prepends it to every absolute-path `ui.link` /
  `ui.navigate.to('/…')` client-side — so in-app navigation stays within the
  tenant with no per-call plumbing. Server-side `RedirectResponse`s do **not** get
  this, so those are prefixed explicitly with `root_path`.

Host-based addressing (a tenant's custom `domain`) is **deferred**: the nullable
`domain` column exists but is not resolved yet.

## Tenant context

[`tenant_context.py`](../../application/tenant_context.py) is the primitive the
whole layer reads. It is a peer of `application/services` (import-safe from every
layer, including repositories) and resolves the tenant in two tiers:

1. a `ContextVar` — set by `TenantMiddleware` for the HTTP request, and by
   `tenant_scope(id)` for background/no-request code; else
2. the current NiceGUI client's per-connection stash
   (`app.storage.client['tenant_id']`), written at page build while the
   middleware's contextvar was still set. This covers websocket UI event handlers,
   which run *outside* any request.

```python
from application.tenant_context import (
    get_current_tenant_id,   # int | None — contextvar, then client stash
    require_tenant_id,        # int — raises if no tenant in scope (the safety net)
    tenant_scope,             # contextmanager: bind a tenant for a block
    stash_client_tenant_id,   # persist tenant onto the NiceGUI client at page build
)
```

Anything that runs with neither tier — the Discord bot loop, the DM-queue worker,
the event-dispatch worker, the volunteer-reminder loop, `background_tasks` — must
wrap its work in an explicit `tenant_scope(tenant_id)`.

## Query scoping: explicit threading

There is **no auto-scoping ORM manager**. Instead, every scoped repository reads
the ambient tenant itself through the shared seam
[`_tenant.py`](../../application/repositories/_tenant.py):

- **Reads** wrap the queryset: `scoped(Match.filter(...))` →
  `Match.filter(..., tenant_id=current_tenant_id())`.
- **Writes** stamp it: `Match.create(..., tenant_id=current_tenant_id())`.

`current_tenant_id()` is `require_tenant_id()`, so a read that forgets to
`scoped(...)` or a write that forgets to stamp fails **loudly** (`RuntimeError`)
the moment it runs without a tenant — rather than silently querying across
tenants. That loud failure is the safety net of the explicit contract, and the
leak tests (below) assert it.

Presentation and service code that does a direct model read for simple display
hand-scopes it the same way: `Tournament.get_or_none(id=x, tenant_id=require_tenant_id())`.

**Nullable-tenant models** (`AuditLog`, `TelemetryEvent`, `UserRole`) filter to the
current tenant on read (excluding NULL platform rows) and stamp the ambient tenant
on write; `UserRole` uses NULL only for the global `SUPER_ADMIN` role.

The two tenancy tables (`Tenant`, `TenantMembership`) are served by cross-tenant
repositories that are **never** `scoped` — they resolve *which* tenant a request
belongs to. See [data-model.md § Tenancy repositories](../reference/data-model.md#tenancy-repositories-and-the-scoping-helper).

## Identity, roles, and membership

- **Users are global.** `User` has no `tenant` FK; `discord_id` / `challonge_user_id`
  / `twitch_user_id` uniques stay global. One login works across every tenant.
- **Roles are per-tenant.** `UserRole` carries a (nullable) `tenant` and a
  `(user, role, tenant)` unique. `AuthService.get_roles` / `has_role` /
  `is_staff` / `can_view_admin` evaluate within `get_current_tenant_id()`. PKs are
  global, so every tenant-aware check adds a `tenant_id` filter.
- **`SUPER_ADMIN` is global.** `AuthService.is_super_admin(user)` looks for a
  `UserRole(role=SUPER_ADMIN, tenant=NULL)` — the only role that may have a NULL
  tenant. Super-admin **bypasses** the per-tenant role gate.
- **Authorization is tenant-scoped, not membership-gated.** A `@protected_page`
  with a role requirement (or `allow_tournament_membership`) is authorized by the
  user's tenant-scoped roles / tournament-admin membership / super-admin — all
  evaluated in the current tenant, so a role in another tenant grants nothing
  here. Role-less protected pages need only authentication (matching
  pre-multitenancy access). There is deliberately **no** separate "must be a
  `TenantMembership`" gate: the app has no self-serve/invite enrollment path, so
  such a gate would lock out every new user. `TenantMembership` still records who
  belongs to a tenant (backfilled by the migration, managed on `/platform`), but
  page access derives from roles, not membership. A page reached with *no* tenant
  (a bare `/admin` on the platform host) 404s — every `@protected_page` is a
  tenant page.

See [authentication.md](../reference/authentication.md) and
[role-based-auth.md](role-based-auth.md).

## Auth, sessions, and OAuth

Path-mode tenants share one session cookie on `PLATFORM_HOST`, so session state is
handled deliberately:

- **Identity keys stay flat** (`discord_id`, `username`, `avatar`, `authenticated`,
  and the OAuth CSRF/return keys) — one login is shared across tenants, and the
  OAuth callbacks run on the bare platform host with no tenant, so they could not
  read a namespaced key.
- **Tenant-scoped UI state is namespaced** under
  `app.storage.user['by_tenant'][str(tid)]` via
  [`tenant_session.py`](../../application/utils/tenant_session.py) — e.g. the match
  table filters, whose values are tenant-local ids that would be meaningless in
  another community.
- **OAuth (Discord, Challonge, Twitch)** uses a single registered redirect URI per
  provider on `PLATFORM_HOST`, built **at request time** (Discord in
  [`pages/auth.py`](../../pages/auth.py); the redirect URIs were formerly built at
  import). The tenant return path (`/t/<slug>/…`) is captured at initiation (where
  the tenant is in scope) and stored in the session; the shared callback — which
  lands on the bare host — reads it and navigates back into the originating
  community. [`tenant_urls.py`](../../application/utils/tenant_urls.py) holds the
  pure `sanitize_return_path` logic that rejects cross-tenant and auth-route
  referrers.

**REST API:** `TenantMiddleware` skips `/api`; instead `api/dependencies.py`
resolves the PAT by hash (no tenant yet), then sets the tenant context from the
token's `tenant_id` for the duration of the request and resets it in a `finally`.

## Platform surface

Served on the bare `PLATFORM_HOST` with **no** tenant context:

- **`/` (community picker)** — [`pages/home.py`](../../pages/home.py) lists active
  tenants (each linking to its `/t/<slug>/` home) plus, for a super-admin, a link
  to `/platform`.
- **`/platform`** — [`pages/platform.py`](../../pages/platform.py), gated on
  *no tenant context* **and** `is_super_admin`. Tenant CRUD (name, slug, domain,
  guild id, active). Its queries pass explicit ids (intended cross-tenant
  capability), backed by `TenantService`, whose CRUD/grant methods are
  super-admin-gated and audited as platform-level rows (`tenant=NULL`).

## Discord: one bot, many guilds

A single bot serves every community. `discord_guild_id` is **not unique**, so a
Discord server may back several tenants; `TenantService.list_tenants_for_guild(guild_id)`
resolves *every* tenant linked to an incoming guild and the callers fan out over
them (an unknown guild resolves to an empty list and is ignored):

- **Login role sync** (`discord_service.py`) and `DiscordRoleMappingService`
  resolve the guild→tenant(s) and wrap each per-tenant sync in `tenant_scope`.
  `DiscordRoleMappingService.sync_user_roles` fans over all tenants that have a
  guild; the live `GUILD_MEMBER_UPDATE` handler (`_sync_member_roles`) fans over
  every tenant sharing the updated guild. Role mappings are tenant-scoped
  (`DiscordRoleMapping.tenant`), so a shared server's mappings stay separated by
  community and the same Discord role can grant different app roles per tenant.
- **Interaction handlers** (`crew_signup`, `crew_acknowledgment`,
  `match_acknowledgment`, `volunteer_acknowledgment`, `watch_buttons`) resolve the
  tenant from the referenced entity's `tenant_id` and wrap DB work in
  `tenant_scope`.
- **`volunteer_reminder`** does one cross-tenant scan over a wide window, then
  re-checks each assignment against **its own tenant's** lead-time
  `SystemConfiguration` inside `tenant_scope`.

### Linking a tenant to a server (verified)

Because `discord_guild_id` is no longer unique, a tenant may not simply *claim*
any guild id — that would let one community sync roles against another's server.
Linking is gated twice, by [`DiscordLinkService`](../reference/services.md):

- **App gate** — only tenant `STAFF` (or a global super-admin) may connect or
  disconnect (`can_manage_link`).
- **Discord gate** — the acting user must administer the target guild. The
  "Connect Discord server" button (Admin → Discord Roles) runs Discord's
  **bot-authorization** OAuth flow (`scope=bot`), which Discord only lets a user
  with *Manage Server* complete and which adds the bot if it is absent. The
  callback (`/oauth/discord/connect/callback`, on the platform host) exchanges the
  code for an authoritative `guild` object, then **re-checks server-side** that
  the acting user has Manage Server / Administrator / is owner of that guild
  (`DiscordService.member_can_manage_guild`, which fails closed) before stamping
  `Tenant.discord_guild_id`. No client-supplied guild id is ever trusted.

The super-admin `/platform` surface keeps a raw guild-id field as a break-glass
override. `MOCK_DISCORD` skips the OAuth round-trip and links a mock guild.

## Events, webhooks, telemetry

- `Event.create()` snapshots `tenant_id` from the ambient context (NULL for
  platform events) and includes it in `to_wire()` — additive to the webhook
  contract; `EventType` names are unchanged.
- The dispatch worker runs outside any request, so `bus.publish` wraps each async
  subscriber's coroutine in `tenant_scope(event.tenant_id)` (`_scoped`) so
  subscribers can safely use scoped services.
- The **webhook subscriber** delivers only to the event's tenant's `Webhook` rows;
  the **telemetry mirror** stamps `TelemetryEvent.tenant` from the event, and
  analytics aggregates scope by tenant. See [webhooks.md](webhooks.md),
  [telemetry.md](telemetry.md), [event-system.md](event-system.md).

## Challonge (per-tenant)

`ChallongeConnection`, `ChallongeParticipant`, `ChallongeMatch`, and
`ChallongeApiUsage` are tenant-scoped ("newest connection row per tenant is
authoritative"; usage tallied per `(tenant, period)`), so each community has its
own service account and quota. Player identity (`User.challonge_user_id` /
`twitch_user_id`) stays global — a one-time capture for the person.

## Migration and bootstrap

The `tenant`-adding migration is **additive and preserves data** — not a rebuild.
Three ordered steps in one migration: schema-add (nullable FK + new composite
uniques alongside the old), data backfill (one `default` `Tenant`, `UPDATE … SET
tenant_id` on every scoped table, a `TenantMembership` per existing user), then
constraint-tighten (`SET NOT NULL`, drop superseded single-column uniques). The
live site keeps working with no manual step. See
[data-model.md § Migrations](../reference/data-model.md#migrations).

Post-migration bootstrap and ongoing tenant management use these scripts (see
[deployment.md](../deployment.md#tenant-bootstrap-first-run-after-the-multitenancy-migration)):

| Script | Purpose |
|---|---|
| `scripts/grant_super_admin.py <discord_id>` | Grant the global `SUPER_ADMIN` role |
| `scripts/seed_tenant.py --name … --slug …` | Create a tenant (+ optionally bootstrap its first admin) |
| `scripts/grant_staff.py <discord_id> [slug]` | Grant `STAFF` within a tenant |
| `scripts/seed_dev.py` | Seed **two** tenants of fixtures for local dev |

## Testing and avoiding leaks

- An autouse fixture binds a default tenant (id 1) for every test; the `db`
  fixture creates that `Tenant` and wraps scoped models' `.create` to stamp it, so
  the existing test sites need no per-call tenant plumbing (this wrapper lives only
  in the test harness — production never auto-stamps).
- **Leak/isolation tests** (`tests/test_tenant_isolation.py`,
  `test_tenant_read_isolation.py`) create data under two tenants via explicit
  `tenant_scope` blocks and assert each tenant sees only its own rows — and that a
  scoped operation with no tenant raises.
- `tests/test_tenant_middleware.py` drives a real Starlette app to prove the scope
  rewrite routes correctly; `test_tenant_urls.py` / `test_tenant_session.py` cover
  the return-path and session-namespacing logic.

**When you add a tenant-scoped model:** give it a `tenant` FK, scope its
repository reads with `scoped(...)` and stamp writes with `current_tenant_id()`,
make any formerly-global unique composite with `tenant`, and add a leak test. If a
new background/worker path touches scoped data, wrap it in `tenant_scope`.
