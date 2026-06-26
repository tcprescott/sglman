# Feature: Role-Based Authorization

_Added: PR #8 | Status: Stable_

## What It Does

Replaces the original single `Permissions` integer field on `User` with a flexible many-to-many role system. A user can hold multiple roles simultaneously.

## Roles

Defined in `models.py` as `Role(str, Enum)`:

| Role | Who Has It | Grants Access To |
|---|---|---|
| `staff` | Tournament organizers | Full admin dashboard; all CRUD; grant/revoke roles |
| `proctor` | Race monitors | Race/schedule workflow on the `/volunteer` page; seat/start/finish/confirm/seed (no Admin access) |
| `stream_manager` | Stream desk | Admin dashboard; stage assignment; stream candidate flag; CRUD on stream rooms |
| `triforce_submitter` | Paid submitters | Submit Triforce texts on active tournaments whose generator supports them (no Admin access) |
| `volunteer_coordinator` | Volunteer leads | Admin dashboard; manage volunteer positions, shifts, and assignments |
| `equipment_manager` | Equipment leads | Admin dashboard; CRUD on lending assets; check equipment in/out; view private notes/owner |
| `volunteer` | General volunteers | Volunteer workflows on the `/volunteer` page; check equipment out to themselves (no Admin access) |

Roles are stored in the `UserRole` junction table. Each row records who granted the role (`granted_by` FK to User), when, and its `source` (`manual` vs `discord`). Roles can be granted by hand by Staff **or** synced automatically from a user's Discord roles at login — see [discord-role-sync.md](discord-role-sync.md). The sync only ever revokes the `discord`-sourced roles it created; `manual` grants are preserved.

## Key Files

| File | Role |
|---|---|
| `models.py` → `Role`, `UserRole` | Enum definition and junction model |
| `application/services/auth_service.py` | `AuthService` — all role-check helpers |
| `middleware/auth.py` | `@protected_page` — enforces login + optional role at page level |
| `pages/admin.py` | Uses `AuthService.can_view_admin()` to gate dashboard access |
| `theme/dialog/user_edit_dialog.py` | Admin grants/revokes roles via checkboxes |
| `application/services/discord_role_mapping_service.py` | Login-time Discord→app role sync (`sync_user_roles`) |

## Auth Service API

```python
from application.services import AuthService, get_user_from_discord_id
from models import Role
from nicegui import app

user = await get_user_from_discord_id(app.storage.user.get('discord_id'))   # User | None

await AuthService.has_role(user, Role.STAFF)            # bool
await AuthService.get_roles(user)                        # set[Role]
await AuthService.can_view_admin(user)                   # admin role or tournament/crew membership (not proctor/volunteer)
await AuthService.can_crud_match(user, match)            # staff or tournament admin
await AuthService.can_transition_match(user, match)      # staff, proctor, or tournament admin
await AuthService.can_manage_stream_rooms(user)          # staff or stream_manager
await AuthService.can_assign_match_stream(user, match)   # stream managers globally; TAs for their tournaments
```

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
