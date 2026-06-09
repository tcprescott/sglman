# Feature: Crew Management

_Added: PR #4 (Discord crew signup), PR #12 (crew acknowledgment) | Status: Stable_

## What It Does

Manages Commentators and Trackers (collectively "crew") for matches. Crew can sign up via the website or via Discord DM buttons. Signups require admin approval.

## Signup Flows

### Web Signup
1. Crew member opens the admin dashboard or home page, finds a match.
2. Clicks "Sign up as Commentator" / "Sign up as Tracker".
3. `CrewService.signup_crew()` inserts a `Commentator` or `Tracker` row with `approved=False`.
4. Admin approves in the match dialog.

### Discord DM Signup (PR #4)
When a match is flagged as a stream candidate, `DiscordService.send_dm_with_crew_buttons()` sends a DM to subscribed users containing interactive "Sign up as Commentator" / "Sign up as Tracker" buttons. Clicking invokes `discordbot/crew_signup.py:on_interaction()`, which calls `CrewService.signup_crew()`.

## Crew Acknowledgment (PR #12)

After admin approval, crew members must acknowledge the match:
- Via web UI: a prompt appears in their "My Crew Assignments" view.
- Via Discord DM: an acknowledgment button is sent by `discordbot/crew_acknowledgment.py`.

## Key Files

| File | Role |
|---|---|
| `models.py` → `Commentator`, `Tracker` | Crew signup rows; `approved` bool, `acknowledged` bool |
| `application/services/crew_service.py` | `CrewService` — signup, approve, reject, acknowledge, undo |
| `discordbot/crew_signup.py` | Discord button handler for DM-based signup |
| `discordbot/crew_acknowledgment.py` | Discord button handler for crew acknowledgment |
| `theme/dialog/approve_crew_dialog.py` | Admin approval dialog |
| `theme/dialog/match_dialog.py` | Shows pending/approved crew per match |

## Approval API

```python
from application.services.crew_service import CrewService

await CrewService.signup_crew(user, match, role='commentator')
await CrewService.approve_crew(commentator_or_tracker_id, actor)
await CrewService.reject_crew(commentator_or_tracker_id, actor)
await CrewService.acknowledge_crew(commentator_or_tracker_id)
await CrewService.undo_signup(commentator_or_tracker_id, actor)
```

## Filtering

The API endpoint for crew returns only `approved=True` entries. This is enforced via a Pydantic validator (added directly on `main` after the refactor: "Filter approved-only crew via Pydantic validator").

## Audit Trail

All approve/reject/signup/undo actions write to `AuditLog` via `AuditActions.CREW_APPROVED` etc.
