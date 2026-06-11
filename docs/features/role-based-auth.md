# Feature: Role-Based Authorization

_Added: PR #8 | Status: Stable_

## What It Does

Replaces the original single `Permissions` integer field on `User` with a flexible many-to-many role system. A user can hold multiple roles simultaneously.

## Roles

Defined in `models.py` as `Role(str, Enum)`:

| Role | Who Has It | Grants Access To |
|---|---|---|
| `staff` | Tournament organizers | Full admin dashboard; all CRUD |
| `proctor` | Race monitors | Match management; seat/start/finish |
| `stream_manager` | Stream desk | Stage assignment; stream candidate flag |

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
from application.services.auth_service import AuthService, current_user_from_storage
from models import Role

user = await current_user_from_storage()          # User | None

await AuthService.has_role(user, Role.STAFF)            # bool
await AuthService.get_roles(user)                        # set[Role]
await AuthService.can_view_admin(user)                   # any role or tournament/crew membership
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

Users without a global role can still access the admin dashboard if they are:
- An admin of any tournament (`Tournament.admins` M2M)
- A crew coordinator of any tournament (`Tournament.crew_coordinators` M2M)

`AuthService.can_view_admin()` checks all three conditions.
