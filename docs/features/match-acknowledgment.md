# Feature: Match Acknowledgment

_Added: PRs #10, #12 | Status: Stable_

## What It Does

Two related acknowledgment flows ensure players and crew actively confirm they are ready for a match.

### Player Acknowledgment (PR #10)

When a match is scheduled, each player receives a Discord DM with interactive buttons:
- **Acknowledge** — confirms the player has seen and accepted the match.
- **I need help** — pings an admin/coordinator.

Acknowledgment state is stored in `MatchAcknowledgment` (one row per player per match). The admin schedule table shows which players have acknowledged.

### Crew Acknowledgment (PR #12)

When crew (Commentator or Tracker) sign up for a match, an admin must approve them. After approval, the crew member sees the match in the web UI with an acknowledgment prompt. Crew can acknowledge via the web; Discord DM buttons are also available.

## Key Files

| File | Role |
|---|---|
| `models.py` → `MatchAcknowledgment` | Stores per-player acknowledgment state per match |
| `discordbot/match_acknowledgment.py` | Discord button handler — receives `acknowledge` / `need_help` interactions |
| `discordbot/crew_acknowledgment.py` | Discord button handler for crew acknowledgment |
| `application/services/match_service.py` | `acknowledge_match()` — updates `MatchAcknowledgment` |
| `theme/dialog/match_dialog.py` | Admin match dialog shows per-player ack status |
| `pages/home_tabs/player.py` | Player tab shows outstanding acknowledgments |

## Flow

```
Match scheduled
  → MatchScheduleService.notify_*()
    → DiscordService.send_dm_with_ack_buttons(player)
      → Player clicks "Acknowledge" in Discord
        → discordbot/match_acknowledgment.py on_interaction()
          → MatchService.acknowledge_match(player, match)
            → MatchAcknowledgment.update_or_create(...)
```

## Crew Acknowledgment Flow

```
Crew signs up (web or Discord DM)
  → AdminMatchDialog shows pending crew
    → Admin approves crew
      → Crew sees match in their schedule
        → Crew clicks "Acknowledge" in web UI or Discord DM
          → CrewService.acknowledge_crew(crew, match)
```

## Status Visibility

The admin schedule table highlights matches with unacknowledged players. The `MatchAcknowledgment` table is queried via `MatchRepository.get_acknowledgments_for_match()`.
