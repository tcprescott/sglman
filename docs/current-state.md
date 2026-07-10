# SGLMan — Current Project State

_Last updated: 2026-06-25_

## What Is This

SGLMan (Speedgaming Live Manager) manages tournament schedules, matches, users, and crew for speedgaming live events. It runs as a single Docker container: FastAPI backend + NiceGUI frontend + Discord bot, backed by PostgreSQL.

This document is the living status snapshot. For the full documentation set — architecture, development/deployment guides, and method-level code reference — start at the [documentation index](README.md).

## Running Status

The application is functional and in active use. All features listed below are merged to `main`. The three-layer refactor (Presentation → Service → Repository) is complete.

## Feature Status

| Feature | Status | PR(s) | Notes |
|---|---|---|---|
| Match scheduling & lifecycle | Stable | pre-Claude | Core feature; state machine via timestamps |
| Discord OAuth login | Stable | pre-Claude | Via `middleware/auth.py`; mock mode available |
| Role-based authorization | Stable | #8 | Replaced single-permission gate with `Role` enum |
| Discord match notifications (DM) | Stable | #3, #4 | Match lifecycle events sent to players/watchers |
| Match watcher (subscribe to match) | Stable | #9 | Users can watch any match for Discord DM updates |
| Match acknowledgment (Discord DM) | Stable | #10 | Players acknowledge match via DM buttons |
| Tournament notification preferences | Stable | #4 | Per-user/tournament subscription levels |
| Discord crew signup (DM buttons) | Stable | #4 | Commentator/Tracker signup via Discord DM |
| Crew match acknowledgment | Stable | #12 | Crew confirms match via web UI; approval flow |
| Admin reports (multi-report) | Stable | #6 | Crew hours, match CSV, audit log viewer |
| Audit logging | Stable | #11 | Covers all major create/update/delete actions |
| Triforce texts | Stable | #14 | Per-tournament player submission + admin moderation |
| Mock Discord (dev mode) | Stable | #5 | `MOCK_DISCORD=true` bypasses OAuth; stub all Discord calls |
| CSV export (injection-safe) | Stable | #7 | Formula prefixes escaped in all CSV outputs |
| PostgreSQL database | Stable | #15, #16 | Migrated from MySQL; runs in Docker via compose |
| GitHub Actions / GHCR publish | Stable | #16 | CI publishes container image on push to main |
| Test suite | Partial | #2, #13 | Unit tests for timezone utils, match service, API; not complete coverage |
| Icon-only button tooltips | Stable | #32 | All icon-only buttons now have `.tooltip()` |
| Required-field markers + validation | Stable | #33 | Forms mark required fields and validate before submit |
| Triforce delete confirmation | Stable | #31 | `ConfirmationDialog` gates admin triforce-text deletion |
| Station assignment display | Stable | direct | Admin schedule shows assigned stations per player |
| Timezone consistency | Stable | #30 | All user-table and report timestamps use Eastern |
| Discord role sync | Stable | recent | Map Discord guild roles → app roles at login ([discord-role-sync.md](features/discord-role-sync.md)) |
| Personal API tokens + REST API | Stable | recent | Bearer-token auth, full read/write routers under `api/` ([rest-api.md](reference/rest-api.md)) |
| In-app feedback | Stable | recent | Logged-in users submit feedback; staff review on admin Feedback tab |
| Player availability | Stable | recent | Self-service availability windows; feed match-time suggestions |
| Volunteer scheduling | Stable | recent | Opt-in, positions, shifts, assignments, availability, auto-scheduler, reminders ([data-model.md](reference/data-model.md), [services.md](reference/services.md)) |
| Equipment lending | Stable | recent | Assets, checkout/check-in, loan history, QR codes; `EQUIPMENT_MANAGER` role |
| Challonge integration | Stable | recent | Service-account OAuth, bracket mirroring, scheduling, per-player identity linking |
| Security headers | Stable | #38 | `middleware/security_headers.py` ([deployment.md](deployment.md)) |
| Event bus + webhooks | Stable | recent | Central in-process event bus (`application/events/`) + staff-managed signed outbound webhooks ([event-system.md](features/event-system.md), [webhooks.md](features/webhooks.md)) |
| Device notifications (web push) | New | recent | Declarative Web Push (iOS/Android/desktop) mirroring every Discord DM to subscribed devices; off until VAPID keys are set ([web-push.md](features/web-push.md)) |
| Engagement telemetry | New | recent | Append-only `TelemetryEvent` capturing page views, curated interactions, and a mirror of every domain event; Staff-only engagement report; `TELEMETRY_ENABLED` kill-switch ([telemetry.md](features/telemetry.md)) |

