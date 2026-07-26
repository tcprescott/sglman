# Feature: Role-Based Authorization

_Added: PR #8 | Status: Stable_

## What It Does

Replaces the original single `Permissions` integer field on `User` with a flexible many-to-many role system. A user can hold multiple roles simultaneously.

## Roles

Defined in `models/enums.py` as `Role(str, Enum)` — eleven members. The first
seven are per-tenant community roles; the next three are per-tenant
online-tournament admin roles; `super_admin` is the one global platform role.

| Role | Who Has It | Grants Access To |
|---|---|---|
| `staff` | Tournament organizers | Full admin dashboard; all CRUD; grant/revoke roles |
| `proctor` | Race monitors | Race/schedule workflow on the `/volunteer` page; seat/start/finish/confirm/seed (no Admin access) |
| `stream_manager` | Stream desk | Admin dashboard; stage assignment; stream candidate flag; CRUD on stream rooms |
| `triforce_submitter` | Paid submitters | Submit Triforce texts on active tournaments whose generator supports them (no Admin access) |
| `volunteer_coordinator` | Volunteer leads | Admin dashboard; manage volunteer positions, shifts, and assignments |
| `equipment_manager` | Equipment leads | Admin dashboard; CRUD on lending assets; check equipment in/out; view private notes/owner |
| `volunteer` | General volunteers | Volunteer workflows on the `/volunteer` page; check equipment out to themselves (no Admin access) |
| `preset_manager` | Seed-preset authors | Author/edit the tenant's seed-rolling presets (`can_manage_presets`) |
| `sync_admin` | Sync/integration admins | Manage upstream sync config: SpeedGaming links, Discord events, racetime bot/room config (`can_manage_sync`) |
| `qualifier_admin` | Qualifier admins | Administer async qualifiers — author pools/permalinks and work the reviewer queue (`can_admin_qualifier`) |
| `super_admin` | Platform operators | Global `/platform` tenant management; bypasses the per-tenant role gate (`is_super_admin`) and is staff-equivalent inside **every** tenant (see below) |

The three online-tournament admin roles each gate a management surface/worker the
way STAFF gates the rest, and STAFF (and the system automation actor and
`super_admin`) are always granted those capabilities too. `super_admin` is the
**only** role whose `UserRole` row carries `tenant=NULL`; it is never granted
per-tenant, stays visible inside any tenant request, and is checked via
`AuthService.is_super_admin` rather than the tenant-scoped role path.

### Super-admin authority inside a tenant

A `super_admin` has **full authority in every tenant**, including one they hold no
roles in. This is implemented in exactly one place — `AuthService.is_staff`
returns True for the global role — because STAFF is the override term in
essentially every `can_*`/`ensure_*` helper, so widening it there carries the
platform role through the whole policy surface rather than scattering
`is_super_admin` across dozens of call sites. Two deliberate limits:

- **`get_roles`/`has_role` stay literal.** They answer "which grants does this
  user hold *here*", which is what role-management UI displays; fabricating a
  STAFF grant would show a role nobody granted. Presentation code that needs the
  gate (rather than the display) must therefore call `is_staff`, not
  `Role.STAFF in await get_roles(user)` — reading the literal grant in
  `pages/admin.py` is exactly what locked super-admins out.
- **Self-service surfaces still render.** The Volunteer hub's "My Availability" /
  "My Shifts" tabs open to staff-equivalent users too. They read the *signed-in*
  user's own rows, so they are safe and simply empty for someone who volunteers
  for nothing, and the domain rule that matters is enforced where it belongs:
  saving availability without a volunteer opt-in raises a `ValueError` from
  `VolunteerAvailabilityService.set_windows` and surfaces as a notification.
- **Feature flags are not bypassed.** Authority is over what a community has
  turned *on*. A flag that is off hides its subsystem from the super-admin too —
  `/volunteer` 404s in a tenant without `VOLUNTEERS` regardless of role — so a
  platform admin never operates a feature the tenant has not enabled.

Tests: `tests/services/test_super_admin_authority.py`.

Roles are stored in the `UserRole` junction table. Each row records who granted the role (`granted_by` FK to User), when, and its `source` (`manual` vs `discord`). Roles can be granted by hand by Staff **or** synced automatically from a user's Discord roles at login — see [discord-role-sync.md](discord-role-sync.md). The sync only ever revokes the `discord`-sourced roles it created; `manual` grants are preserved.

## Key Files

| File | Role |
|---|---|
| `models/enums.py` → `Role`; `models/` → `UserRole` | Enum definition and junction model |
| `application/services/auth_service.py` | `AuthService` — all role-check helpers |
| `middleware/auth.py` | `@protected_page` — enforces login + optional role at page level |
| `pages/admin.py` | Uses `AuthService.can_view_admin()` to gate dashboard access |
| `theme/dialog/user_edit_dialog.py` | Admin grants/revokes roles via checkboxes |
| `application/services/discord/discord_role_mapping_service.py` | Login-time Discord→app role sync (`sync_user_roles`) |

## Auth Service API

```python
from application.services import AuthService, get_user_from_discord_id
from models import Role
from nicegui import app

user = await get_user_from_discord_id(app.storage.user.get('discord_id'))   # User | None

await AuthService.has_role(user, Role.STAFF)            # bool
await AuthService.get_roles(user)                        # set[Role] (tenant-scoped, excludes SUPER_ADMIN)
await AuthService.is_super_admin(user)                   # global platform role (UserRole tenant=NULL)
await AuthService.can_view_admin(user)                   # admin role, tournament/crew membership, or super-admin
await AuthService.can_crud_match(user, match)            # staff or tournament admin
await AuthService.can_transition_match(user, match)      # staff, proctor, or tournament admin
await AuthService.can_manage_stream_rooms(user)          # staff or stream_manager
await AuthService.can_assign_match_stream(user, match)   # stream managers globally; TAs for their tournaments
await AuthService.can_manage_presets(user)               # system/super-admin/staff or preset_manager
await AuthService.can_manage_sync(user)                  # system/super-admin/staff or sync_admin
await AuthService.can_admin_qualifier(user, qualifier)   # system/super-admin/staff, qualifier_admin, or per-entity admin
```

The three online-tournament gates (`can_manage_presets`, `can_manage_sync`,
`can_admin_qualifier`) share one cascade — the system automation actor,
`super_admin`, `staff`, or the matching per-tenant role (`PRESET_MANAGER` /
`SYNC_ADMIN` / `QUALIFIER_ADMIN`). Each also has a raising `ensure_*` variant
(`ensure_can_manage_presets`, `ensure_can_manage_sync`,
`ensure_can_admin_qualifier`, `ensure_super_admin`).

Full method catalog: [reference/authentication.md](../reference/authentication.md).

## Route-Level Protection

```python
from middleware.auth import protected_page
from models import Role

@protected_page('/admin', roles=[Role.STAFF])
async def admin_page():
    ...
```

Unauthenticated users are redirected to `/login`. Users without the required role see a "You do not have permission to view this page." message.

## Tournament/Crew Access

Users without an admin global role can still access the admin dashboard if they are:
- An admin of any tournament (`Tournament.admins` M2M)
- A crew coordinator of any tournament (`Tournament.crew_coordinators` M2M)

`AuthService.can_view_admin()` checks these conditions. Holding only `PROCTOR`, `TRIFORCE_SUBMITTER`, or `VOLUNTEER` does **not** grant admin access — proctors and volunteers run their workflow from the `/volunteer` page. The admin-granting roles are `STAFF`, `STREAM_MANAGER`, `EQUIPMENT_MANAGER`, and `VOLUNTEER_COORDINATOR`.
