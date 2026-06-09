# Feature: Mock Discord Integration

_Added: PR #5 | Status: Stable_

## What It Does

Enables local development without a live Discord application or bot token. When `MOCK_DISCORD=true`:

1. **OAuth bypass** — `/login` renders a user picker instead of redirecting to Discord OAuth. Any user in the database can be selected and their identity is stored in session. A "Create test user" shortcut is also available.
2. **DiscordService stubbed** — All `DiscordService` methods (send_dm, get_guild_member, etc.) return mock/no-op responses. No real Discord API calls are made.
3. **Bot interactions** — Discord button interactions (acknowledgment, crew signup, watch) are not testable in mock mode since there is no bot connection. Test these flows against a real Discord dev server.

## How to Enable

```bash
# .env
MOCK_DISCORD=true
```

No `DISCORD_TOKEN` required when mock mode is active.

## Key Files

| File | Role |
|---|---|
| `middleware/auth.py` | Detects `MOCK_DISCORD`; renders user-picker at `/login` instead of OAuth redirect |
| `application/services/discord_service.py` | `DiscordService` — all methods short-circuit when mock mode detected |

## Development Workflow

```bash
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
