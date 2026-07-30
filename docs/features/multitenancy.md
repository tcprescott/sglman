# Multitenancy

Wizzrobe is **logically multitenant**: one process and one database serve many
independent tournament communities ("tenants"). Every request resolves to a
tenant, and the data layer scopes reads and stamps writes to that tenant so
communities never see each other's data. The per-task scoping obligations are in
CLAUDE.md; this doc is the mechanism behind them.

The unifying rule: **identity, the tenancy machinery, and singleton runtime
resources are global; everything a community owns or produces is tenant-scoped.**

## The model at a glance

| Concern | Where | Notes |
|---|---|---|
| Tenant context | [`application/tenant_context.py`](../../application/tenant_context.py) | Request-time `tenant_id` in a `ContextVar` + per-client fallback |
| Addressing | [`middleware/tenant.py`](../../middleware/tenant.py) | Path mode `/t/<slug>`; rewrites the ASGI scope |
| Resolution & CRUD | [`TenantService`](../reference/services.md#tenant_servicepy--tenantservice) | Cached slug/guild/domain lookup; `/platform` CRUD |
| Read scoping / write stamping | [`_tenant.py`](../../application/repositories/_tenant.py) | `scoped(qs)` and `current_tenant_id()` used by every scoped repo |
| Schema | [data-model.md § Multitenancy](../reference/data-model.md#multitenancy) | `Tenant`, `TenantMembership`, a `tenant` FK on every scoped model |
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

### Host mode: a tenant's custom domain

When a request's normalized `Host` matches a tenant's `domain`, `TenantMiddleware`
resolves that tenant with the scope **left untouched** (`root_path` stays empty —
the host owns everything) and marks the request *host mode*
(`application/tenant_context.is_host_mode`). `X-Forwarded-Host` is honored only
behind `TRUST_FORWARDED_HOST` (last value).

- **One domain, one tenant.** Host mode is authoritative there: a stray
  `/t/<other>` stays literal and 404s. Path mode stays authoritative on
  `PLATFORM_HOST`.
- **Discord login runs on the custom domain** — the `redirect_uri` is built from
  the tenant's stored `domain` (https-forced), so the host-only session cookie
  lands on the right host.
- **Profile identity links** (Challonge player-link / Twitch / racetime) complete
  their callback on the platform host. With `HOST_OAUTH_MODE=handoff` they use the
  same signed handoff as login: `/<provider>/link` → platform-host
  `/oauth/link/start` → provider OAuth → a callback minting a token that carries
  only the public provider identity → custom-domain `/oauth/link/claim`, which
  records the link where the session and tenant live (`pages/_oauth_link.py`).
- **Privileged flows stay main-site-only** — Challonge STAFF service-connect and
  Discord-connect hold real per-tenant OAuth tokens, so their buttons are hidden
  on a custom domain and their initiation routes bounce to the path-mode surface.

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

There is **no auto-scoping ORM manager** — the `scoped(...)` / stamp-on-write
contract every repository follows is stated in CLAUDE.md. The seam it goes
through is [`_tenant.py`](../../application/repositories/_tenant.py), whose
`current_tenant_id()` is `require_tenant_id()`: forgetting either half fails
loudly (`RuntimeError`) instead of querying across tenants, and the leak tests
(below) assert that failure.

Two carve-outs:

- **Nullable-tenant models** — `AuditLog`, `TelemetryEvent`, `UserRole`, and
  `ApiToken`. They filter to the current tenant on read (excluding NULL rows) and
  stamp the ambient tenant on write. NULL means "platform-level": a super-admin
  audit/telemetry row, the global `SUPER_ADMIN` role, or an MCP OAuth token, whose
  hash lookup happens before any tenant context exists.
- **The tenancy tables** (`Tenant`, `TenantMembership`, `RacetimeBotTenant`) are
  served by cross-tenant repositories that are **never** `scoped` — they answer
  *which* tenant, so they take explicit ids. See
  [data-model.md § Multitenancy](../reference/data-model.md#multitenancy).

## Identity, roles, and membership

**Users are global** (no `tenant` FK; `discord_id` / `challonge_user_id` /
`twitch_user_id` uniques stay global, so one login works everywhere), while
`UserRole` carries a nullable `tenant` and a `(user, role, tenant)` unique.
Because PKs are global, every tenant-aware `AuthService` check adds a `tenant_id`
filter; `SUPER_ADMIN` is the one role that may have `tenant=NULL` and bypasses the
per-tenant gate.

**Membership answers "who is in this community".** `TenantMembership` is the
join between a global `User` and the tenants they belong to, and it carries one
invariant:

> **Holding any role in a tenant implies membership in that tenant.**

Membership is the *wider* set — a member may hold no roles (a player), but
nobody holds a role without being a member. It is enforced where roles are
written (`UserService.grant_role`, `UserService.create_user`,
`TenantService.bootstrap_staff`, the Discord role sync), not by a reconciler.
`SUPER_ADMIN` is the exception: its row carries `tenant=NULL` and it belongs to
no community, so the grant is guarded on the role rather than on whether a
tenant happens to be in scope. `TenantMembershipService.remove_member` defends
the invariant from the other side — it refuses to eject someone who still holds
roles rather than cascading a revoke. `scripts/backfill_memberships.py` catches
up rows granted before the invariant existed.

Every **per-community person list** joins through it —
`UserService.get_community_users` (`UserRepository.get_members`), which is what
the match, equipment and bracket pickers, the Users tab, `GET /users` and the
MCP `list_users` tool all read. `get_all_users` still answers "every account on
the platform" and has exactly one caller: `/platform`'s first-admin picker,
which is choosing from every account precisely because the target community has
no members yet. The reserved `System` automation actor is excluded from the
community list — the migration made it a member of everywhere, and it was
measured being offered as a player.

**Authorization is tenant-scoped *and* membership-gated.** A tenant page runs
four checks in order — tenant → feature → **membership** → role:

| Check | Failure renders |
|---|---|
| A tenant is in scope | 404 (a bare `/admin` on the platform host is not a tenant page) |
| The feature is live here | 404 — a subsystem the tenant has off is hidden from everyone, member or not, so an unreleased feature never leaks |
| The viewer is a member | the **join door** (`theme/join_page.py`) — not a 403 |
| The viewer holds a required role | 403 |

The membership check is `middleware.auth.enforce_membership`. It renders a door
rather than a 403 on purpose: forbidden-by-role is a dead end, but not-a-member
is a state with a remedy, and the page whose whole job is to offer that remedy
should not open by saying no. It is rendered **in place**, at the URL that was
asked for, so a Discord deep link survives — approve the request, reload, and
you land where the link pointed. `SUPER_ADMIN` bypasses it, exactly as it
bypasses the role gate; it belongs to no community by design. It is deliberately
**not** gated on `Tenant.is_active` — an inactive community is a separate
concern with its own handling.

Two surfaces sit outside it. `@public_page` routes (the spectator bracket views)
are world-readable and always were. And the tenant home is registered with a
bare `ui.page` — the same function also renders the platform community picker,
which has no tenant and must stay anonymous — so it calls `enforce_membership`
itself rather than getting it from the decorator.

**Membership is acquired three ways:** a staff grant (Users tab → Add Member),
any role grant (the invariant above), or an approved **join request**.
`TenantJoinRequest` is the self-serve enrollment path whose absence used to be
the documented reason no gate existed: one row per `(user, tenant)` — a denied
request is re-opened, never appended to — with the community's staff notified
when it arrives and the requester notified on **both** outcomes.

The gate is a page-level check on a *person*. It does not apply to the REST API
or MCP (a token belongs to a tenant, and wave 2 scoped what those return), to the
Discord bot (an interaction handler acts for someone already assigned), or to
workers (they run in `tenant_scope`, not as a user). The one service that
enforces it directly is **crew signup**, because the measured symptom was a
non-member being offered *Sign Up* — and UI-only gating is not gating.

See [authentication.md](../reference/authentication.md) and
[role-based-auth.md](../reference/authentication.md#roles).

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
  [`pages/auth.py`](../../pages/auth.py)) — never at import. The tenant return path
  (`/t/<slug>/…`) is captured at initiation (where
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
  to `/platform`. It carries the same login/logout control as the tenant
  `BaseLayout`, so identity — which is global — can be established before picking a
  community.
- **`/platform`** — [`pages/platform.py`](../../pages/platform.py), gated on
  *no tenant context* **and** `is_super_admin`. Tenant CRUD (name, slug, domain,
  guild id, active), the **first-admin grant** (below), a **Setup** column, **and
  Racetime Bot CRUD + per-tenant authorization grants** (`RacetimeBotService`;
  client secrets are write-only and never shown). Its queries pass explicit ids
  (intended cross-tenant capability), backed by `TenantService` /
  `RacetimeBotService`, whose CRUD/grant methods are super-admin-gated and
  audited as platform-level rows (`tenant=NULL`).

## Provisioning a community

Creating a tenant writes exactly one row — no starter tournament, no stream
room. What it needs next is a *first admin* and an order to work in:

| Step | Where |
|---|---|
| Grant the first `STAFF` + `TenantMembership` | `/platform` → a tenant's **Admins** action (`TenantService.bootstrap_staff`), offered automatically at the end of creation. `scripts/seed_tenant.py --operator-discord-id` does the same from a shell. |
| Everything after that | The **Setup** tab on the community's `/admin` |

`TenantSetupService` derives the checklist on every read — five existence
checks, nothing stored. Three steps are **required** (a staff member, a
tournament, an enrolled player: a match cannot be scheduled without all three);
a stream room and an event window are shown but advisory, because a match
schedules without either. A community that deletes its last tournament becomes
un-set-up again and the checklist says so.

While a community is not ready, `build_admin_tabs`
([`pages/admin.py`](../../pages/admin.py)) prepends a `Setup` tab, which
`BaseLayout` then makes the landing view; once the required steps are done the
tab is not built at all. The same derivation feeds `/platform`'s Setup column
(`Ready`, or `1 of 3` with a tooltip naming what is outstanding) via
`TenantSetupService.status_for(tenant_id)`, which wraps `tenant_scope` because
the platform surface has no ambient tenant — the same shape as
`TenantService.list_staff`.

## Discord: one bot, many guilds

A single bot serves every community. `discord_guild_id` is **not unique**, so a
Discord server may back several tenants; `TenantService.list_tenants_for_guild(guild_id)`
resolves *every* tenant linked to an incoming guild and the callers fan out over
them (an unknown guild resolves to an empty list and is ignored):

- **Role sync** — `DiscordRoleMappingService.sync_user_roles` (at login) and the
  live `GUILD_MEMBER_UPDATE` handler (`_sync_member_roles`) both fan over every
  tenant sharing the guild, wrapping each per-tenant sync in `tenant_scope`.
  Mappings are tenant-scoped (`DiscordRoleMapping.tenant`), so a shared server's
  mappings stay separated and the same Discord role can grant different app roles
  per community.
- **Interaction handlers** (`crew_signup`, `crew_acknowledgment`,
  `match_acknowledgment`, `volunteer_acknowledgment`, `watch_buttons`) resolve the
  tenant from the referenced entity's `tenant_id` and wrap DB work in
  `tenant_scope`.
- **`volunteer_reminder`** does one cross-tenant scan over a wide window, then
  re-checks each assignment against **its own tenant's** lead-time
  `SystemConfiguration` inside `tenant_scope`.

### Linking a tenant to a server (verified)

Because `discord_guild_id` is not unique, a tenant may not simply *claim* a guild
id — that would let one community sync roles against another's server. Linking is
gated twice, by [`DiscordLinkService`](../reference/services.md):

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
  platform events) and includes it in `to_wire()`.
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

The `tenant`-adding migration is **additive** — schema-add (nullable FK + new
composite uniques), data backfill (one `default` `Tenant`, every scoped table
updated, a `TenantMembership` per existing user), then constraint-tighten
(`SET NOT NULL`, drop the superseded single-column uniques) in one migration. See
[data-model.md § Migrations](../reference/data-model.md#migrations).

Bootstrap and ongoing tenant management run through `scripts/grant_super_admin.py`,
`scripts/seed_tenant.py` and `scripts/grant_staff.py` — invocations in
[deployment.md](../deployment.md#tenant-and-role-bootstrap) — though the first
STAFF grant is now reachable from `/platform` itself. `scripts/seed_dev.py` seeds
two fully-provisioned tenants plus `fledgling`, deliberately stopped after its
staff grant so the setup checklist is visible in a half-done state.

## Testing and avoiding leaks

- An autouse fixture binds a default tenant (id 1) for every test; the `db`
  fixture creates that `Tenant` and wraps scoped models' `.create` to stamp it, so
  existing test sites need no per-call plumbing. The wrapper lives only in the
  harness — production never auto-stamps.
- **Leak/isolation tests** (`tests/tenancy/test_tenant_isolation.py`,
  `test_tenant_read_isolation.py`, plus the per-domain `*_tenant_isolation.py`
  modules) create data under two tenants in explicit `tenant_scope` blocks and
  assert each sees only its own rows — and that a scoped operation with no tenant
  raises.
- `test_tenant_middleware.py` drives a real Starlette app to prove the scope
  rewrite routes correctly; `test_tenant_urls.py` / `test_tenant_session.py` cover
  the return-path and session-namespacing logic.

The checklist for adding a tenant-scoped model is in CLAUDE.md § Multitenancy.
