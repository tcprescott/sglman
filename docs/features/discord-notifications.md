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
- **Matchup ready to schedule** — DM to both entrants of a bracket matchup the
  moment it becomes bookable (and again, as a *rebook*, if its game is later
  called off). The one bracket-specific message: see
  [brackets.md → Notifications](brackets.md#notifications) for the rule that
  keeps it the only one.

**Series context on every match DM.** A match that is one game of a bracket
matchup leads its info block with `Round: Semifinals · Game 2 of 3 · Series 1-0`
— resolved once by `BracketService.match_dm_context` and threaded through
`_match_descriptor(match, bracket_line)`. Empty for the vast majority of matches,
which no bracket scheduled. The cancellation DM additionally swaps "Nothing
further is needed from you" for "the matchup is open to reschedule" when the
cancellation frees a bracket slot.

## Key Files

| File | Role |
|---|---|
| `application/services/match/match_schedule_service.py` | `MatchScheduleService` — notification fan-out methods called after match state transitions |
| `application/services/discord/discord_service.py` | `DiscordService` — `send_dm()`, `send_dm_with_crew_buttons()` |
| `application/services/tournament_notification_service.py` | Manages per-user/tournament notification preferences; fan-out queries |
| `discordbot/watch_buttons.py` | Handles "Watch match" Discord button interactions |

## How Fan-Out Works

`MatchScheduleService.notify_*` methods query:
1. The match's players.
2. Users watching the match via `MatchWatcher`.
3. Tournament subscribers (for stream candidate notifications) via `TournamentNotificationService`.

Deduplication: users who are both a player and a tournament subscriber only receive one DM.

### Cancellation is the exception

`notify_match_cancelled` takes a **pre-resolved** `{discord_id: is_watcher}` map
instead of a `Match`, and only fans out. Cancelling deletes the row, and every
other notifier re-queries `MatchPlayers` / `Commentator` / `Tracker` /
`MatchWatcher` when the queue worker finally awaits it — by which point the
cascade has removed them all and the DM would silently reach nobody. So
`MatchService._cancel_match` resolves recipients and builds the message *before*
the delete. Every recipient gets a plain DM, deliberately not the watcher variant,
whose Unwatch button would carry the id of a match that no longer exists.
The card uses `COLOR_CANCELLED` (deep red), the palette's only negative colour.

## Notification Levels (Tournament Subscriptions)

Defined in `models.py` as `MatchNotificationLevel`:

| Level | Gets notified for |
|---|---|
| `none` | Nothing |
| `streamed` | Matches assigned to a stream stage |
| `streamed_and_candidates` | Stream-assigned + stream candidate matches |
| `all` | Every scheduled match |

Managed via `TournamentNotificationPreference` model and `pages/home_tabs/player_edit_info.py`.

## Mock Mode

When `MOCK_DISCORD=true`, `DiscordService` is swapped for `MockDiscordService`, whose `send_dm()` prints the message to stdout (e.g. `[MOCK Discord DM] -> <user_id>: <message>`) instead of sending it. No Discord token required in dev.

## Testing

Notification fan-out logic is tested in `tests/services/test_match_schedule_service.py`. Discord DM delivery is not unit-tested (requires live Discord; covered by integration only).

**See also:** [reference/discord-integration.md](../reference/discord-integration.md) — implementation reference for the bot, DM queue, and button handlers.
