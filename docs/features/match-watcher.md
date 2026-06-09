# Feature: Match Watcher

_Added: PR #9 | Status: Stable_

## What It Does

Any logged-in user can "watch" a match to receive Discord DMs when its state changes (seated, started, finished, stage assigned). This is separate from player acknowledgment — watchers are observers, not participants.

## Key Files

| File | Role |
|---|---|
| `models.py` → `MatchWatcher` | Junction table: user × match watch subscriptions |
| `discordbot/watch_buttons.py` | Discord "Unwatch" button on watcher DMs (`make_unwatch_view`) |
| `application/services/match_watcher_service.py` | `MatchWatcherService` — `watch`/`unwatch`, query watched matches |
| `application/services/match_schedule_service.py` | Includes watcher fan-out in notify methods |
| `pages/home_tabs/schedule.py` | Shows watch/unwatch button on each match row |
| `theme/dialog/match_dialog.py` | Admin can see watcher count on a match |

## How It Works

1. User clicks "Watch" on a match in the schedule tab.
2. `MatchWatcherService.watch(match_id, user)` inserts a `MatchWatcher` row.
3. When any notify method fires in `MatchScheduleService`, watchers are fetched and included in the DM fan-out alongside players.
4. Watchers can unwatch from the same UI button (toggles) or via Discord DM button.

## Discord DM Buttons

Lifecycle DMs sent to a watcher include an "Unwatch" interactive button (custom_id `match_watch:unwatch:<match_id>`). Clicking it invokes the handler in `discordbot/watch_buttons.py`, which calls `MatchWatcherService.unwatch()`. Watching itself happens only in the web UI — there is no "watch" button on Discord.

## Deduplication

Users who are both a player and a watcher on the same match receive only one DM per event. Dedup happens in `MatchScheduleService` before the DM loop runs.

**See also:** [reference/discord-integration.md](../reference/discord-integration.md) — custom_id formats and handler implementation details.
