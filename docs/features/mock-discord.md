# Feature: Mock Discord Integration

_Added: PR #5 | Status: Stable_

## What It Does

Enables local development without a live Discord application or bot token. When `MOCK_DISCORD=true`:

1. **OAuth bypass** — `/login` renders a user picker instead of redirecting to Discord OAuth. Any user in the database can be selected and their identity is stored in session. A "Create test user" shortcut is also available.
2. **DiscordService stubbed** — `DiscordService` is swapped for `MockDiscordService`, which mirrors the real public surface and returns success/no-op responses (logging to stdout) so notification code paths run end-to-end. No real Discord API calls are made. Stub methods: `send_dm`, `send_dm_with_crew_buttons`, `send_dm_with_acknowledgment_button`, `send_dm_with_crew_acknowledgment_button`, `send_dm_with_volunteer_acknowledgment_button`, `send_dm_with_unwatch_button`, `get_bot`, `list_guilds`, `list_guild_roles`, `add_role_to_user`, `remove_role_from_user`, `get_member_role_ids`, `get_guild_summary`, `member_can_manage_guild`.
3. **Server-connect flow works offline** — the "Connect Discord server" flow (bot-authorization OAuth) is short-circuited: the tenant admin page redirects straight to the callback with a mock guild id instead of hopping to Discord, and `member_can_manage_guild` returns `True`, so `Tenant.discord_guild_id` gets set without a real Discord round-trip.
4. **Bot interactions** — Discord button interactions (acknowledgment, crew signup, watch) are not testable in mock mode since there is no bot connection. Test these flows against a real Discord dev server.

### Mock Discord data

The fake API's servers, roles, and per-member role assignments are defined in one
place — [`application/utils/mock_discord_data.py`](../../application/utils/mock_discord_data.py) — and every
`MockDiscordService` method reads from it, so the data stays self-consistent. It
is **kept in sync with `scripts/seed_dev.py`**: the two guild ids and the four
*mapped* role ids/names match the dev seed, so a mock member's roles resolve
against the seeded `DiscordRoleMapping` rows and login role sync grants the
expected app roles. `get_member_role_ids` hands each user a deterministic, varied
role set (everyone is at least a Volunteer), so role sync does real work in mock
mode. To enrich the fixtures — more servers, more roles, or a specific user's
roles — edit that module (`MOCK_GUILDS`, a guild's `roles`, or `MOCK_MEMBER_ROLES`).

## How to Enable

```bash
# .env
MOCK_DISCORD=true
```

No `DISCORD_TOKEN` required when mock mode is active.

## Key Files

| File | Role |
|---|---|
| `application/utils/mock_discord.py` | `is_mock_discord()` — single source of truth for the flag; refuses to start if enabled in production |
| `pages/auth.py` | `create()` detects `MOCK_DISCORD` and delegates to its private `_create_mock()` (which renders the user-picker login page that impersonates an existing user or creates a new one) instead of the OAuth redirect |
| `application/services/discord_service.py` | Defines `MockDiscordService`; aliases `DiscordService = MockDiscordService` when mock mode is detected |
| `application/utils/mock_discord_data.py` | Fixture data (guilds, roles, member roles) the mock service returns; kept in sync with `scripts/seed_dev.py` |

## Development Workflow

```bash
./start.sh mock            # shortcut: sets ENVIRONMENT=development, MOCK_DISCORD=true, MOCK_CHALLONGE=true
# or, to mock only Discord:
MOCK_DISCORD=true ./start.sh dev
# Navigate to http://localhost:8000/login
# Pick any existing user from the dropdown
# Proceed as that user
```

## Notes

- Test users created via the picker are real database rows — they persist between restarts.
- Role assignments and tournament enrollments work normally in mock mode.
- The Discord bot does not start when `MOCK_DISCORD=true` (`main.py:init_discord_bot()` checks the flag).

**See also:** [reference/authentication.md](../reference/authentication.md) — how the mock login page replaces the OAuth routes.
