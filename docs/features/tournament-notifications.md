# Feature: Tournament Notification Preferences

_Added: PR #4 | Status: Stable_

## What It Does

Users can subscribe to a tournament to receive Discord DMs about matches — beyond just their own matches. Subscription level controls how much noise they receive.

## Notification Levels

Defined in `models.py` as `MatchNotificationLevel(str, Enum)`:

| Level | When DMs Are Sent |
|---|---|
| `none` | Never (effectively unsubscribed) |
| `streamed` | Only matches that have been assigned to a stream stage |
| `streamed_and_candidates` | Stream-assigned matches + matches flagged as stream candidates |
| `all` | Every scheduled match in the tournament |

## Key Files

| File | Role |
|---|---|
| `models.py` → `TournamentNotificationPreference` | User × Tournament × Level |
| `application/services/tournament_notification_service.py` | CRUD for preferences; subscriber fan-out queries |
| `application/services/match_schedule_service.py` | Calls `TournamentNotificationService.get_subscribers()` during fan-out |
| `theme/dialog/tournament_notification_dialog.py` | UI for users to set their preference per tournament |

## User Flow

1. User opens the schedule or home page.
2. Finds a "Notification Preferences" button for a tournament.
3. `TournamentNotificationDialog` opens; user picks a level.
4. `TournamentNotificationService.set_preference(user, tournament, level)` upserts the preference.

## Integration With Match Scheduling

When `MatchScheduleService.notify_tournament_subscribers_scheduled()` fires (e.g., match created or marked as stream candidate):

1. Queries `TournamentNotificationPreference` for subscribers at the appropriate level.
2. Deduplicates against players already in the fan-out.
3. Sends DMs via `DiscordService.send_dm()` or `send_dm_with_crew_buttons()`.

## Stream Candidate Flag

`Match.is_stream_candidate` (bool) is set by admins in `AdminMatchDialog`. When toggled on, `MatchScheduleService` triggers a DM fan-out to all `streamed_and_candidates`-level subscribers, including interactive crew signup buttons.

**See also:** [reference/discord-integration.md](../reference/discord-integration.md) — implementation reference for the bot, DM queue, and button handlers.
