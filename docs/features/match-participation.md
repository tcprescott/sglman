# Match Participation: Crew, Acknowledgment, Watching

How people attach themselves to a match — signing up as crew, confirming they will
be there, and subscribing to updates. The DMs these flows send are documented in
[discord.md](discord.md); the button handlers behind them in
[reference/discord-integration.md](../reference/discord-integration.md).

## Crew signup and approval

Commentators and Trackers (collectively "crew") sign up per match, and a staff
member approves them. Signup works from the web or from Discord DM buttons — both
land in the same service, so the rules and audit trail are identical.

1. Signup inserts a `Commentator` or `Tracker` row with `approved=False`, either from the web UI or from the buttons on a stream-candidate DM (`discordbot/crew_signup.py`).
2. A staff member approves in the match dialog.
3. The approved crew member acknowledges — web UI or DM button.

```python
from application.services import CrewService

await CrewService().signup_crew(match_id, user, 'commentator')
await CrewService().undo_crew_signup(match_id, user, 'commentator')

crew = await CrewService().get_crew_member_by_id(crew_id, 'commentator')
await CrewService().approve_crew_member(crew, 'commentator', actor=actor)
await CrewService().update_crew_approval(crew, 'commentator', approved=False, actor=actor)
await CrewService().acknowledge_crew_assignment(crew_id, 'commentator', user)
```

The REST crew endpoints return only `approved=True` rows — enforced by a Pydantic
validator, so an unapproved signup is never exposed. Signup, approval and undo all
audit through `AuditActions.CREW_SIGNUP_CREATED` / `CREW_APPROVAL_CHANGED`.

## Acknowledgment

Two flows, both confirming someone has seen and accepted a match.

**Players** get a DM with an Acknowledge button (`match_ack:ack:<match_id>`) when a
match is scheduled. The handler in `discordbot/match_acknowledgment.py` calls
`MatchService.acknowledge_match(match_id, user)`, which upserts a
`MatchAcknowledgment` row — one per player per match.

**Crew** acknowledge after approval, via the web UI prompt on their assignments view
or the DM button in `discordbot/crew_acknowledgment.py`, routing to
`CrewService.acknowledge_crew_assignment`.

The admin schedule highlights matches with unacknowledged players; per-player state
comes from `MatchAcknowledgmentRepository.list_for_match()` / `list_for_matches()`.

## Watching

Any logged-in user can watch a match to get DMs on its state changes — watchers are
observers, not participants, and watching is independent of acknowledgment.

`MatchWatcherService.watch(match_id, user)` inserts a `MatchWatcher` row from the
schedule tab or the match dialog. Lifecycle DMs to a watcher carry an Unwatch button
(`match_watch:unwatch:<match_id>`) handled in `discordbot/watch_buttons.py`. Watching
itself is web-only — there is no Watch button on Discord, only Unwatch.

Someone who is both a player and a watcher gets one DM per event, not two; dedup
happens in `MatchScheduleService` before the send loop.

## Models

| Model | Holds |
|---|---|
| `Commentator`, `Tracker` | crew signups; `approved` bool, `acknowledged_at` timestamp |
| `MatchAcknowledgment` | per-player acknowledgment state per match |
| `MatchWatcher` | user × match watch subscriptions |

Field-level detail: [reference/data-model.md](../reference/data-model.md).
