# Feature: Match Watcher

_Added: PR #9 | Status: Stable_

## What It Does

Any logged-in user can "watch" a match to receive Discord DMs when its state changes (seated, started, finished, stage assigned). This is separate from player acknowledgment — watchers are observers, not participants.

## Key Files

| File | Role |
|---|---|
| `models.py` → `MatchWatcher` | Junction table: user × match watch subscriptions |
| `discordbot/watch_buttons.py` | Discord button handler: "Watch this match" / "Stop watching" |
| `application/services/match_watcher_service.py` | `MatchWatcherService` — add/remove watchers, query watcher list |
| `application/services/match_schedule_service.py` | Includes watcher fan-out in notify methods |
| `pages/home_tabs/schedule.py` | Shows watch/unwatch button on each match row |
| `theme/dialog/match_dialog.py` | Admin can see watcher count on a match |

## How It Works

1. User clicks "Watch" on a match in the schedule tab.
2. `MatchWatcherService.add_watcher(user, match)` inserts a `MatchWatcher` row.
3. When any notify method fires in `MatchScheduleService`, watchers are fetched and included in the DM fan-out alongside players.
4. Watchers can unwatch from the same UI button (toggles) or via Discord DM button.

## Discord DM Buttons

The initial notification DM sent to a watcher includes "Stop Watching" as an interactive button. Clicking it calls `discordbot/watch_buttons.py`, which calls `MatchWatcherService.remove_watcher()`.

## Deduplication

Users who are both a player and a watcher on the same match receive only one DM per event. Dedup happens in `MatchScheduleService` before the DM loop runs.
