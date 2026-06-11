# Service Layer Reference

_Method-level reference for `application/services/` (all 16 modules) and `application/utils/`. Part of the [documentation index](../README.md)._

## Pattern & conventions

Services are the business-logic layer of the [three-layer architecture](../refactoring-guide.md): pages and dialogs call services, services call repositories, repositories touch the ORM. The rules below are codebase-wide; see [CLAUDE.md](../../CLAUDE.md) for the full convention list.

- **Services own business rules.** Validation, permission gates, cross-entity coordination, audit logging, and Discord notification fan-out all live here. Repositories (see [data-model.md](data-model.md)) stay free of business logic; UI stays free of writes.
- **No NiceGUI imports.** Services never render or notify the UI. (The one deliberate exception: `auth_service.current_user_from_storage` reads `nicegui.app.storage` because resolving the session user is its entire job.)
- **`ValueError` for user-facing errors.** Validation failures ("Match must have at least one player", "Tournament not found") raise `ValueError`; the UI catches it and shows `ui.notify(str(e), color='warning')`.
- **`PermissionError` for authorization failures.** Permission gates run through `AuthService.ensure(allowed, message)`, which raises `PermissionError`. UI handlers that gate-protected services catch both (see `pages/admin_tabs/admin_schedule.py`).
- **Audit logging** uses `AuditService.write_log(actor, action, details)` with `verb.object` action constants from `AuditActions`. The actor is required — `write_log` raises `ValueError` when actor is `None`. See [audit-logging.md](../features/audit-logging.md) and the [CLAUDE.md conventions](../../CLAUDE.md).
- **The `actor` parameter.** Mutating methods take the acting `User` as a trailing `actor` parameter (or `user` when the action is inherently self-service, e.g. `acknowledge_match`, `signup_crew`, `watch`). The same object feeds both the permission gate and the audit entry; callers resolve it once via `current_user_from_storage()`.
- **Stateless instances.** Services hold only repository/service references; instantiate per request (`MatchService()`) or call static methods on the class (`AuthService`, `SystemConfigService`). The two intentional pieces of module/class state are `MatchScheduleService._seed_locks` (per-match seed-generation locks) and the `discord_queue` module's queue/worker.
- **`(ok, message)` tuple returns** are the exception, not the rule, and exist only where failure is routine and must not raise:
  - `DiscordService.send_dm*`, `add_role_to_user`, `remove_role_from_user` → `(bool, str)`
  - `DiscordService.list_guilds`, `list_guild_roles` → `(bool, data_or_error)`
  - `MatchScheduleService.generate_seed` → `(bool, message, seed_url | None)`

  Everything else returns models/values and raises on failure.
- **Fire-and-forget Discord work** is wrapped in a coroutine and handed to `discord_queue.enqueue(...)` rather than awaited inline, so DB transactions never block on Discord rate limits.

## Service catalog

| Service | Module | Responsibility | Feature doc |
|---|---|---|---|
| `AuditService` / `AuditActions` | [audit_service.py](../../application/services/audit_service.py) | Write and query the audit trail | [audit-logging.md](../features/audit-logging.md) |
| `AuthService` / `current_user_from_storage` | [auth_service.py](../../application/services/auth_service.py) | Role checks and permission policy | [authentication.md](authentication.md), [role-based-auth.md](../features/role-based-auth.md) |
| `CrewService` | [crew_service.py](../../application/services/crew_service.py) | Crew approval and acknowledgment | [crew-management.md](../features/crew-management.md) |
| `DiscordRoleMappingService` | [discord_role_mapping_service.py](../../application/services/discord_role_mapping_service.py) | Discord-role→app-role mapping CRUD and login-time role sync | [discord-role-sync.md](../features/discord-role-sync.md) |
| `discord_queue` (module) | [discord_queue.py](../../application/services/discord_queue.py) | Serialized background Discord sends | [discord-integration.md](discord-integration.md) |
| `DiscordService` / `MockDiscordService` | [discord_service.py](../../application/services/discord_service.py) | Bot DMs, button views, guild roles | [discord-integration.md](discord-integration.md) |
| `MatchScheduleService` | [match_schedule_service.py](../../application/services/match_schedule_service.py) | Match lifecycle transitions, seed rolls, DM fan-out | [discord-notifications.md](../features/discord-notifications.md) |
| `MatchService` | [match_service.py](../../application/services/match_service.py) | Match CRUD, display formatting, crew signup, acknowledgments | [match-acknowledgment.md](../features/match-acknowledgment.md) |
| `MatchWatcherService` | [match_watcher_service.py](../../application/services/match_watcher_service.py) | Watch/unwatch matches for DM updates | [match-watcher.md](../features/match-watcher.md) |
| `ReportsService` | [reports_service.py](../../application/services/reports_service.py) | Capacity, operations, crew, and stage reports | [admin-reports.md](../features/admin-reports.md) |
| `SeedGenerationService` | [seedgen_service.py](../../application/services/seedgen_service.py) | Randomizer seed generation | [seed-generation.md](seed-generation.md) |
| `StreamRoomService` | [stream_room_service.py](../../application/services/stream_room_service.py) | Stream room (stage) CRUD | — |
| `SystemConfigService` | [system_config_service.py](../../application/services/system_config_service.py) | Typed access to `SystemConfiguration` keys | [admin-reports.md](../features/admin-reports.md) |
| `TournamentNotificationService` | [tournament_notification_service.py](../../application/services/tournament_notification_service.py) | Per-tournament notification preferences | [tournament-notifications.md](../features/tournament-notifications.md) |
| `TournamentService` | [tournament_service.py](../../application/services/tournament_service.py) | Tournament CRUD, TA/CC membership | — |
| `TriforceTextService` | [triforce_text_service.py](../../application/services/triforce_text_service.py) | Triforce text submission and moderation | [triforce-texts.md](../features/triforce-texts.md) |
| `UserService` | [user_service.py](../../application/services/user_service.py) | User CRUD, profiles, roles, enrollments | [role-based-auth.md](../features/role-based-auth.md) |

