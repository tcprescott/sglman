# SGLMan — Current Project State

_Last updated: 2026-07-10_

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
| Analytics & insights dashboard | New | recent | Reports → Insights: crew participation, volunteer hours, tournament health, and admin activity trended weekly/monthly across events (`AnalyticsService`, `pages/admin_tabs/reports/insights.py`) |
| Multitenancy | New | recent | Logical multitenancy: one DB, `tenant` FK on ~33 models, path-mode `/t/<slug>` addressing, request-time tenant context, explicit repo scoping, global users with per-tenant roles + global `SUPER_ADMIN`, `/platform` management surface, one Discord bot for many guilds. Additive migration backfills a `default` tenant preserving live data ([multitenancy.md](features/multitenancy.md)) |
| Online-tournament foundations (PR 0) | In progress | this PR | Shared plumbing for the [online-tournaments plan](online-tournaments/README.md): reserved system `User` (sentinel `discord_id` + `is_system`) via `UserService.get_system_user`; `PRESET_MANAGER`/`SYNC_ADMIN`/`QUALIFIER_ADMIN` roles + `AuthService.can_manage_presets`/`can_manage_sync`/`can_admin_qualifier`; hybrid-config substrate (`Tournament.config` + `validate_tournament_config` + `tournament_strategies/` registry). Plumbing only — concrete strategies/feature models land in later PRs |
| User-managed seed presets (PR 1) | In progress | this PR | Tenant-authored `Preset` rows (`randomizer` + `settings` JSON) replace hard-coded preset files as the source of seed settings: `PresetService` CRUD (gated by `PRESET_MANAGER`/STAFF) + import of the built-in `presets/` files, admin **Presets** tab, `Tournament.preset` FK (overrides legacy `seed_generator`), and `SeedGenerationService.generate_seed(randomizer, preset)` resolving ALTTPR settings from the preset. Non-ALTTPR backends stay hard-coded until PR 11 ([seed-rolling.md](online-tournaments/seed-rolling.md)) |
| Racetime identity linking (PR 2) | In progress | this PR | racetime.gg becomes the third verified-identity link on the global `User` (`racetime_user_id` unique + `racetime_username` + `racetime_linked_at`; identity only, token discarded). `RacetimeService` + one-time OAuth (`pages/racetime_oauth.py`), profile "racetime.gg" link/unlink card, and a `MOCK_RACETIME` identity mock (production-refused) mirror the Twitch flow. Bot connection / room lifecycle land in PR 3/4/6 ([pr-2-racetime-identity.md](online-tournaments/implementation/pr-2-racetime-identity.md)) |
| Racetime room lifecycle (PR 6) | In progress | this PR | The core online loop: from a scheduled `Match`, auto-create and drive a racetime room through finish/cancel, attaching the seed and capturing results. `RaceRoomService` (the business layer the auto-open worker and the PR 4 handlers both call) maps create → open (+ seed attach via `MatchScheduleService`) → in-progress (`started_at`) → finish (map racetime entrants → linked `User`, record `finish_rank` place + new `finish_time` seconds, close the match) → cancel, auditing + publishing a `race_room.*` event on each transition and acting as the system user. Terminal states (forfeit / no-show / DQ / one-finisher) map correctly; unmatched racetime handles are surfaced in the audit for staff reconcile; results feed the existing reporting path (Challonge push optional, non-Challonge tournaments still close). An opt-in auto-open worker (`racetime_auto_create_rooms` + `room_open_minutes_before`, eligibility = all entrants linked, idempotent, keep-room-on-reschedule) opens rooms ahead of scheduled matches; STAFF/`SYNC_ADMIN` can also create a room manually from the match dialog. Migration 25 adds `matchplayers.finish_time` ([pr-6-racetime-lifecycle.md](online-tournaments/implementation/pr-6-racetime-lifecycle.md)) |
| Racetime bot runtime (PR 4) | In progress | this PR | Runtime half of racetime room automation: a lifespan-managed `racetimebot/` package (peer of `discordbot/`) that opens one long-lived connection per active `RacetimeBot` category. Health is first-class state — the connection loop writes `RacetimeBot.status`: connect → `connected` (+`last_connected_at`); auth rejection → `error` and stop retrying; transient failure → `error` then reconnect with exponential backoff capped at 5 min; a liveness heartbeat refreshes `last_checked_at`. Inbound room events route to the tenant via the unscoped `RacetimeRoom.slug` → tenant lookup wrapped in `tenant_scope`, acting as the system user; a crashing handler can't take down the bot or its siblings. On boot it re-adopts open rooms so a redeploy doesn't orphan them. Gated by `RACETIME_BOT_ENABLED` (off by default) and fully mockable via `MOCK_RACETIME` (a scripted event-emitting fake, production-refused). `/platform` gains per-bot health + a restart action ([pr-4-racetime-bot-runtime.md](online-tournaments/implementation/pr-4-racetime-bot-runtime.md)) |
| SpeedGaming schedule ETL (PR 7) | In progress | this PR | One-way SG → SGLMan schedule sync. The placeholder-user pattern lands on the global `User` (`discord_id` nullable+unique with a `CHECK (discord_id IS NOT NULL OR is_placeholder)`, plus `is_placeholder` + unique `speedgaming_id`): an unresolved SG player becomes a first-class placeholder `User`, upgraded in place when a `discord_id` later appears (resolution order `discord_id` → `discord_username` → placeholder-by-`speedgaming_id` → create). Tenant-scoped `SpeedGamingEventLink` (SG slug ↔ tournament + observability fields) and `SpeedGamingEpisode` (staging snapshot + content hash) models; `Match` gains its OneToOne source-marker FK to `SpeedGamingEpisode` (SET_NULL). `SpeedGamingETLService` ports sahabot2's extract/transform/load; the hybrid read-only contract is enforced two ways — `MatchService.update_match` rejects edits to ETL-owned fields on a sourced match (UI disables them with a "Synced from SpeedGaming" badge), and the sync lifecycle guards skip finished/manual/room-linked matches + auto-finish >4h past. A `SPEEDGAMING_SYNC_ENABLED` worker runs each active link on its cadence as the system user (`sg_sync.*` audit/events); `MOCK_SPEEDGAMING` drives a scripted fake. Admin **SpeedGaming** tab (SYNC_ADMIN) does event-link CRUD + "Sync now". Migration 26; leak tests ([pr-7-speedgaming-etl.md](online-tournaments/implementation/pr-7-speedgaming-etl.md)) |
| Discord Events sync (PR 8) | In progress | this PR | Mirrors the SGLMan schedule into each tenant guild's **Discord Scheduled Events** as idempotent reconciliation (create/update/cancel), not fire-and-forget. Tenant-scoped `DiscordScheduledEvent` link model (`discord_event_id` unique; polymorphic `source_type`/`source_id` via the `DiscordEventSource` enum — today `MATCH`; unique `(tenant, source_type, source_id)`; `content_hash` drives update-vs-noop). Per-tournament opt-in columns on `Tournament` (`discord_events_enabled`, `discord_event_duration_minutes`, nullable title/description templates with `{tournament}`/`{match}`/`{players}`). **Shared-guild safety is the sharp edge**: since `discord_guild_id` is not unique, the reconciler's working set is **only this tenant's own link rows** — the repository is tenant-scoped, so a sibling tenant's event in a shared guild is never enumerated and never cancelled; the target guild is the verified `Tenant.discord_guild_id`. `DiscordEventReconcilerService` + `DiscordService` scheduled-event methods (mock-backed under `MOCK_DISCORD`); a `DISCORD_EVENTS_SYNC_ENABLED` worker reconciles every linked tenant on a cadence as the system user (`discord_event.*` audit/events). Admin **Discord Events** tab (SYNC_ADMIN): per-tournament opt-in + "Sync now" + mirrored-events observability. Migration 27; shared-guild isolation regression test ([pr-8-discord-events.md](online-tournaments/implementation/pr-8-discord-events.md)) |
| Platform service-health board (PR 5) | In progress | this PR | A SUPER_ADMIN `/platform` board showing the live health of every external dependency (PostgreSQL, Discord bot + OAuth, racetime bots, SpeedGaming feed, Challonge reachability **and** token expiry, Twitch OAuth, seed-gen upstreams alttpr/ootrandomizer/maprando, web-push/VAPID, Sentry), so an admin learns something is down before it breaks a race day. **Computed-and-cached, no persistence model**: `ServiceHealthService` holds an async probe registry + an in-memory result cache; a `SERVICE_HEALTH_ENABLED` worker refreshes on a cadence and the board force-refreshes on demand. Status model `healthy / degraded / down / unknown` plus a distinct **credential-warning** signal (expiring Challonge token, racetime auth error). A transition into down / credential-warning publishes a platform-level `service_health.alert` event, captures to Sentry, and — under `SERVICE_HEALTH_ALERT_DM` — DMs super-admins. Tenant STAFF get a **read-only subset** admin tab (their authorized racetime bots + their own Challonge connection) via `tenant_subset()`. Challonge token expiry read across tenants through an explicitly-unscoped repo method; no schema change/migration ([pr-5-service-health.md](online-tournaments/implementation/pr-5-service-health.md)) |
| Async Qualifiers (PR 9) | In progress | this PR | Self-paced permalink-pool qualifiers — a **peer aggregate of `Tournament`**, web-first, with its own state machine (window opens → draw → run → review → scored leaderboard → close) entirely outside the Match/schedule system. Five tenant-scoped models (`AsyncQualifier` with typed window columns + `runs_per_pool`/`allowed_reattempts` + validated-JSON `config` + `admins` M2M; `AsyncQualifierPool` with optional `Preset` FK; `AsyncQualifierPermalink` with maintained `par_time` + `live_race` flag; `AsyncQualifierRun` with run/review status enums, timing, VoD, `reattempted`/`reattempt_reason`, `score`, reviewer claim-lock; `AsyncQualifierReviewNote`). `AsyncQualifierService` owns the rules: an **atomic locked draw** (one active run/player, `runs_per_pool` cap, permalink no-repeat, imbalance-forcing fairness) revealing a spoiler-safe permalink only at start; submit/forfeit(irreversible, 0)/reattempt(voids + frees slot, limited); reviewer queue = the `admins` M2M with **self-review blocked** + claim-locking; par (mean of N fastest approved) + score (`clamp(0,105,(2−elapsed/par)·100)`) + slot leaderboard; and the **active-window information lockdown** (board/pools/pars staff-only until the qualifier closes). Admin **Qualifiers** tab (QUALIFIER_ADMIN) authors pools/permalinks (paste or roll-N from a preset) + works the reviewer queue; player pages (`/qualifiers`, `/qualifiers/{id}`) draw + time + submit + view the leaderboard. `async_qualifier.*` audit; `run_submitted`/`run_reviewed` events; DM on review. Migration 28; scoring + service + leak tests ([pr-9-async-qualifiers.md](online-tournaments/implementation/pr-9-async-qualifiers.md)) |
| Async Qualifier live races (PR 10) | In progress | this PR | Synchronous racetime races for a qualifier pool, **reusing the PR 4/6 racetime subsystem** (not a second integration). New tenant-scoped `AsyncQualifierLiveRace` model (FKs → `pool` CASCADE, nullable `permalink`/`episode` SET_NULL; `match_title`; globally-unique nullable `racetime_slug` mirroring the room slug; `AsyncQualifierLiveRaceStatus` scheduled→pending→in_progress→finished) plus the deferred `AsyncQualifierRun.live_race` FK. `AsyncQualifierLiveRaceService` authors a race, `open_room` opens a `RacetimeRoom` (`match=None`) via one of the tenant's authorized bots and mirrors its slug, and `record_finish` maps each racetime entrant to a `User` and captures an `AsyncQualifierRun` (done→finished/dnf→forfeit/dq→disqualified; `finish_time`→elapsed) then par-scores. **Decision: live-race runs skip reviewer sign-off** (written `APPROVED` — the racetime result is self-attributing); **recording is refused while any entrant is still racing**. `RaceRoomLifecycle` routes a room with no match to this capture path by slug. Admin **Live Races** sub-tab (create + open room). `async_qualifier.live_race_*` audit; `live_race_recorded` event. Migration 29; leak + service + lifecycle-routing tests ([pr-10-qualifier-live-races.md](online-tournaments/implementation/pr-10-qualifier-live-races.md)) |
| Racetime bots + rooms (PR 3) | In progress | this PR | Data + admin half of racetime room automation (no live websocket — that is PR 4). Global platform-managed `RacetimeBot` per game category (OAuth creds as DB rows, secret write-only + `BotStatus` health fields), `RacetimeBotTenant` SUPER_ADMIN authorization grants, tenant-scoped `RaceRoomProfile` reusable room settings, and a `RacetimeRoom` record (globally-unique slug for unscoped tenant routing, O2O→`Match`). `Tournament` gains racetime config columns (`racetime_bot`, `race_room_profile`, auto-create/lead-time/require-link/goal). `/platform` bot CRUD + tenant assignment; admin **Racetime** tab (`RaceRoomProfile` CRUD, SYNC_ADMIN); tournament dialog Racetime section. Leak tests cover grants/profiles/rooms ([pr-3-racetime-bots.md](online-tournaments/implementation/pr-3-racetime-bots.md)) |
| Online-tournament REST API | In progress | this PR | Full read + write REST parity for every online-tournament feature (presets, race-room profiles, racetime bots, race rooms, SpeedGaming ETL, Discord events, service health, seeds, async qualifiers + live races): ten new routers under `api/` (80 endpoints) as a thin layer over the existing services, so the same `AuthService` gate the web UI uses applies. Adds two global-scope auth deps (`require_super_admin`/`require_super_admin_write`) for the platform resources (RacetimeBot, service-health board); tenant-role groups use the coarse actor dep and let the service gate the finer `PRESET_MANAGER`/`SYNC_ADMIN`/`QUALIFIER_ADMIN` role. RacetimeBot responses use the secret-free `serialize()` projection; `race-rooms/open` filters the deliberately-unscoped open-rooms list to the caller's tenant. One `test_api_<resource>.py` per group ([rest-api.md](reference/rest-api.md#online-tournament-features), [online-tournaments/rest-api-coverage.md](online-tournaments/rest-api-coverage.md)) |

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
models.py               ← Tortoise models (43) + enums (11: Role, RoleSource, MatchNotificationLevel, …)
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
