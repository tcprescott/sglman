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
| `application/services/tournament_notification_service.py` | CRUD for preferences (`upsert_preference`, `get_preference`, `get_user_preferences`, `get_active_tournaments`) |
| `application/repositories/tournament_notification_repository.py` | Data access, including the subscriber fan-out queries (`get_match_notification_subscribers`, `get_stream_candidate_subscribers`) |
| `application/services/match_schedule_service.py` | Reads subscribers directly via `TournamentNotificationRepository` during fan-out |
| `pages/home_tabs/player_edit_info.py` | Embeds the UI for users to set their per-tournament preference |

## User Flow

1. User opens their player info on the home page (`pages/home_tabs/player_edit_info.py`).
2. The per-tournament notification preferences are rendered inline, one selector per active tournament.
3. User picks a level for a tournament.
4. `TournamentNotificationService.upsert_preference(user, tournament_id, match_notifications)` upserts the preference.

## Integration With Match Scheduling

When `MatchScheduleService.notify_tournament_subscribers_scheduled()` fires (e.g., match created or scheduled):

1. Reads subscribers directly via `TournamentNotificationRepository.get_match_notification_subscribers()` — there is no `get_subscribers()` service abstraction.
2. Deduplicates against players already in the fan-out.
3. Sends DMs via `DiscordService.send_dm()` or `send_dm_with_crew_buttons()`.

A separate `MatchScheduleService.notify_stream_candidate_subscribers()` handles the stream-candidate path, reading from `TournamentNotificationRepository.get_stream_candidate_subscribers()`.

## Stream Candidate Flag

`Match.is_stream_candidate` (bool) is set by admins in `AdminMatchDialog`. When toggled on, `MatchScheduleService` triggers a DM fan-out to all `streamed_and_candidates`-level subscribers, including interactive crew signup buttons.

**See also:** [reference/discord-integration.md](../reference/discord-integration.md) — implementation reference for the bot, DM queue, and button handlers.
