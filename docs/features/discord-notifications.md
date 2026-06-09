# Feature: Discord Match Notifications

_Added: PRs #3, #4, #9 | Status: Stable_

## What It Does

Sends Discord DMs to relevant users when match lifecycle events occur:

- **Scheduled** — DM sent to both players when a match is first scheduled.
- **Confirmed** — DM sent when the second player confirms a submitted match.
- **Seated (Checked In)** — DM sent to players and crew when a match is seated at a stage.
- **Started** — DM sent to watchers when match begins.
- **Finished** — DM sent to players and crew with result.
- **Stage assigned** — DM to players when a stream stage is assigned.
- **Stream candidate** — DM to subscribed users (with crew signup buttons) when a match is flagged as a stream candidate.

## Key Files

| File | Role |
|---|---|
| `application/services/match_schedule_service.py` | `MatchScheduleService` — notification fan-out methods called after match state transitions |
| `application/services/discord_service.py` | `DiscordService` — `send_dm()`, `send_dm_with_crew_buttons()` |
| `application/services/tournament_notification_service.py` | Manages per-user/tournament notification preferences; fan-out queries |
| `discordbot/watch_buttons.py` | Handles "Watch match" Discord button interactions |

## How Fan-Out Works

`MatchScheduleService.notify_*` methods query:
1. The match's players.
2. Users watching the match via `MatchWatcher`.
3. Tournament subscribers (for stream candidate notifications) via `TournamentNotificationService`.

Deduplication: users who are both a player and a tournament subscriber only receive one DM.

## Notification Levels (Tournament Subscriptions)

Defined in `models.py` as `MatchNotificationLevel`:

| Level | Gets notified for |
|---|---|
| `none` | Nothing |
| `streamed` | Matches assigned to a stream stage |
| `streamed_and_candidates` | Stream-assigned + stream candidate matches |
| `all` | Every scheduled match |

Managed via `TournamentNotificationPreference` model and `tournament_notification_dialog.py`.

## Mock Mode

When `MOCK_DISCORD=true`, `DiscordService.send_dm()` logs the message instead of sending it. No Discord token required in dev.

## Testing

Notification fan-out logic is tested in `tests/test_match_service.py`. Discord DM delivery is not unit-tested (requires live Discord; covered by integration only).