The four reference docs ([data-model.md](reference/data-model.md), [services.md](reference/services.md), [rest-api.md](reference/rest-api.md), [frontend.md](reference/frontend.md)) carry the method-level detail for the newer subsystems; dedicated feature docs for volunteering, equipment, and Challonge are not yet written.

## Known Open Issues

The UX audit findings (tooltips, required-field validation, delete confirmations, timezone consistency) have all been addressed by PRs #30–#33. No known issues currently block core workflows; remaining polish items are tracked as GitHub issues.

**Notification centralization — Phase 2 (not started):** the event bus is currently *additive* — services publish domain events for webhooks, but the existing Discord DM fan-out still runs directly through `discord_queue`. A future phase could migrate the Discord notifications to be event-bus subscribers so a single `event_bus.publish` drives all channels. This is deferred because the DM fan-out is deeply audience-specific (players/crew/watchers/subscribers with different button variants). See [event-system.md](features/event-system.md).

## Architecture Summary

```
pages/ + theme/         ← NiceGUI UI (Quasar components)
  ↓ calls
application/services/   ← business logic, validation, audit, Discord notifications
  ↓ calls
application/repositories/ ← ORM queries (Tortoise)
  ↓ uses
models.py               ← Tortoise models (36) + enums (9: Role, RoleSource, MatchNotificationLevel, …)
```

All datetimes stored UTC; all user-facing times in US/Eastern. See [timezone-handling.md](timezone-handling.md).

Full architecture (startup sequence, component diagram, directory map): [architecture.md](architecture.md). Layer-by-layer code reference: [reference/](README.md#code-reference-docsreference).

## Key Files at a Glance

Method-level detail for every file below lives in the [code reference docs](README.md#code-reference-docsreference).

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, DB init, lifespan, Discord bot startup |
| `api/` | REST routers, Pydantic schemas, token auth, rate limiting under `/api` |
| `frontend.py` | Registers NiceGUI pages |
| `models.py` | All Tortoise ORM models + enums |
| `middleware/auth.py` | Discord OAuth; `@protected_page` decorator; mock mode |
| `application/services/auth_service.py` | `AuthService` — role checks, `can_crud_match`, etc. |
| `application/services/match_service.py` | Match CRUD, lifecycle transitions |
| `application/services/match_schedule_service.py` | Scheduling logic + Discord notification fan-out |
| `application/services/discord_service.py` | All Discord DM and interaction logic |
| `application/services/audit_service.py` | `AuditService` + `AuditActions` constants |
| `discordbot/crew_signup.py` | Discord button handler for crew DM signup |
| `discordbot/match_acknowledgment.py` | Discord button handler for match acknowledgment |
| `discordbot/watch_buttons.py` | Discord button handler for match watch |
| `pages/home.py` | Homepage (Schedule / On Air / Profile / Player tabs; logged-in users also get My Availability / Triforce Texts / Equipment) |
| `pages/admin.py` | Admin dashboard (Schedule, Users, Tournaments, Stream Rooms, Triforce Texts, Volunteers, Reports, Challonge, Discord Roles, Equipment, Feedback, Settings); tabs shown per role |
| `pages/volunteer.py` | Volunteer hub (availability / my shifts for volunteers; Schedule race workflow for proctors/staff) |
| `pages/equipment.py` | Equipment asset detail (QR, loan history, checkout/check-in) |
| `pages/home_tabs/triforce_texts.py` | Player triforce text submission (home tab) |

## Environment Variables

The authoritative environment-variable table lives in **[deployment.md](deployment.md)** (kept in sync with `application/utils/environment.py`). It is not duplicated here — a second copy only drifts.

## Running Locally

```bash
poetry install
cp .env.example .env      # fill in credentials, or set MOCK_DISCORD=true
./start.sh dev            # port 8000 with auto-reload
```

## Testing

```bash
poetry run pytest         # runs all tests under tests/
```

Tests cover: timezone utilities, match state transitions, match service, API endpoints. Coverage is partial — happy paths for core flows only.
