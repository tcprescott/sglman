# Feature: Discord Role Sync

_Status: Stable_

## What It Does

Maps a user's roles in a Discord server (guild) the bot has joined onto application roles. When a user signs in via Discord OAuth, the app reads their current Discord roles and **full-syncs** the mapped application roles: granting the ones they should have and revoking the ones they no longer should — without disturbing roles a Staff member granted by hand.

Because the bot reads guild membership directly (it has the `members` intent), this needs **no extra OAuth scope** — the login flow keeps the `identify` scope. The user simply has to be a member of the configured guild.

## How It Works

1. A Staff member picks the Discord server on the admin **Settings** tab (stored in `SystemConfiguration` under `discord_role_sync_guild_id`) and defines mappings on the admin **Discord Roles** tab (`DiscordRoleMapping` rows).
2. On OAuth login, `middleware/auth.py` calls `DiscordRoleMappingService().sync_user_roles(user)` after the `User` is created/updated and before the redirect.
3. `sync_user_roles`:
   - Resolves the configured guild id; if none, it is a no-op.
   - Reads the member's Discord role ids via `DiscordService.get_member_role_ids(guild_id, discord_id)`.
   - Computes the **desired** app roles from the mappings whose `discord_role_id` the member holds.
   - **Grants** desired roles the user lacks, tagging them `source=discord`.
   - **Revokes** `source=discord` rows that are no longer desired.
   - Leaves `source=manual` rows untouched.

### Source tracking (the safety guard)

`UserRole.source` (`RoleSource` enum: `manual` | `discord`) is what makes full-sync safe:

- Roles a Staff member grants through the Users dialog are `manual` and are **never** auto-revoked.
- Roles the sync grants are `discord` and are revoked when the corresponding Discord role disappears.
- If a Staff member manually grants a role that was previously Discord-synced, `UserRoleRepository.add` upgrades the row to `manual`, **pinning** it against future revocation.

### Fail-open

`sync_user_roles` never raises. If the bot is not ready or the Discord API errors, the sync is **skipped** and existing roles are left as-is, so a Discord outage can never block login. A member who is definitively *not* in the guild yields an empty role set, which correctly revokes their Discord-sourced roles.

## Operational Prerequisites

- **Server Members Intent** (privileged) must be enabled for the bot application in the Discord Developer Portal. The code already sets `intents.members = True`; the portal toggle is the matching operational step.
- The bot must be invited to the guild (`bot` scope).
- Without these, `get_member_role_ids` returns errors/empty sets and the sync is a safe no-op.

## Key Files

| File | Role |
|---|---|
| `models.py` → `RoleSource`, `UserRole.source`, `DiscordRoleMapping` | Enum, source column, mapping table |
| `application/repositories/discord_role_mapping_repository.py` | Mapping data access |
| `application/repositories/user_role_repository.py` | `add(..., source=)` upgrade rule, `list_for_user_by_source` |
| `application/services/discord_role_mapping_service.py` | Mapping CRUD + `sync_user_roles` |
| `application/services/discord_service.py` → `get_member_role_ids` | Reads a member's Discord role ids |
| `application/services/system_config_service.py` → `get_discord_sync_guild_id` | Configured guild id |
| `middleware/auth.py` | Calls the sync during the OAuth callback |
| `pages/admin_tabs/admin_discord_roles.py` | Admin **Discord Roles** tab (manage mappings) |
| `pages/admin_tabs/admin_system_config.py` | Guild selector on the **Settings** tab |

## Audit Actions

| Action | When |
|---|---|
| `discord_role.mapping_added` / `discord_role.mapping_removed` | Staff add/remove a mapping |
| `role.discord_sync_granted` / `role.discord_sync_revoked` | The login sync grants/revokes a role (actor = the signing-in user) |

## Mock Mode

Under [`MOCK_DISCORD`](mock-discord.md), `get_member_role_ids` returns `(True, set())`, so the sync runs as a harmless no-op. The admin **Settings** guild selector shows the mock guild list and the **Discord Roles** tab still works against the database.