All classes and `current_user_from_storage` are re-exported from [`application/services/__init__.py`](../../application/services/__init__.py); `discord_queue` is imported as a module (`from application.services import discord_queue`).

### audit_service.py — AuditService

Writes and queries `AuditLog` rows. Every mutating service action records who did what, with JSON-encoded details. Canonical doc: [audit-logging.md](../features/audit-logging.md).

**`AuditActions`** is a plain constants class holding every namespaced `verb.object` action string used in the codebase — one place to grep when reviewing audit coverage. Namespaces covered: `match.*` (lifecycle, CRUD, stage/station assignment, stream-candidate flag, watchers, seed rolls), `crew.*` (signups, approval, acknowledgment), `tournament.*` (CRUD, TA/CC grants), `user.*` (CRUD, profile edits, activation, roles, enrollments), `stream_room.*` (CRUD), `system_config.*` (updates), and `triforce_text.*` (submission/moderation lifecycle). Add a new constant here when introducing a new action; never pass literal strings.

| Method | Returns | Description |
|---|---|---|
| `write_log(actor, action, details=None)` | `AuditLog` | Create an entry; JSON-encodes `details` (non-serializable values fall back to `str`). Raises `ValueError` if `actor` is `None`. |
| `list_logs(*, start=None, end=None, user_id=None, action_contains=None, limit=100, offset=0)` | `list[AuditLog]` | Filtered, paginated log listing (delegates to `AuditRepository`). |
| `count_logs(*, start=None, end=None, user_id=None, action_contains=None)` | `int` | Count matching the same filters as `list_logs`. |
| `get_logs_for_user(user, limit=None)` | `list[AuditLog]` | A user's entries, most recent first. |
| `get_recent_logs(limit=100)` | `list[AuditLog]` | Most recent entries across all users, with `user` prefetched. |

Collaborators: `AuditRepository`. Consumers: every mutating service (writer side); the audit log viewer at `pages/admin_tabs/reports/audit.py` (reader side).

### auth_service.py — AuthService and current_user_from_storage

Stateless authorization policy: every check is a `@staticmethod` taking `User | None` and returning a bool (no exceptions for "not allowed" — that is `ensure`'s job). Deep dive: [authentication.md](authentication.md); role semantics: [role-based-auth.md](../features/role-based-auth.md).

| Method | Returns | Description |
|---|---|---|
| `get_roles(user)` | `set[Role]` | All global roles held by the user (empty for `None`). |
| `has_role(user, role)` | `bool` | Whether the user holds a specific global `Role`. |
| `is_staff(user)` | `bool` | Holds `Role.STAFF`. |
| `is_proctor(user)` | `bool` | Holds `Role.PROCTOR`. |
| `is_stream_manager(user)` | `bool` | Holds `Role.STREAM_MANAGER`. |
| `is_tournament_admin(user, tournament_id)` | `bool` | Listed in `Tournament.admins`. |
| `is_crew_coordinator_of(user, tournament_id)` | `bool` | Listed in `Tournament.crew_coordinators`. |
| `can_view_admin(user)` | `bool` | Any global role, or TA/CC of any tournament. |
| `can_edit_tournament(user, tournament)` | `bool` | Staff, or TA of that tournament. |
| `can_crud_match(user, match)` | `bool` | Staff, or TA of the match's tournament. |
| `can_transition_match(user, match)` | `bool` | Staff, Proctor, or TA — gates seat/start/finish/confirm, seed rolls, station assignment. |
| `can_approve_crew(user, match)` | `bool` | Staff, TA, or CC of the match's tournament. |
| `can_manage_stream_rooms(user)` | `bool` | Staff or Stream Manager — gates StreamRoom CRUD. |
| `can_assign_match_stream(user, match)` | `bool` | Stream Manager globally, or TA of the match's tournament — gates stage assignment and the stream-candidate flag. |
| `can_grant_roles(user)` | `bool` | Staff only — gates role grants and TA/CC membership changes. |
| `ensure(allowed, message="Permission denied")` | `None` | Raises `PermissionError(message)` when `allowed` is falsy; the standard gate inside mutating services. |

**Module-level helper:** `current_user_from_storage() -> User | None` resolves the session's `discord_id` from `app.storage.user` to a `User` model (or `None` when logged out / deleted). Call it once at page entry and pass the result into the helpers above — don't re-resolve per check.

Consumers: `middleware/auth.py` (`protected_page` role enforcement), nearly every page and dialog (`pages/home.py`, `pages/admin.py`, `pages/admin_tabs/*`, `theme/dialog/*`, `theme/tables/*`), and all mutating services via `ensure`.

### crew_service.py — CrewService

Crew (commentator/tracker) approval workflow and crew-side acknowledgment. Signup itself lives on `MatchService.signup_crew`. Feature doc: [crew-management.md](../features/crew-management.md).

| Method | Returns | Description |
|---|---|---|
| `get_crew_member_by_id(crew_id, crew_type)` | `Commentator \| Tracker \| None` | Fetch by row id; `crew_type` must be `'commentator'` or `'tracker'` (else `ValueError`). |
| `update_crew_approval(crew_member, crew_type, approved, actor=None)` | `Commentator \| Tracker` | Approve/unapprove. Gated by `can_approve_crew`; refreshes from DB to narrow approval races; no-ops (no audit, no DM) when state already matches; unapproval clears `acknowledged_at`; approval enqueues an acknowledgment-request DM. |
| `approve_crew_member(crew_member, crew_type, actor=None)` | `Commentator \| Tracker` | Convenience wrapper for `update_crew_approval(..., approved=True)`. |
| `acknowledge_crew_assignment(crew_id, crew_type, user)` | `Commentator \| Tracker` | Crew member confirms their own approved assignment. Rejects other users and unapproved rows (`ValueError`); already-acknowledged rows are a silent no-op. |

Collaborators: `CommentatorRepository`, `TrackerRepository`, `AuditService`, `DiscordService` (via `discord_queue`). Consumers: `theme/dialog/approve_crew_dialog.py`, `theme/tables/match.py` (web acknowledge button), `discordbot/crew_acknowledgment.py` (DM button handler).

### discord_role_mapping_service.py — DiscordRoleMappingService

CRUD for `DiscordRoleMapping` plus the login-time sync that maps a user's Discord guild roles onto application roles. Feature doc: [discord-role-sync.md](../features/discord-role-sync.md).

| Method | Returns | Description |
|---|---|---|
| `list_all_mappings()` / `list_mappings(guild_id)` | `List[DiscordRoleMapping]` | All mappings, or those scoped to one guild. |
| `add_mapping(guild_id, discord_role_id, discord_role_name, app_role, actor)` | `DiscordRoleMapping` | Staff-only; rejects exact duplicates (`ValueError`); audits `discord_role.mapping_added`. |
| `remove_mapping(mapping_id, actor)` | `None` | Staff-only; `ValueError` if missing; audits `discord_role.mapping_removed`. |
| `sync_user_roles(user)` | `dict` | Full-syncs the user's Discord-sourced roles. **Never raises** — fails open on any error so login is never blocked. Grants mapped roles the user lacks (`source=discord`), revokes Discord-sourced roles no longer present, and never touches `source=manual` rows. Returns a `{'granted', 'revoked', 'skipped'}` summary. |

Collaborators: `DiscordRoleMappingRepository`, `UserRoleRepository`, `DiscordService.get_member_role_ids`, `SystemConfigService.get_discord_sync_guild_id`, `AuthService`, `AuditService`. Consumers: `middleware/auth.py` (OAuth callback calls `sync_user_roles`), `pages/admin_tabs/admin_discord_roles.py` (mapping management UI).

### discord_queue.py — module functions

Single-worker async queue that serializes all outbound Discord work. Producers call `enqueue(coro)` from anywhere; one worker task awaits queued coroutines in FIFO order, so DM bursts cannot stampede the Discord API and callers never block on sends. Worker exceptions are printed and swallowed — an individual failed DM never kills the worker. Deep dive: [discord-integration.md](discord-integration.md).

| Function | Returns | Description |
|---|---|---|
| `start()` | `None` | Create the worker task on the running event loop. Called once from `main.py` lifespan startup. |
| `stop()` (async) | `None` | Cancel the worker and await its exit; warns if items are still queued (they are dropped). Called from lifespan shutdown. |
| `enqueue(coro)` | `None` | Put a coroutine on the queue without awaiting it (`put_nowait`). |

Producers: `MatchService`, `MatchScheduleService`, `CrewService`. Tests stub `enqueue` (see [Testing](#testing-the-service-layer)).

### discord_service.py — DiscordService, MockDiscordService, get_discord_bot

Thin wrapper around the shared discord.py bot: DM sending (plain and with interactive button views), guild/role management. All methods return tuples instead of raising, since Discord failures (DMs disabled, user missing, bot not ready) are routine. Deep dive: [discord-integration.md](discord-integration.md).

**Module-level:** `get_discord_bot() -> commands.Bot` lazily creates the singleton bot with the required intents and registers the `on_interaction` dispatcher that routes button `custom_id` prefixes (`crew_signup:`, `match_ack:`, `crew_ack:`, `match_watch:`) to the handlers in `discordbot/`.

| Method | Returns | Description |
|---|---|---|
| `send_dm(user_id, message)` | `(bool, str)` | Plain DM to a Discord user id. |
| `send_dm_with_crew_buttons(user_id, message, match_id)` | `(bool, str)` | DM with commentator/tracker signup buttons. |
| `send_dm_with_acknowledgment_button(user_id, message, match_id)` | `(bool, str)` | DM with a match Acknowledge button. |
| `send_dm_with_crew_acknowledgment_button(user_id, message, crew_type, crew_id)` | `(bool, str)` | DM with a crew-assignment Acknowledge button. |
| `send_dm_with_unwatch_button(user_id, message, match_id)` | `(bool, str)` | DM with an Unwatch button for match watchers. |
| `get_bot()` | `commands.Bot \| None` | The underlying bot instance. |
| `list_guilds()` | `(bool, list[{id, name}] \| str)` | Guilds the bot is connected to. |
| `list_guild_roles(guild_id)` | `(bool, list[{id, name}] \| str)` | All roles in a guild (fetch with cached fallback). |
| `add_role_to_user(guild_id, user_id, role_id, reason=None)` | `(bool, str)` | Grant a Discord role to a guild member. |
| `remove_role_from_user(guild_id, user_id, role_id, reason=None)` | `(bool, str)` | Remove a Discord role from a guild member. |

**`MockDiscordService`** mirrors the full public surface, printing to stdout and returning success tuples. When [`MOCK_DISCORD`](../features/mock-discord.md) is enabled, the module rebinds the name `DiscordService = MockDiscordService` at import time, so all callers get the stub transparently.

Consumers: `MatchScheduleService` and `CrewService` (notification fan-out), `theme/dialog/send_message_dialog.py` (admin "send DM" dialog).

### match_schedule_service.py — MatchScheduleService

Match lifecycle transitions (seat → start → finish → confirm), seed rolling, and all Discord DM fan-out for match events. Every transition is gated by `AuthService.can_transition_match`, validates ordering (e.g. "Match must be checked in before starting" as `ValueError`), stamps the timestamp, writes the matching `match.*` audit action, and enqueues a participant DM. Feature docs: [discord-notifications.md](../features/discord-notifications.md), [match-acknowledgment.md](../features/match-acknowledgment.md), [match-watcher.md](../features/match-watcher.md).

| Method | Returns | Description |
|---|---|---|
| `seat_match(match, actor=None)` | `None` | Set `seated_at` (rejects double check-in); audits `match.seated`; DMs participants. |
| `start_match(match, actor=None)` | `None` | Set `started_at` (requires seated, rejects restart); audits `match.started`; DMs participants. |
| `finish_match(match, actor=None)` | `None` | Set `finished_at` (requires started, rejects re-finish); audits `match.finished`; DMs participants. |
| `confirm_match(match, actor=None)` | `None` | Set `confirmed_at` (requires finished, rejects re-confirm); audits `match.confirmed`; DMs participants. |
| `generate_seed(match_id, actor=None)` | `(bool, str, str \| None)` | Roll a seed via `SeedGenerationService` using the tournament's `seed_generator` preset. Per-match `asyncio.Lock` (class-level `_seed_locks` dict) rejects concurrent rolls; also fails softly when a seed already exists, no generator is configured, the generator is unknown, or permission is denied. On success creates the `GeneratedSeeds` row, audits `match.seed_rolled`, and enqueues seed DMs to opted-in players. Exceptions are caught and returned as `(False, error, None)`. |
| `notify_match_participants(match, message)` | `None` | DM opted-in players, approved crew, and watchers — one DM per person; watchers get the Unwatch-button variant. Never raises; per-DM failures are printed. |
| `notify_match_crew(match, message)` | `None` | DM approved crew and watchers, excluding players (players get the acknowledgment DM instead). Never raises. |
| `notify_acknowledgment_request(match, *, rescheduled)` | `None` | DM each player whose acknowledgment is still pending with an Acknowledge button; message wording switches on `rescheduled`. Never raises. |
| `notify_tournament_subscribers_scheduled(match, message, exclude_discord_ids)` | `None` | DM tournament-notification subscribers (filtered by whether the match has a stream room) with crew signup buttons, skipping already-notified ids. Never raises. |
| `notify_stream_candidate_subscribers(match, exclude_discord_ids)` | `None` | DM stream-candidate subscribers with crew signup buttons. Skipped entirely when the match already has a stream room (those subscribers were already notified). Never raises. |

The `notify_*` methods are designed to run **inside** the `discord_queue` worker: callers enqueue them rather than awaiting. All DM recipients are filtered by `User.dm_notifications` and the presence of a `discord_id`.

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentNotificationRepository`, `DiscordService`, `SeedGenerationService`, `AuditService`, `discord_queue`. Consumers: `pages/admin_tabs/admin_schedule.py` (seat/start/finish/confirm/seed buttons), `MatchService` (reuses the notify helpers and DM message builders).

### match_service.py — MatchService

The largest service: match CRUD with full notification fan-out, display formatting for the match tables, schedule queries, crew signup, station/stage assignment, results, and player acknowledgments.

| Method | Returns | Description |
|---|---|---|
| `get_match_for_display(match_id)` | `dict \| None` | One match formatted for the UI (state, Eastern-formatted times, players with rank/station, acknowledgment summary, crew with approval/ack state, seed URL). |
| `get_matches_for_display(*, tournament_ids=None, stream_room_ids=None, only_upcoming=False, user_discord_id=None)` | `list[dict]` | Filtered match list in the same display shape, with acknowledgments batch-loaded. |
| `get_tournaments_for_filter()` | `dict[int, str]` | Tournament id → name for filter dropdowns. |
| `get_stream_rooms_for_filter()` | `dict[int, str]` | Stream room id → name for filter dropdowns. |
| `get_all_matches_for_schedule()` | `list[Match]` | Every match with relations prefetched, ordered by `scheduled_at` (public schedule tab). |
| `get_matches_for_date(target_date, exclude_finished=True, require_stream_room=True)` | `list[Match]` | A day's matches with players/crew prefetched (stage timeline). |
| `group_matches_by_stream_room(matches)` | `dict[int, (StreamRoom, list[Match])]` | Group prefetched matches by stream room. |
| `get_matches_for_player(discord_id)` | `list[Match]` | Matches where the Discord user is a player. |
| `create_match(tournament_id, scheduled_date, scheduled_time, player_ids, comment=None, stream_room_id=None, commentator_ids=None, tracker_ids=None, is_stream_candidate=False, actor=None)` | `Match` | Admin match creation — see flow below. Staff or TA of the target tournament. |
| `update_match(match_id, *, tournament_id=None, scheduled_date=None, scheduled_time=None, player_ids=None, commentator_ids=None, tracker_ids=None, comment=None, clear_seated/clear_started/clear_finished/clear_confirmed/clear_seed=False, actor=None)` | `Match` | Partial update; syncs player/crew lists; can clear lifecycle timestamps and the seed; audits `match.updated`; re-runs acknowledgment + notification fan-out when the time or player set changed. Gated by `can_crud_match`. |
| `submit_match_request(tournament_id, scheduled_date, scheduled_time, player_ids, actor, comment=None)` | `Match` | Player-initiated creation: the actor must be one of the players (`PermissionError` otherwise) — bypasses the TA/Staff gate without granting other powers. Audits `match.requested` and runs the same acknowledgment/notification fan-out as `create_match`. |
| `set_stream_candidate(match_id, flag, actor=None)` | `Match` | Toggle `is_stream_candidate`; gated by `can_assign_match_stream`; notifies stream-candidate subscribers on a false→true transition. |
| `assign_stage(match_id, stream_room_id, actor=None)` | `Match` | Assign or clear (`None`) the match's stream room; gated by `can_assign_match_stream`; audits assigned/cleared variants. |
| `assign_stations(match_id, assignments, actor=None)` | `Match` | Set `MatchPlayers.assigned_station` from a `{match_player_id: station}` mapping; gated by `can_transition_match`. |
| `ensure_players_enrolled(tournament_id, player_ids)` | `None` | Enroll any of the given users not yet in the tournament (`ValueError` on unknown id). |
| `delete_match(match_id, actor=None)` | `None` | Delete; gated by `can_crud_match`; audits `match.deleted`. |
| `seat_players(match_id, actor=None)` | `Match` | Set `seated_at` and DM participants (older sibling of `MatchScheduleService.seat_match`, without the already-seated guard). |
| `finish_match(match_id, actor=None)` | `Match` | Set `finished_at`; requires `seated_at` (older sibling of `MatchScheduleService.finish_match`). |
| `record_match_result(match_id, winner_id, actor)` | `Match` | Two-player results: winner gets `finish_rank` 1, the other 2. `winner_id` is a **`MatchPlayers` row id**, not a User id. Gated by `can_transition_match`. |
| `signup_crew(match_id, user, role)` | `None` | Self-signup as `'commentator'` or `'tracker'`, unapproved by default; rejects duplicates; audits `crew.signup_created`. |
| `undo_crew_signup(match_id, user, role)` | `None` | Remove one's own crew signup; audits `crew.signup_removed`. |
| `acknowledge_match(match_id, user)` | `MatchAcknowledgment` | Player confirms they have seen their match. Only current players may acknowledge; double-acknowledge raises `ValueError`. Audits `match.acknowledged`. |

**Creation/reschedule flow.** `create_match` resolves every referenced user up front (so a bad id cannot leave an orphan `Match` row), creates the row, enrolls players in the tournament if needed, attaches commentators/trackers as pre-approved, audits `match.created`, then seeds per-player acknowledgment rows (the actor auto-acknowledges their own). Finally it enqueues, in order: acknowledgment-request DMs to players, the scheduled DM to crew/watchers, the subscriber fan-out (excluding everyone already DM'd), and — if flagged — the stream-candidate fan-out. `update_match` repeats the acknowledgment seeding and fan-out only when `scheduled_at` actually changed or the player set changed; a reschedule sends the "rescheduled" wording.

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `StreamRoomRepository`, `TournamentRepository`, `UserRepository`, `CommentatorRepository`, `TrackerRepository`, `AuditService`, `MatchScheduleService` (notify helpers and DM message builders), `AuthService`, `discord_queue`. Consumers: `theme/tables/match.py` (display rows, signup, acknowledge), `theme/dialog/match_dialog.py` (create/update/delete/request), `theme/dialog/match_result_dialog.py`, `theme/dialog/station_assignment_dialog.py`, `theme/dialog/stream_room_dialog.py` (stage + candidate flag), `pages/home_tabs/schedule.py`, `pages/home_tabs/stage_timeline.py`, `pages/home_tabs/player.py`, `discordbot/crew_signup.py` and `discordbot/match_acknowledgment.py` (DM button handlers).

### match_watcher_service.py — MatchWatcherService

Opt-in "watch this match" subscriptions: watchers receive lifecycle DMs without being players or crew. The DM fan-out itself happens in `MatchScheduleService`. Feature doc: [match-watcher.md](../features/match-watcher.md).

| Method | Returns | Description |
|---|---|---|
| `watch(match_id, user)` | `MatchWatcher` | Subscribe (idempotent via get-or-create). Rejects unknown and already-confirmed matches (`ValueError`); audits `match.watcher_added` only on creation. |
| `unwatch(match_id, user)` | `bool` | Unsubscribe; returns whether a row was removed; audits `match.watcher_removed` when it was. |
| `is_watching(match_id, user)` | `bool` | Whether the user currently watches the match. |
| `list_watched_match_ids(user)` | `list[int]` | All match ids the user watches (used to mark rows in the schedule table). |

Collaborators: `MatchWatcherRepository`, `MatchRepository`, `AuditService`. Consumers: `theme/tables/match.py` and `theme/dialog/match_dialog.py` (watch toggles), `discordbot/watch_buttons.py` (Unwatch DM button).

### reports_service.py — ReportsService

Aggregation queries behind the admin Reports tabs. All time math runs in US/Eastern via [`application/utils/timezone.py`](../../application/utils/timezone.py); each match contributes an estimated active window (`seated_at` or scheduled−1h → `finished_at` or start+expected duration, default 90 min). Module constants: `DEFAULT_MATCH_DURATION_MIN = 90`, `ON_TIME_THRESHOLD_MIN = 5`. Feature doc: [admin-reports.md](../features/admin-reports.md).

| Method | Returns | Description |
|---|---|---|
| `generate_capacity_forecast(start, end, tournament_id=None)` | `dict` | Concurrent-player counts (total and on-stream) sampled at auto-sized intervals (15/30/60 min by span), plus active match ids per interval and the configured `max_capacity`. |
| `peak_times(intervals, counts, top_n=5)` (static) | `list[(datetime, int)]` | Top-N busiest sampled instants from a forecast. |
| `matches_active_at(instant, tournament_id=None)` | `list[Match]` | Matches whose estimated window covers the instant (drill-down for forecast points). |
| `match_operations(start, end, tournament_id=None)` | `dict` | Per-match rows (start delay, duration, confirmation lag) and per-tournament aggregates (averages, on-time % within ±5 min). |
| `crew_coverage(start, end, tournament_id=None, user_id=None, approved_only=False)` | `dict` | Per-match crew slot coverage (flagging stream candidates with zero approved commentators or trackers) and per-user contribution rows with covered hours. |
| `stream_room_utilization(start, end, tournament_id=None, stream_room_id=None)` | `dict` | Per-room scheduled hours, back-to-back counts (<15 min gaps), idle gap hours, plus unplaced stream-candidate matches. |

**Module-level helper:** `event_day_bounds(d) -> (datetime, datetime)` — midnight-to-midnight Eastern-aware bounds for a date.

Collaborators: `SystemConfigService` (capacity limit); queries `Match`/`StreamRoom` ORM directly (read-only aggregation). Consumers: `pages/admin_tabs/reports/` (`dashboard.py`, `capacity.py`, `match_ops.py`, `crew.py`, `stream_rooms.py`).

### seedgen_service.py — SeedGenerationService

Generates randomizer seeds from the presets in `presets/`. Deep dive (per-randomizer details, presets, API keys): [seed-generation.md](seed-generation.md).

| Member | Returns | Description |
|---|---|---|
| `AVAILABLE_RANDOMIZERS` (class attr) | `list[str]` | Supported generator keys: `alttpr`, `ff1r`, `z1r`, `smmap`, `ootr`, `test`. Drives the tournament dialog dropdown and the `generate_seed` validity check. |
| `generate_seed(randomizer)` | `str` | Dispatch to the named generator; returns the seed URL/string. `ValueError` for unsupported keys. |
| `generate_alttpr_for_tournament(tournament_id, balanced=True)` | `str` | ALTTPR seed with an approved community triforce text embedded — balanced selection weights every submitter equally; falls back to a plain seed when no approved texts exist. `ValueError` for unknown tournaments. |

Collaborators: `TriforceTextService` (text selection), `pyz3r`/`aiohttp` for external randomizer APIs. Consumers: `MatchScheduleService.generate_seed` (the match seed-roll path), `theme/dialog/tournament_edit_dialog.py` (reads `AVAILABLE_RANDOMIZERS`).

### stream_room_service.py — StreamRoomService

CRUD for `StreamRoom` (stage) records. All mutations are gated by `AuthService.can_manage_stream_rooms` (Staff or Stream Manager) and audited under `stream_room.*`.

| Method | Returns | Description |
|---|---|---|
| `create_stream_room(name, stream_url=None, is_active=True, actor=None)` | `StreamRoom` | Create; trims inputs; non-empty name required (`ValueError`). |
| `update_stream_room(stream_room, name=None, stream_url=None, is_active=None, actor=None)` | `StreamRoom` | Partial update; rejects blanking the name. |
| `delete_stream_room(stream_room, actor=None)` | `None` | Delete and audit. |
| `get_all_stream_rooms(active_only=False)` | `list[StreamRoom]` | All rooms, optionally only active. |
| `get_stream_room_by_id(stream_room_id)` | `StreamRoom \| None` | Lookup by id. |

Collaborators: `StreamRoomRepository`, `AuditService`. Consumers: `theme/dialog/stream_room_edit_dialog.py` (via the admin settings tab). Match↔room assignment lives on `MatchService.assign_stage`, not here.

### system_config_service.py — SystemConfigService

Typed, static accessors over the `SystemConfiguration` key/value table; used mainly by reports. Module constants name the known keys: `event_start_date`, `event_end_date`, `max_concurrent_players`, `max_concurrent_stages`.

| Method | Returns | Description |
|---|---|---|
| `get_raw(key)` | `str \| None` | Raw stored value. |
| `set_raw(key, value, actor)` | `SystemConfiguration` | Upsert; Staff-only (`ensure`); audits `system_config.updated` with old/new values. |
| `get_int(key, default=None)` | `int \| None` | Int parse with fallback on missing/garbage values. |
| `get_date(key, default=None)` | `date \| None` | ISO date parse with fallback. |
| `get_event_window()` | `(date, date)` | Event start/end. Falls back to min/max `Match.scheduled_at`, then to today; clamps end ≥ start. |
| `get_max_concurrent_players(default=60)` | `int` | Configured player capacity, or default when unset/non-positive. |
| `get_max_concurrent_stages(default=None)` | `int` | Configured stage capacity; falls back to the given default, then to the count of active stream rooms. |

Consumers: `ReportsService` and `pages/admin_tabs/reports/` (`shared.py`, `capacity.py`, `dashboard.py`).

### tournament_notification_service.py — TournamentNotificationService

Per-user, per-tournament match-notification preference management (`MatchNotificationLevel`). The subscriber queries that consume these preferences live in `TournamentNotificationRepository` and are called from `MatchScheduleService`. Feature doc: [tournament-notifications.md](../features/tournament-notifications.md).

| Method | Returns | Description |
|---|---|---|
| `get_preference(user, tournament_id)` | `TournamentNotificationPreference \| None` | A user's preference for one tournament (`None` for unknown tournament or unset). |
| `get_user_preferences(user)` | `list[TournamentNotificationPreference]` | All of a user's preferences. |
| `upsert_preference(user, tournament_id, match_notifications)` | `TournamentNotificationPreference` | Create/update; validates the level string against `MatchNotificationLevel` and the tournament's existence (`ValueError`). |
| `get_active_tournaments()` | `list[Tournament]` | Active tournaments, name-ordered (for the preference dialog). |

Collaborators: `TournamentNotificationRepository`, `TournamentRepository`. Consumers: `theme/dialog/tournament_notification_dialog.py` (profile tab).

### tournament_service.py — TournamentService

Tournament CRUD plus Tournament Admin / Crew Coordinator membership. Creation and deletion are Staff-only; updates allow the tournament's TAs; membership grants are Staff-only (`can_grant_roles`). All mutations audited under `tournament.*`.

| Method | Returns | Description |
|---|---|---|
| `create_tournament(name, description=None, seed_generator=None, bracket_url=None, rules_url=None, tournament_format=None, average_match_duration=None, max_match_duration=None, is_active=True, players_per_match=2, team_size=1, staff_administered=False, actor=None)` | `Tournament` | Create; trims strings; treats the literal string `"None"` as no seed generator; non-empty name required. |
| `update_tournament(tournament, ...same optional fields..., actor=None)` | `Tournament` | Partial update of any subset of the same fields; audits the changed-field list. |
| `delete_tournament(tournament, actor=None)` | `None` | Staff-only delete. |
| `add_admin(tournament, target, actor=None)` | `None` | Grant Tournament Admin (M2M add). |
| `remove_admin(tournament, target, actor=None)` | `None` | Revoke Tournament Admin. |
| `add_crew_coordinator(tournament, target, actor=None)` | `None` | Grant Crew Coordinator. |
| `remove_crew_coordinator(tournament, target, actor=None)` | `None` | Revoke Crew Coordinator. |
| `get_all_tournaments(active_only=False)` | `list[Tournament]` | List tournaments. |
| `get_tournament_by_id(tournament_id)` | `Tournament \| None` | Lookup by id. |

Collaborators: `TournamentRepository`, `AuditService`. Consumers: `theme/dialog/tournament_edit_dialog.py`, `theme/dialog/user_edit_dialog.py`, `pages/admin_tabs/reports/shared.py` (filter options).

### triforce_text_service.py — TriforceTextService

Community-submitted ALTTP end-game triforce texts, scoped per tournament, with a moderation workflow (Staff or that tournament's TAs). Validation enforces exactly 3 lines, ≤19 characters each, restricted to the ALTTP text-engine character set, at least one non-blank line. Feature doc: [triforce-texts.md](../features/triforce-texts.md).

| Method | Returns | Description |
|---|---|---|
| `submit(tournament_id, lines, user)` | `TriforceText` | Validate and store a submission; rejects anonymous users, unknown or inactive tournaments; audits `triforce_text.submitted`. |
| `list_user_submissions(tournament_id, user)` | `list[TriforceText]` | A user's own submissions (empty list for unknown tournament/user). |
| `list_for_moderation(tournament_id, status=None)` | `list[TriforceText]` | Submissions filtered by `None`/`'pending'`/`'approved'`/`'rejected'`. |
| `moderate(text_id, approved, actor)` | `TriforceText` | Approve or reject; permission failure raises `ValueError` (not `PermissionError`); audits approved/rejected variants. |
| `delete(text_id, actor)` | `None` | Delete a submission under the same permission rule; audits `triforce_text.deleted`. |
| `get_balanced_text(tournament)` | `str \| None` | Random submitter first, then a random approved text from them — equal weight per submitter (deleted-user texts form their own bucket). |
| `get_random_text(tournament)` | `str \| None` | Uniformly random approved text. |

Collaborators: `TriforceTextRepository`, `AuditService`, `AuthService`. Consumers: `pages/triforce_texts.py` (player submission page), `pages/admin_tabs/triforce_texts.py` (moderation tab), `SeedGenerationService.generate_alttpr_for_tournament` (text selection).

### user_service.py — UserService

User lookup, profile edits (self- and admin-driven), activation, global role grants, and tournament enrollment management. Audited under `user.*`; role grants gated by `can_grant_roles`, admin fields by `is_staff`.

| Method | Returns | Description |
|---|---|---|
| `get_user_by_discord_id(discord_id)` | `User \| None` | Lookup by Discord id. |
| `get_current_user_from_storage(storage_discord_id)` | `User \| None` | Resolve a storage-held Discord id to a `User` (parameterized variant of `current_user_from_storage`). |
| `get_active_tournaments_categorized()` | `dict[str, list[Tournament]]` | Active tournaments split into `staff_tournaments` / `player_tournaments` / `all_tournaments`. |
| `get_user_tournament_registrations(user)` | `list[TournamentPlayers]` | The user's enrollment rows. |
| `update_user_personal_info(user, actor, display_name=None, pronouns=None, dm_notifications=None)` | `User` | Self-profile edit (page-level auth assumed); blank strings become `None`; audits only when something changed. |
| `update_user_tournament_registrations(user, actor, selected_tournament_ids, current_registrations)` | `None` | Diff-and-apply enrollment set; audits added/removed tournament ids. |
| `create_user(username, actor, display_name=None, pronouns=None, is_active=True, discord_id=None)` | `User` | Staff-only manual user creation; non-empty username required. |
| `update_user_profile(user, actor, display_name=None, pronouns=None, check_concurrency=False, initial_updated_at=None)` | `User` | Edit display name/pronouns — allowed for self or Staff (`PermissionError` otherwise); optional optimistic-concurrency check on `updated_at` raises `ValueError` on conflict. |
| `update_user_admin_fields(user, actor, is_active=None, check_concurrency=False, initial_updated_at=None)` | `User` | Staff-only activation toggle with the same concurrency option; audits `user.activation_changed` only on a real change. |
| `grant_role(target, role, actor)` | `None` | Add a `UserRole` row recording who granted it. |
| `revoke_role(target, role, actor)` | `None` | Remove a `UserRole` row. |
| `manage_tournament_enrollments(user, actor, tournament_ids, is_update=True)` | `None` | Update mode diffs against current enrollments; create mode (new users) only adds. |

Collaborators: `UserRepository`, `UserRoleRepository`, `AuditService`, `AuthService`. Consumers: `theme/dialog/user_edit_dialog.py` (admin user management), `pages/home_tabs/player_edit_info.py` (self profile), `theme/tables/match.py` and `pages/home_tabs/schedule.py` (session-user resolution).

## Utilities (`application/utils/`)

### csv_export.py

CSV rendering for the report tables ([csv_export.py](../../application/utils/csv_export.py)).

| Function | Returns | Description |
|---|---|---|
| `rows_to_csv_bytes(columns, rows)` | `bytes` | Render NiceGUI-style column descriptors (`name`, `label`, optional `hidden`) plus row dicts as UTF-8-with-BOM CSV; hidden columns are skipped. |
| `timestamped_filename(prefix, ext='csv')` | `str` | `prefix-20251130T143015Z.csv`-style download filename (UTC stamp). |

**CSV-injection safety:** every non-numeric cell whose stripped value starts with `=`, `+`, `-`, or `@` is prefixed with an apostrophe so spreadsheet apps treat it as text rather than a formula. Numbers are exempt (so negative values export cleanly); booleans render as `true`/`false`; datetimes as ISO strings; `None` as empty.

### environment.py

Environment detection and fail-fast startup validation ([environment.py](../../application/utils/environment.py)).

| Function | Returns | Description |
|---|---|---|
| `get_environment()` | `str` | `ENVIRONMENT` env var, trimmed and lowercased; defaults to `'development'`. |
| `is_production()` | `bool` | True when the environment is exactly `'production'`. |
| `validate_security_config()` | `None` | Raises `RuntimeError` — aborting startup — when `STORAGE_SECRET` is missing/blank (always; it signs the session store the whole authorization model trusts), and additionally in production when `DB_USERNAME` or `DB_PASSWORD` is empty. |

### mock_discord.py

Single helper backing the [`MOCK_DISCORD` development mode](../features/mock-discord.md) ([mock_discord.py](../../application/utils/mock_discord.py)).

| Function | Returns | Description |
|---|---|---|
| `is_mock_discord()` | `bool` | True when `MOCK_DISCORD` is `1`/`true`/`yes` (case-insensitive). Because the mock layer is a complete authentication bypass (the `/login` user picker can impersonate anyone, including Staff), the function **raises `RuntimeError` when enabled while `ENVIRONMENT=production`** rather than returning True. |

This check is what swaps `DiscordService` for `MockDiscordService` at import time (see [discord_service.py](#discord_servicepy--discordservice-mockdiscordservice-get_discord_bot)).

### timezone.py

Canonical UTC-storage / Eastern-display utilities. Full rules and rationale: [timezone-handling.md](../timezone-handling.md) ([timezone.py](../../application/utils/timezone.py)).

| Function | Returns | Description |
|---|---|---|
| `EASTERN_TZ` (constant) | `ZoneInfo` | `America/New_York`, the application display timezone. |
| `now_eastern()` | `datetime` | Current Eastern-aware datetime. |
| `parse_eastern_datetime(date_str, time_str)` | `datetime` | Parse `YYYY-MM-DD` + `HH:MM` as Eastern and return UTC (the storage path; `ValueError` on bad format). |
| `to_eastern(dt)` | `datetime \| None` | Convert any datetime to Eastern; naive inputs are assumed UTC. |
| `format_eastern_datetime(dt, fmt='%Y-%m-%d %H:%M')` | `str` | Eastern-formatted string; empty for `None`. |
| `format_eastern_date(dt)` | `str` | `YYYY-MM-DD` in Eastern; plain `date` values format as-is. |
| `format_eastern_time(dt)` | `str` | `HH:MM` (24-hour) in Eastern. |
| `format_eastern_display(dt)` | `str` | `YYYY-MM-DD HH:MM EST/EDT` with DST-aware abbreviation. |

## Testing the service layer

Service tests live in `tests/services/` — one `test_<service>_service.py` module per service (13 of the 16 modules are covered; `discord_queue`, `discord_service`, and `seedgen_service` have no dedicated suite). Key fixtures:

- [`tests/conftest.py`](../../tests/conftest.py) provides a function-scoped `db` fixture: a fresh in-memory SQLite database per test via `Tortoise.init(db_url="sqlite://:memory:")` + `generate_schemas()`, torn down by closing connections — no state leaks between tests.
- [`tests/services/conftest.py`](../../tests/services/conftest.py) adds an autouse `stub_discord_queue` fixture that monkeypatches `discord_queue.enqueue` to capture coroutines instead of running them, letting tests assert that notifications were enqueued while closing the coroutines to avoid "never awaited" warnings.
- `asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions need no decorator.

For the full development workflow (running tests, CI) see [development.md](../development.md); for suite scope and known gaps see [test-coverage.md](../features/test-coverage.md).
