# Service Layer Reference

_Method-level reference for `application/services/` (all 30 modules) and `application/utils/`. Part of the [documentation index](../README.md)._

## Pattern & conventions

Services are the business-logic layer of the [three-layer architecture](../refactoring-guide.md): pages and dialogs call services, services call repositories, repositories touch the ORM. The rules below are codebase-wide; see [CLAUDE.md](../../CLAUDE.md) for the full convention list.

- **Services own business rules.** Validation, permission gates, cross-entity coordination, audit logging, and Discord notification fan-out all live here. Repositories (see [data-model.md](data-model.md)) stay free of business logic; UI stays free of writes.
- **No NiceGUI imports.** Services never render or notify the UI; resolving the session user from `app.storage` happens in the page layer, which passes the `discord_id` into `get_user_from_discord_id`.
- **`ValueError` for user-facing errors.** Validation failures ("Match must have at least one player", "Tournament not found") raise `ValueError`; the UI catches it and shows `ui.notify(str(e), color='warning')`.
- **`PermissionError` for authorization failures.** Permission gates run through `AuthService.ensure(allowed, message)`, which raises `PermissionError`. UI handlers that gate-protected services catch both (see `pages/admin_tabs/admin_schedule.py`).
- **Audit logging** uses `AuditService.write_log(actor, action, details)` with `verb.object` action constants from `AuditActions`. The actor is required — `write_log` raises `ValueError` when actor is `None`. See [audit-logging.md](../features/audit-logging.md) and the [CLAUDE.md conventions](../../CLAUDE.md).
- **The `actor` parameter.** Mutating methods take the acting `User` as a trailing `actor` parameter (or `user` when the action is inherently self-service, e.g. `acknowledge_match`, `signup_crew`, `watch`). The same object feeds both the permission gate and the audit entry; callers resolve it once via `get_user_from_discord_id(app.storage.user.get('discord_id'))`.
- **Stateless instances.** Services hold only repository/service references; instantiate per request (`MatchService()`) or call static methods on the class (`AuthService`, `SystemConfigService`). The intentional pieces of module/class state are `MatchScheduleService._seed_locks` (per-match seed-generation locks), the `discord_queue` module's queue/worker, and the `volunteer_reminder` module's background loop task.
- **`(ok, message)` tuple returns** are the exception, not the rule, and exist only where failure is routine and must not raise:
  - `DiscordService.send_dm*`, `add_role_to_user`, `remove_role_from_user` → `(bool, str)`
  - `DiscordService.list_guilds`, `list_guild_roles` → `(bool, data_or_error)`
  - `MatchScheduleService.generate_seed` → `(bool, message, seed_url | None)`

  Everything else returns models/values and raises on failure.
- **Fire-and-forget Discord work** is wrapped in a coroutine and handed to `discord_queue.enqueue(...)` rather than awaited inline, so DB transactions never block on Discord rate limits.

## Service catalog

| Service | Module | Responsibility | Feature doc |
|---|---|---|---|
| `AnalyticsService` | [analytics_service.py](../../application/services/analytics_service.py) | Longitudinal trends: crew participation, volunteer hours, tournament health | — |
| `ApiTokenService` | [api_token_service.py](../../application/services/api_token_service.py) | Personal API access token issue/revoke/authenticate | [rest-api.md](rest-api.md) |
| `AuditService` / `AuditActions` | [audit_service.py](../../application/services/audit_service.py) | Write and query the audit trail | [audit-logging.md](../features/audit-logging.md) |
| `AuthService` / `get_user_from_discord_id` | [auth_service.py](../../application/services/auth_service.py) | Role checks and permission policy | [authentication.md](authentication.md), [role-based-auth.md](../features/role-based-auth.md) |
| `ChallongeService` | [challonge_service.py](../../application/services/challonge_service.py) | Challonge OAuth, bracket sync, scheduling, result push | — |
| `CrewService` | [crew_service.py](../../application/services/crew_service.py) | Crew signup/undo, approval, and acknowledgment | [crew-management.md](../features/crew-management.md) |
| `DiscordLinkService` | [discord_link_service.py](../../application/services/discord_link_service.py) | Verified tenant↔Discord-server link (bot-authorization OAuth + authority re-check) | [multitenancy.md](../features/multitenancy.md) |
| `DiscordRoleMappingService` | [discord_role_mapping_service.py](../../application/services/discord_role_mapping_service.py) | Discord-role→app-role mapping CRUD and login-time role sync | [discord-role-sync.md](../features/discord-role-sync.md) |
| `discord_queue` (module) | [discord_queue.py](../../application/services/discord_queue.py) | Serialized background Discord sends | [discord-integration.md](discord-integration.md) |
| `DiscordService` / `MockDiscordService` | [discord_service.py](../../application/services/discord_service.py) | Bot DMs, button views, guild roles | [discord-integration.md](discord-integration.md) |
| `EquipmentService` | [equipment_service.py](../../application/services/equipment_service.py) | Lending-asset CRUD and checkout/check-in workflow | — |
| `FeedbackService` | [feedback_service.py](../../application/services/feedback_service.py) | In-app feedback submission and review | — |
| `MatchDisplayService` | [match_display_service.py](../../application/services/match_display_service.py) | Read + format matches into table-row dicts (filters, display shape) | [frontend.md](frontend.md) |
| `MatchScheduleService` | [match_schedule_service.py](../../application/services/match_schedule_service.py) | Match lifecycle transitions, seed rolls, DM fan-out | [discord-notifications.md](../features/discord-notifications.md) |
| `MatchService` | [match_service.py](../../application/services/match_service.py) | Match CRUD, lifecycle, station/stage, acknowledgments | [match-acknowledgment.md](../features/match-acknowledgment.md) |
| `MatchSuggestionService` | [match_suggestion_service.py](../../application/services/match_suggestion_service.py) | Suggest match start times that minimise venue occupancy | — |
| `MatchWatcherService` | [match_watcher_service.py](../../application/services/match_watcher_service.py) | Watch/unwatch matches for DM updates | [match-watcher.md](../features/match-watcher.md) |
| `PlayerAvailabilityService` | [player_availability_service.py](../../application/services/player_availability_service.py) | Player-declared availability windows | — |
| `ReportsService` | [reports_service.py](../../application/services/reports_service.py) | Capacity, operations, crew, and stage reports | [admin-reports.md](../features/admin-reports.md) |
| `SeedGenerationService` | [seedgen_service.py](../../application/services/seedgen_service.py) | Randomizer seed generation | [seed-generation.md](seed-generation.md) |
| `StreamRoomService` | [stream_room_service.py](../../application/services/stream_room_service.py) | Stream room (stage) CRUD | — |
| `SystemConfigService` | [system_config_service.py](../../application/services/system_config_service.py) | Typed access to `SystemConfiguration` keys | [admin-reports.md](../features/admin-reports.md) |
| `TelemetryService` / `TelemetryCategory` / `TelemetryEventType` | [telemetry_service.py](../../application/services/telemetry_service.py) | Engagement telemetry capture + Staff-gated engagement report | [telemetry.md](../features/telemetry.md) |
| `TenantService` | [tenant_service.py](../../application/services/tenant_service.py) | Tenant resolution (cached slug/guild/domain lookup), tenant CRUD, membership, super-admin grant | [multitenancy.md](../features/multitenancy.md) |
| `TournamentNotificationService` | [tournament_notification_service.py](../../application/services/tournament_notification_service.py) | Per-tournament notification preferences | [tournament-notifications.md](../features/tournament-notifications.md) |
| `TournamentService` | [tournament_service.py](../../application/services/tournament_service.py) | Tournament CRUD, TA/CC membership | — |
| `TriforceTextService` | [triforce_text_service.py](../../application/services/triforce_text_service.py) | Triforce text submission and moderation | [triforce-texts.md](../features/triforce-texts.md) |
| `TwitchService` | [twitch_service.py](../../application/services/twitch_service.py) | Twitch account-linking OAuth (verified identity capture) | — |
| `UserService` | [user_service.py](../../application/services/user_service.py) | User CRUD, profiles, roles, enrollments | [role-based-auth.md](../features/role-based-auth.md) |
| `VolunteerAutoscheduleService` | [volunteer_autoschedule_service.py](../../application/services/volunteer_autoschedule_service.py) | Greedy draft generator for the volunteer schedule | — |
| `VolunteerAvailabilityService` | [volunteer_availability_service.py](../../application/services/volunteer_availability_service.py) | Volunteer-declared availability windows | — |
| `VolunteerPositionService` | [volunteer_position_service.py](../../application/services/volunteer_position_service.py) | Coordinator-defined volunteer position CRUD | — |
| `VolunteerQualificationService` | [volunteer_qualification_service.py](../../application/services/volunteer_qualification_service.py) | Read and set which positions a volunteer is qualified to fill | — |
| `VolunteerProfileService` | [volunteer_profile_service.py](../../application/services/volunteer_profile_service.py) | Volunteer opt-in lifecycle and assignable pool | — |
| `volunteer_reminder` (module) | [volunteer_reminder.py](../../application/services/volunteer_reminder.py) | Background loop sending shift-reminder DMs | — |
| `VolunteerScheduleService` | [volunteer_schedule_service.py](../../application/services/volunteer_schedule_service.py) | Volunteer shifts, assignments, acknowledgment, coverage | — |

All classes and `get_user_from_discord_id` are re-exported from [`application/services/__init__.py`](../../application/services/__init__.py); `discord_queue` and `volunteer_reminder` are imported as modules (`from application.services import discord_queue`).

### api_token_service.py — ApiTokenService

Issues, lists, revokes, and authenticates personal API access tokens. Only the SHA-256 hash of a token is persisted; the plaintext (prefixed `sglman_pat_`) is returned exactly once, at creation. A token authenticates as its owning `User` and inherits that user's permissions; a `read_only` token is restricted to read (GET) endpoints by the API auth layer. Used by the REST API; see [rest-api.md](rest-api.md).

| Method | Returns | Description |
|---|---|---|
| `create_token(actor, name, read_only=False, expires_at=None)` | `(ApiToken, str)` | Create a token for `actor`; returns the record and the **raw token** (only chance to capture it). Non-empty name required; `expires_at` must be in the future (else `ValueError`). Audits `apitoken.created`. |
| `list_tokens(actor)` | `list[ApiToken]` | The actor's own active (non-revoked) tokens. |
| `revoke_token(actor, token_id)` | `None` | Revoke; `ValueError` for unknown/already-revoked tokens, `PermissionError` when the token belongs to another user. Audits `apitoken.revoked`. |
| `authenticate(raw_token)` | `(User, ApiToken) \| None` | Resolve a raw bearer token to its owner. Returns `None` for unknown/revoked/expired tokens (logged as warnings); on success updates `last_used_at`. |

Collaborators: `ApiTokenRepository`, `AuditService`. Consumers: the REST API authentication layer (bearer-token auth) and the token-management UI.

### audit_service.py — AuditService

Writes and queries `AuditLog` rows. Every mutating service action records who did what, with JSON-encoded details. Canonical doc: [audit-logging.md](../features/audit-logging.md).

**`AuditActions`** is a plain constants class holding every namespaced `verb.object` action string used in the codebase — one place to grep when reviewing audit coverage. Namespaces covered: `match.*` (lifecycle, CRUD, stage/station assignment, stream-candidate flag, watchers, seed rolls), `crew.*` (signups, approval, acknowledgment), `tournament.*` (CRUD, TA/CC grants), `user.*` (CRUD, profile edits, activation, roles, enrollments), `stream_room.*` (CRUD), `system_config.*` (updates), `triforce_text.*` (submission/moderation lifecycle), `apitoken.*` (issue/revoke), `feedback.*` (submission/review), `equipment.*` (asset CRUD, checkout/check-in), `challonge.*` (connection, player/tournament linking, bracket sync, result push), `volunteer.*` (opt-in, position/shift CRUD, assignment, acknowledgment, drafts), and `player_availability.*` (window updates). Add a new constant here when introducing a new action; never pass literal strings.

| Method | Returns | Description |
|---|---|---|
| `write_log(actor, action, details=None)` | `AuditLog` | Create an entry; JSON-encodes `details` (non-serializable values fall back to `str`). Raises `ValueError` if `actor` is `None`. |
| `list_logs(*, start=None, end=None, user_id=None, action_contains=None, limit=100, offset=0)` | `list[AuditLog]` | Filtered, paginated log listing (delegates to `AuditRepository`). |
| `count_logs(*, start=None, end=None, user_id=None, action_contains=None)` | `int` | Count matching the same filters as `list_logs`. |
| `get_logs_for_user(user, limit=None)` | `list[AuditLog]` | A user's entries, most recent first. |
| `get_recent_logs(limit=100)` | `list[AuditLog]` | Most recent entries across all users, with `user` prefetched. |

Collaborators: `AuditRepository`. Consumers: every mutating service (writer side); the audit log viewer at `pages/admin_tabs/reports/audit.py` (reader side).

### auth_service.py — AuthService and get_user_from_discord_id

Stateless authorization policy: every check is a `@staticmethod async def` taking `User | None` and returning a bool (no exceptions for "not allowed" — that is `ensure`'s job). Deep dive: [authentication.md](authentication.md); role semantics: [role-based-auth.md](../features/role-based-auth.md).

| Method | Returns | Description |
|---|---|---|
| `get_roles(user)` | `set[Role]` | All global roles held by the user (empty for `None`). |
| `has_role(user, role)` | `bool` | Whether the user holds a specific global `Role`. |
| `is_staff(user)` | `bool` | Holds `Role.STAFF`. |
| `is_proctor(user)` | `bool` | Holds `Role.PROCTOR`. |
| `is_stream_manager(user)` | `bool` | Holds `Role.STREAM_MANAGER`. |
| `is_volunteer_coordinator(user)` | `bool` | Holds `Role.VOLUNTEER_COORDINATOR`. |
| `is_equipment_manager(user)` | `bool` | Holds `Role.EQUIPMENT_MANAGER`. |
| `is_volunteer(user)` | `bool` | Holds `Role.VOLUNTEER`. |
| `is_tournament_admin(user, tournament_id)` | `bool` | Listed in `Tournament.admins`. |
| `is_crew_coordinator_of(user, tournament_id)` | `bool` | Listed in `Tournament.crew_coordinators`. |
| `can_view_admin(user)` | `bool` | An admin global role (`STAFF`, `STREAM_MANAGER`, `EQUIPMENT_MANAGER`, `VOLUNTEER_COORDINATOR`), or TA/CC of any tournament. Excludes `PROCTOR`/`VOLUNTEER`. |
| `can_edit_tournament(user, tournament)` | `bool` | Staff, or TA of that tournament. |
| `can_crud_match(user, match)` | `bool` | Staff, or TA of the match's tournament. |
| `can_transition_match(user, match)` | `bool` | Staff, Proctor, or TA — gates seat/start/finish/confirm, seed rolls, station assignment. |
| `can_approve_crew(user, match)` | `bool` | Staff, TA, or CC of the match's tournament. |
| `can_manage_stream_rooms(user)` | `bool` | Staff or Stream Manager — gates StreamRoom CRUD. |
| `can_manage_volunteers(user)` | `bool` | Staff or Volunteer Coordinator — gates volunteer position/shift/assignment management and the auto-scheduler. |
| `can_manage_equipment(user)` | `bool` | Staff or Equipment Manager — gates asset CRUD and check-in. |
| `can_checkout_equipment(user)` | `bool` | Manager (any borrower) or Volunteer (self-checkout only). |
| `can_checkin_equipment(user)` | `bool` | Staff or Equipment Manager. |
| `can_assign_match_stream(user, match)` | `bool` | Stream Manager globally, or TA of the match's tournament — gates stage assignment and the stream-candidate flag. |
| `can_grant_roles(user)` | `bool` | Staff only — gates role grants and TA/CC membership changes. |
| `ensure(allowed, message="Permission denied")` | `None` | Raises `PermissionError(message)` when `allowed` is falsy; the standard gate inside mutating services. |

**Module-level helper:** `get_user_from_discord_id(discord_id) -> User | None` resolves a Discord id — typically `app.storage.user.get('discord_id')`, read in the page layer — to a `User` model (or `None` when logged out / deleted). Call it once at page entry and pass the result into the helpers above — don't re-resolve per check.

Consumers: `middleware/auth.py` (`protected_page` role enforcement), nearly every page and dialog (`pages/home.py`, `pages/admin.py`, `pages/admin_tabs/*`, `theme/dialog/*`, `theme/tables/*`), and all mutating services via `ensure`.

### challonge_service.py — ChallongeService

Coordinates the Challonge integration: one shared SGL service-account OAuth connection writes brackets; players link their own Challonge identity (scope `me`) only so they can be mapped to bracket participants (their tokens are not retained). The service mirrors a linked tournament's bracket into local `ChallongeParticipant`/`ChallongeMatch` rows, schedules open matchups through the existing match-request flow, and pushes recorded results back to Challonge. Module constants: `CHALLONGE_MONTHLY_QUOTA = 500`, plus internal token-refresh-buffer and sync-throttle windows. Mock mode is gated by [`MOCK_CHALLONGE`](#mock_challongepy).

| Method | Returns | Description |
|---|---|---|
| `is_configured()` (static) | `bool` | OAuth app credentials are present (or mock is on). |
| `service_authorize_url(state)` / `player_authorize_url(state)` (static) | `str` | Challonge OAuth authorize URL for the service-account / per-player flow. |
| `redirect_uri()` (static) | `str` | The single registered OAuth redirect URI (both flows). |
| `get_valid_access_token(force_refresh=False)` | `str` | Live service access token, refreshing when expiring/forced; `ValueError` when not connected or no refresh token is available. |
| `save_service_connection(token_payload, actor)` | `ChallongeConnection` | Staff-only; stores the service-account tokens and connected username; audits `challonge.connected`. |
| `disconnect(actor)` | `None` | Staff-only; clears the connection; audits `challonge.disconnected`. |
| `get_connection_status()` | `dict` | `{connected, configured, request_usage, request_quota, ...}` for the admin UI. |
| `record_player_link(user, challonge_user_id, challonge_username, actor)` | `None` | Persist a player's linked Challonge identity (OAuth path); audits `challonge.player_linked`. |
| `participant_tournament_ids(user)` | `set[int]` | Tournament ids whose mirrored bracket includes this user. |
| `link_player_manually(user, challonge_user_id, challonge_username, actor)` | `None` | Staff override linking a user by Challonge id; rejects ids already linked elsewhere (`ValueError`); audits `challonge.player_linked` with `manual: True`. |
| `set_player_username(user, challonge_username, actor)` | `None` | Staff override correcting the display username on an already-linked account; audits `challonge.player_username_updated`. |
| `unlink_player(user, actor)` | `None` | Clear a user's Challonge link; audits `challonge.player_unlinked`. |
| `exchange_player_code(code)` | `dict` | Exchange a player's auth code and return `{user_id, username}` (token used once, discarded). |
| `exchange_service_code(code)` | `dict` | Exchange the service-account auth code for a token payload. |
| `parse_tournament_identifier(id_or_url)` (static) | `str` | Extract a Challonge identifier from a raw id or URL (handles subdomain brackets). |
| `link_tournament(tournament_id, id_or_url, actor)` | `Tournament` | Gated by `can_edit_tournament`; fetches the bracket, stores the link, and mirrors participants/matches in the same round-trip; audits `challonge.tournament_linked`. |
| `sync_bracket(tournament_id, actor, force=False)` | `dict[str, int]` | Gated by `can_edit_tournament`; re-fetch and mirror the bracket; non-forced calls inside the throttle window are a no-op (`{skipped: True}`). Audits `challonge.bracket_synced`. |
| `list_unscheduled_matches_for_user(user)` | `list[ChallongeMatch]` | Open bracket matchups for the user not yet scheduled locally. |
| `schedule_challonge_match(challonge_match_pk, scheduled_date, scheduled_time, actor, comment=None)` | `Match` | Schedule an open matchup via `MatchService.submit_match_request` and link it; `ValueError` for already-scheduled/not-ready matches or unlinked players. |
| `push_result_if_linked(match, actor)` | `bool` | Push the result only when the match mirrors a Challonge match; returns whether a push was attempted (used by the confirm flow). |
| `push_match_result(match, actor)` | `None` | Report the recorded winner/loser to Challonge, then force a re-sync to surface newly-opened next-round matches; audits `challonge.result_pushed`. |

Collaborators: `ChallongeRepository`, `TournamentRepository`, `MatchService`, `AuthService`, `AuditService`, [`challonge_client.py`](#challonge_clientpy) (`ChallongeClient`/`MockChallongeClient`), [`mock_challonge.py`](#mock_challongepy). Consumers: the Challonge OAuth callback middleware, the admin Challonge tab, and the player linking/scheduling pages.

### crew_service.py — CrewService

Crew (commentator/tracker) self-signup, the approval workflow, and crew-side acknowledgment. Feature doc: [crew-management.md](../features/crew-management.md).

| Method | Returns | Description |
|---|---|---|
| `signup_crew(match_id, user, role)` | `None` | Self-signup as `'commentator'` or `'tracker'`, unapproved by default; rejects an invalid role, a finished match, a duplicate signup, and a user who is a player in the match; audits `crew.signup_created`. |
| `undo_crew_signup(match_id, user, role)` | `None` | Remove one's own crew signup; audits `crew.signup_removed`. |
| `get_crew_member_by_id(crew_id, crew_type)` | `Commentator \| Tracker \| None` | Fetch by row id; `crew_type` must be `'commentator'` or `'tracker'` (else `ValueError`). |
| `update_crew_approval(crew_member, crew_type, approved, actor=None)` | `Commentator \| Tracker` | Approve/unapprove. Gated by `can_approve_crew`; refreshes from DB to narrow approval races; no-ops (no audit, no DM) when state already matches; unapproval clears `acknowledged_at`; approval enqueues an acknowledgment-request DM. |
| `approve_crew_member(crew_member, crew_type, actor=None)` | `Commentator \| Tracker` | Convenience wrapper for `update_crew_approval(..., approved=True)`. |
| `acknowledge_crew_assignment(crew_id, crew_type, user)` | `Commentator \| Tracker` | Crew member confirms their own approved assignment. Rejects other users and unapproved rows (`ValueError`); already-acknowledged rows are a silent no-op. |

Collaborators: `CommentatorRepository`, `TrackerRepository`, `MatchRepository` (signup match lookup), `AuditService`, `DiscordService` (via `discord_queue`). Consumers: `theme/dialog/approve_crew_dialog.py`, `theme/tables/match.py` (web signup/undo + acknowledge buttons), `api/routers/match_actions.py` (REST signup/undo), `discordbot/crew_signup.py` and `discordbot/crew_acknowledgment.py` (DM button handlers).

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
| `send_dm(user_id, message)` | `(bool, str)` | Plain DM to a Discord user id. Also enqueues a fire-and-forget mirror of the message to the recipient's web-push devices (real service only; the mock skips it) — see [web-push.md](../features/web-push.md). |
| `send_dm_with_crew_buttons(user_id, message, match_id)` | `(bool, str)` | DM with commentator/tracker signup buttons. |
| `send_dm_with_acknowledgment_button(user_id, message, match_id)` | `(bool, str)` | DM with a match Acknowledge button. |
| `send_dm_with_crew_acknowledgment_button(user_id, message, crew_type, crew_id)` | `(bool, str)` | DM with a crew-assignment Acknowledge button. |
| `send_dm_with_unwatch_button(user_id, message, match_id)` | `(bool, str)` | DM with an Unwatch button for match watchers. |
| `get_bot()` | `commands.Bot \| None` | The underlying bot instance. |
| `list_guilds()` | `(bool, list[{id, name}] \| str)` | Guilds the bot is connected to. |
| `list_guild_roles(guild_id)` | `(bool, list[{id, name}] \| str)` | All roles in a guild (fetch with cached fallback). |
| `add_role_to_user(guild_id, user_id, role_id, reason=None)` | `(bool, str)` | Grant a Discord role to a guild member. |
| `remove_role_from_user(guild_id, user_id, role_id, reason=None)` | `(bool, str)` | Remove a Discord role from a guild member. |
| `get_guild_summary(guild_id)` | `(bool, {id, name} \| str)` | Name of a guild the bot can see (renders the connected-server label; confirms bot presence). |
| `member_can_manage_guild(guild_id, user_id)` | `(bool, bool \| str)` | Whether a user is owner / Administrator / has Manage Server. **Fails closed** (`ok=False`) if the bot can't determine it. The authority check behind `DiscordLinkService`. |

**`MockDiscordService`** mirrors the full public surface, printing to stdout and returning success tuples. Its fixture data (guilds, roles, member roles, authority) comes from [`mock_discord_data.py`](../../application/utils/mock_discord_data.py), kept in sync with `scripts/seed_dev.py`. When [`MOCK_DISCORD`](../features/mock-discord.md) is enabled, the module rebinds the name `DiscordService = MockDiscordService` at import time, so all callers get the stub transparently.

### discord_link_service.py — DiscordLinkService

Verified linking of a `Tenant` to a Discord guild. Because `discord_guild_id` is no longer unique, a tenant may not merely *claim* a guild id — `DiscordLinkService` gates linking twice: **app** (`can_manage_link` → tenant STAFF or super-admin) and **Discord** (the actor must administer the guild). `authorize_url(state)` builds Discord's bot-authorization URL (`scope=bot`, adds the bot on consent); `complete_link(actor, tenant, code)` exchanges the code for an authoritative `guild` object then calls `link_guild(actor, tenant, guild_id)`, which re-checks `DiscordService.member_can_manage_guild` (fails closed) before stamping the guild via `TenantService.set_discord_guild_id` and auditing `discord.server_linked`. `disconnect(actor, tenant)` clears the link (leaving the bot, which other tenants may share) and audits `discord.server_unlinked`. Callback route: `/oauth/discord/connect/callback` in [`pages/auth.py`](../../pages/auth.py). Env: `DISCORD_BOT_PERMISSIONS`, `DISCORD_CONNECT_REDIRECT_URL`.

Consumers: `MatchScheduleService` and `CrewService` (notification fan-out), `theme/dialog/send_message_dialog.py` (admin "send DM" dialog).

### equipment_service.py — EquipmentService

Lending-asset management (create/edit/delete, bulk creation with auto-assigned asset numbers) and the checkout/check-in workflow with full loan history. Asset management is gated by `AuthService.can_manage_equipment` (Staff or Equipment Manager); checkout by `can_checkout_equipment` (managers, or Volunteers checking out to themselves only); check-in by `can_checkin_equipment`. Audited under `equipment.*`. Module constant: `MAX_BULK_COUNT = 200`.

| Method | Returns | Description |
|---|---|---|
| `create_asset(actor, name, description=None, private_notes=None, owner_user_id=None)` | `Equipment` | Manager-only; auto-assigns the next asset number; non-empty name required; `owner_user_id=None` means SpeedGaming Live. Audits `equipment.created`. |
| `bulk_create_assets(actor, name, count, description=None, private_notes=None, owner_user_id=None)` | `list[Equipment]` | Manager-only; create `count` (1–200) consecutively numbered assets. |
| `update_asset(actor, equipment_id, name, description, private_notes, owner_user_id, status=None)` | `Equipment` | Manager-only edit; refuses to set/clear `CHECKED_OUT` status directly (use checkout/check-in). Audits `equipment.updated`. |
| `delete_asset(actor, equipment_id)` | `None` | Manager-only; refuses an asset with an open loan. Audits `equipment.deleted`. |
| `checkout(actor, equipment_id, borrower_id=None)` | `EquipmentLoan` | Open a loan; managers may set a `borrower_id`, otherwise the borrower is `actor`. Rejects retired/already-checked-out assets; flips status to `CHECKED_OUT`. Audits `equipment.checked_out`. |
| `checkin(actor, equipment_id)` | `Equipment` | Close the open loan and flip status to `AVAILABLE`; `ValueError` when not checked out. Audits `equipment.checked_in`. |
| `list_assets()` | `list[Equipment]` | All assets. |
| `get_asset(equipment_id)` | `Equipment \| None` | Lookup by id. |
| `current_loan(equipment)` | `EquipmentLoan \| None` | The open loan for an asset, if any. |
| `open_loans_by_equipment_id()` | `dict[int, EquipmentLoan]` | All open loans keyed by equipment id (table batch-load). |
| `loan_history(equipment)` | `list[EquipmentLoan]` | Full loan history for an asset. |
| `my_checkouts(user)` | `list[EquipmentLoan]` | A user's currently-open loans. |

Collaborators: `EquipmentRepository`, `AuthService`, `AuditService`. The equipment detail pages render QR codes via [`qrcode_util.py`](#qrcode_utilpy).

### feedback_service.py — FeedbackService

Records in-app feedback from logged-in attendees and lets admins review it. The submitted category is coerced to a valid `FeedbackCategory` (defaulting to `OTHER`); the page URL is truncated to `PAGE_URL_MAX_LENGTH = 512`. Audited under `feedback.*`.

| Method | Returns | Description |
|---|---|---|
| `submit(actor, category, message, page_url)` | `Feedback` | Record a submission from `actor`; non-empty message required (`ValueError`). Audits `feedback.submitted`. |
| `list_recent(limit=200)` | `list[Feedback]` | Recent submissions for the admin review list. |
| `mark_reviewed(actor, feedback_id)` | `Feedback` | Admin-only (`can_view_admin`); sets status `REVIEWED`; `ValueError` for unknown id. Audits `feedback.reviewed`. |

Collaborators: `FeedbackRepository`, `AuthService`, `AuditService`. Consumers: the in-app feedback dialog and the admin feedback review tab.

### match_display_service.py — MatchDisplayService

Read-only view-model assembly for the match tables: fetches matches (and their acknowledgments) via repositories and formats them into the plain dicts the NiceGUI slot templates consume. Extracted from `MatchService` so the latter keeps only lifecycle logic — no writes, audit, or notifications here. Feature doc: [frontend.md](frontend.md).

| Method | Returns | Description |
|---|---|---|
| `get_match_for_display(match_id)` | `dict \| None` | One match formatted for the UI (state, Eastern-formatted times, players with rank/station, acknowledgment summary, crew with approval/ack state, seed URL). |
| `get_matches_for_display(*, tournament_ids=None, stream_room_ids=None, only_upcoming=False, user_discord_id=None)` | `list[dict]` | Filtered match list in the same display shape, with acknowledgments batch-loaded. |
| `get_tournaments_for_filter()` | `dict[int, str]` | Tournament id → name for filter dropdowns. |
| `get_stream_rooms_for_filter()` | `dict[int, str]` | Stream room id → name for filter dropdowns. |

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentRepository`, `StreamRoomRepository`. Consumers: `theme/tables/match.py` (`self.display_service` — filters, `refresh`, and single-row updates).

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
| `notify_match_scheduled(match, *, rescheduled=False, is_stream_candidate=False)` | `None` | The collapsed scheduled/rescheduled fan-out shared by `create_match`/`update_match`/`submit_match_request`: loads relations, computes the exclude list, then enqueues the ack request + crew DM + tournament-subscriber DMs (+ stream-candidate DMs when flagged). Awaited by the caller; the individual sub-notifications run on the queue. |
| `notify_stream_candidate(match)` | `None` | Standalone stream-candidate fan-out for `set_stream_candidate` (fetch + collect exclude + enqueue the subscriber DMs). |

The per-recipient `notify_*` methods are designed to run **inside** the `discord_queue` worker: callers enqueue them rather than awaiting. All DM recipients are filtered by `User.dm_notifications` and the presence of a `discord_id`.

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentNotificationRepository`, `DiscordService`, `SeedGenerationService`, `AuditService`, `discord_queue`. Consumers: `pages/admin_tabs/admin_schedule.py` (seat/start/finish/confirm/seed buttons), `MatchService` (reuses the notify helpers and DM message builders).

### match_service.py — MatchService

Match CRUD with full notification fan-out, schedule queries, station/stage assignment, results, and player acknowledgments. Table display formatting now lives in [`MatchDisplayService`](#match_display_servicepy--matchdisplayservice) and crew signup/undo in [`CrewService`](#crew_servicepy--crewservice); the schedule-query methods below delegate to `MatchRepository`.

| Method | Returns | Description |
|---|---|---|
| `get_all_matches_for_schedule()` | `list[Match]` | Every match with relations prefetched, ordered by `scheduled_at` (public schedule tab). Delegates to `MatchRepository.get_all_for_schedule`. |
| `get_matches_for_date(target_date, exclude_finished=True, require_stream_room=True)` | `list[Match]` | A day's matches with players/crew prefetched (stage timeline). Delegates to `MatchRepository.get_for_date`. |
| `group_matches_by_stream_room(matches)` | `dict[int, (StreamRoom, list[Match])]` | Group prefetched matches by stream room. |
| `get_matches_for_player(discord_id)` | `list[Match]` | Matches where the Discord user is a player. Delegates to `MatchRepository.get_for_player`. |
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
| `acknowledge_match(match_id, user)` | `MatchAcknowledgment` | Player confirms they have seen their match. Only current players may acknowledge; double-acknowledge raises `ValueError`. Audits `match.acknowledged`. |

**Creation/reschedule flow.** `create_match` resolves every referenced user up front (so a bad id cannot leave an orphan `Match` row), creates the row, enrolls players in the tournament if needed, attaches commentators/trackers as pre-approved, audits `match.created`, then seeds per-player acknowledgment rows (the actor auto-acknowledges their own). Finally it hands the whole scheduled-notification fan-out to `MatchScheduleService.notify_match_scheduled` (ack request + crew DM + subscriber fan-out, plus stream-candidate when flagged). `update_match` re-seeds acknowledgments when `scheduled_at` or the player set changed; on a time change it calls `notify_match_scheduled(rescheduled=True)`, otherwise it enqueues just the acknowledgment request.

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentRepository`, `UserRepository`, `CommentatorRepository`, `TrackerRepository`, `AuditService`, `MatchScheduleService` (lifecycle notify + `notify_match_scheduled`/`notify_stream_candidate`), `AuthService`, `discord_queue`. Consumers: `theme/tables/match.py` (acknowledge, plus reads via `MatchDisplayService`), `theme/dialog/match_dialog.py` (create/update/delete/request), `theme/dialog/match_result_dialog.py`, `theme/dialog/station_assignment_dialog.py`, `theme/dialog/stream_room_dialog.py` (stage + candidate flag), `pages/home_tabs/schedule.py`, `pages/home_tabs/stage_timeline.py`, `pages/home_tabs/player.py`, `discordbot/match_acknowledgment.py` (DM button handler).

### match_suggestion_service.py — MatchSuggestionService

Suggests an optimal match start time by finding occupancy troughs across the venue, scoring 30-minute candidate slots by combined player occupancy (and preferring slots all players prefer). Searches the next 4 hours within the configured tournament hours first, then falls back to the full remaining event window. Player availability is honoured: a slot is ineligible if any player with declared windows is unavailable for it. Capacity is never surfaced to callers — the suggestion appears as a neutral "best time." Module constants: `_SLOT_INTERVAL_MIN = 30`, `_PRIMARY_WINDOW_HOURS = 4`.

| Method | Returns | Description |
|---|---|---|
| `suggest_match_time(tournament_id, player_ids)` | `datetime` | Best UTC start time for the match. Raises `ValueError` when no eligible slot exists within the event schedule. |

Collaborators: `PlayerAvailabilityRepository`, `SystemConfigService` (`get_tournament_hours`, `get_event_window`), [`timezone.py`](#timezonepy), queries `Match`/`Tournament` directly. Consumers: the match-request/create dialogs ("suggest time" helper).

### match_watcher_service.py — MatchWatcherService

Opt-in "watch this match" subscriptions: watchers receive lifecycle DMs without being players or crew. The DM fan-out itself happens in `MatchScheduleService`. Feature doc: [match-watcher.md](../features/match-watcher.md).

| Method | Returns | Description |
|---|---|---|
| `watch(match_id, user)` | `MatchWatcher` | Subscribe (idempotent via get-or-create). Rejects unknown and already-confirmed matches (`ValueError`); audits `match.watcher_added` only on creation. |
| `unwatch(match_id, user)` | `bool` | Unsubscribe; returns whether a row was removed; audits `match.watcher_removed` when it was. |
| `is_watching(match_id, user)` | `bool` | Whether the user currently watches the match. |
| `list_watched_match_ids(user)` | `list[int]` | All match ids the user watches (used to mark rows in the schedule table). |

Collaborators: `MatchWatcherRepository`, `MatchRepository`, `AuditService`. Consumers: `theme/tables/match.py` and `theme/dialog/match_dialog.py` (watch toggles), `discordbot/watch_buttons.py` (Unwatch DM button).

### player_availability_service.py — PlayerAvailabilityService

Self-service availability for any logged-in player — unlike volunteer availability there is no role or opt-in gate. A user's windows are replaced wholesale on each save. Windows carry a `VolunteerAvailabilityStatus` (`AVAILABLE`/`PREFERRED`/`UNAVAILABLE`). Audited under `player_availability.*`.

| Method | Returns | Description |
|---|---|---|
| `availability_for(user)` | `list[PlayerAvailability]` | The user's declared windows. |
| `set_windows(user, windows)` | `list[PlayerAvailability]` | Replace the user's availability with `(starts_at, ends_at, status, note)` tuples (each must end after it starts); transactional. Audits `player_availability.updated`. |
| `clear(user)` | `None` | Delete all of the user's windows; audits `player_availability.updated` with `window_count: 0`. |
| `availability_map(user_ids, start, end)` | `dict[int, list[PlayerAvailability]]` | user_id → windows overlapping `[start, end]` (batch lookup). |
| `covers(windows, start, end)` (static) | `VolunteerAvailabilityStatus \| None` | Strongest signal for a window: an overlapping `UNAVAILABLE` wins; else `PREFERRED` beats `AVAILABLE`; `None` if nothing overlaps. |
| `effective_segments(windows, start, end)` (static) | `list[(datetime, datetime, status \| None)]` | Split `[start, end]` into maximal constant-availability segments (resolved by `covers` precedence, adjacent equal segments merged). |

Collaborators: `PlayerAvailabilityRepository`, `AuditService`. Consumers: the player availability page and `MatchSuggestionService`.

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

### analytics_service.py — AnalyticsService

Longitudinal / cross-event analytics behind the admin Reports → **Insights & Trends** page — the trend counterpart to `ReportsService`'s point-in-time snapshots. Events are bucketed by the US/Eastern calendar date of when they happened (`week` = Monday-anchored, `month` = 1st-anchored) into contiguous buckets (capped at `MAX_BUCKETS = 240`). Module constants: `ON_TIME_THRESHOLD_MIN = 5`, `HEALTH_WEIGHTS` (completion 0.30, on-time 0.25, coverage 0.25, duration 0.20).

| Method | Returns | Description |
|---|---|---|
| `crew_participation_trends(start, end, bucket='week', tournament_id=None)` | `dict` | Per-bucket commentator/tracker signups & approvals and unique-people counts (bucketed by match `scheduled_at`), plus top-15 contributors and window totals. |
| `volunteer_hour_trends(start, end, bucket='week')` | `dict` | Per-bucket scheduled vs checked-in volunteer-hours, needed-hours and fill-rate %, a per-position breakdown, and top-15 volunteers (bucketed by shift `starts_at`). |
| `tournament_health(start, end)` | `dict` | Per-tournament scorecards: completion % (past matches only), on-time %, crew coverage %, avg duration vs expected, and a composite 0–100 `health_score`. |
| `activity_trends(start, end, bucket='week')` | `dict` | Per-bucket audit-log volume grouped by action namespace (the `verb.object` prefix). |

**Pure helpers (unit-tested without a DB):** `bucket_start`, `iter_bucket_starts`, `bucket_label`, `_bucket_index`, `health_score` (weighted average of present `(value, weight)` components, renormalized so missing dimensions don't dilute the score; `None` when no component has data), `_finalize_health`, `_duration_hours`.

Collaborators: queries `Match`/`Commentator`/`Tracker`/`VolunteerShift`/`VolunteerAssignment`/`AuditLog` ORM directly (read-only aggregation, same pattern as `ReportsService`); `now_eastern` for the past-match cutoff. Consumers: `pages/admin_tabs/reports/insights.py`.

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

Typed, static accessors over the `SystemConfiguration` key/value table. Module constants name the known keys: `KEY_EVENT_START_DATE`, `KEY_EVENT_END_DATE`, `KEY_MAX_CONCURRENT_PLAYERS`, `KEY_MAX_CONCURRENT_STAGES`, `KEY_VOLUNTEER_REMINDER_LEAD_MINUTES`, `KEY_TOURNAMENT_HOURS`, `KEY_DISCORD_SYNC_GUILD_ID`.

| Method | Returns | Description |
|---|---|---|
| `get_raw(key)` | `str \| None` | Raw stored value. |
| `set_raw(key, value, actor)` | `SystemConfiguration` | Upsert; Staff-only (`ensure`); audits `system_config.updated` with old/new values. |
| `get_int(key, default=None)` | `int \| None` | Int parse with fallback on missing/garbage values. |
| `get_discord_sync_guild_id()` | `int \| None` | Discord guild id used for login-time role sync (read by `DiscordRoleMappingService`). |
| `get_date(key, default=None)` | `date \| None` | ISO date parse with fallback. |
| `get_event_window()` | `(date, date)` | Event start/end. Falls back to min/max `Match.scheduled_at`, then to today; clamps end ≥ start. |
| `get_max_concurrent_players(default=60)` | `int` | Configured player capacity, or default when unset/non-positive. |
| `get_max_concurrent_stages(default=None)` | `int` | Configured stage capacity; falls back to the given default, then to the count of active stream rooms. |
| `get_volunteer_reminder_lead_minutes(default=60)` | `int` | How far ahead of a shift the reminder loop fires; default when unset/non-positive. |
| `get_tournament_hours()` | `dict[date, (time, time)]` | Per-day open/close windows (JSON-decoded; malformed entries skipped). |
| `get_tournament_window_for_date(d)` | `(time, time) \| None` | Open/close window for one date, or `None` when unconfigured. |
| `set_tournament_hours(mapping, actor)` | `None` | Persist `{date: (open_HH:MM, close_HH:MM)}`; validates HH:MM format and that close is after open (`ValueError`). |

Consumers: `ReportsService`, `MatchSuggestionService`, `volunteer_reminder`, `DiscordRoleMappingService`, and `pages/admin_tabs/reports/` (`shared.py`, `capacity.py`, `dashboard.py`).

### telemetry_service.py — TelemetryService

Engagement telemetry — *how* people use the tool, as opposed to the deliberate actions `AuditService` records. Three best-effort, non-blocking capture points, all honoring the `TELEMETRY_ENABLED` kill-switch and swallowing/logging their own errors so telemetry never breaks a render or a mutating call: `record_event(event)` (registered on the [event bus](../features/event-system.md) in `main.py`, mirroring every published domain event into a `domain` `TelemetryEvent` row on the dispatch worker), `track_page_view(...)` (called from the `protected_page` decorator on every authenticated page load, capturing path + bounded query params + browser session id), and `track_interaction(...)` (curated UI actions, e.g. `report.viewed` from the reports dispatcher). Reads power the Staff-only engagement report and are gated on `AuthService.is_staff` (`ensure`, like `WebhookService`): `engagement_summary`, `top_paths`, `top_event_types`, `top_users`, `list_events`, `count_events` — aggregations run in the database via `TelemetryRepository`. `TelemetryCategory` (`page`/`interaction`/`domain`) and `TelemetryEventType` (`page.view`/`report.viewed`/`report.exported`) name the buckets and engagement event types. Collaborators: `TelemetryRepository`, `AuthService`, `application.events`, `application.utils.environment.telemetry_enabled`. Consumers: `main.py` (bus subscription), `middleware/auth.py` (page views), `pages/admin_tabs/reports/` (`__init__.py` interaction, `telemetry.py` report). Feature doc: [telemetry.md](../features/telemetry.md).

### tenant_service.py — TenantService

The tenancy machinery: resolves a `Tenant` from a URL slug (`TenantMiddleware`), a custom domain, or a Discord guild id (bot routing), and backs the `/platform` super-admin surface. Resolution lookups are cached in-process (single worker) and the whole cache is dropped on any write. CRUD and grant operations are **super-admin gated** (`AuthService.is_super_admin` via `ensure`) and run with *no* tenant context, so they pass explicit ids to the repositories rather than relying on the ambient tenant — their audit rows are platform-level (`tenant=NULL`). Slugs are validated against `_SLUG_RE` and a `_RESERVED_SLUGS` set (the platform's own top-level paths). Feature doc: [multitenancy.md](../features/multitenancy.md).

| Method | Returns | Description |
|---|---|---|
| `get_by_id(tenant_id)` / `get_by_slug(slug)` / `get_by_domain(domain)` | `Tenant \| None` | Resolution lookups; `get_by_slug` is cached. |
| `list_tenants_for_guild(guild_id)` | `list[Tenant]` | Every tenant linked to a Discord guild (a guild may back several); cached. The bot fans out over the result. |
| `list_tenants()` | `list[Tenant]` | All tenants (platform admin table + community picker). |
| `create_tenant(actor, *, name, slug, domain=None, discord_guild_id=None, ...)` | `Tenant` | Super-admin create; validates slug/domain uniqueness and format; audited `tenant.created`. |
| `update_tenant(actor, tenant, **fields)` | `Tenant` | Super-admin partial update; re-validates slug/domain; audited `tenant.updated`. |
| `is_member(user_id, tenant_id)` | `bool` | Membership check (`TenantMembership` lookup; used by `/platform` membership management). |
| `add_member(actor, user, tenant_id)` / `list_members(tenant_id)` / `list_memberships_for_user(user)` | — / `list` / `list` | Membership management. |
| `grant_super_admin(actor, user)` / `revoke_super_admin(actor, user)` | `None` | Super-admin gated; grant/revoke the global `SUPER_ADMIN` role (`UserRole` with `tenant=NULL`); audited `super_admin.*`. |
| `bootstrap_staff(actor, tenant_id, user)` | `None` | Grant a tenant its first `STAFF` + membership. |
| `slugify(name)` (module fn) | `str` | Best-effort URL-safe slug suggestion from a display name. |

Collaborators: `TenantRepository`, `TenantMembershipRepository`, `UserRoleRepository`, `AuthService`, `AuditService`. Consumers: `middleware/tenant.py` (slug→tenant resolution), `pages/platform.py` (tenant CRUD UI), `pages/home.py` (community picker), `application/services/discord_service.py` + `discord_role_mapping_service.py` (guild→tenant routing).

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

### twitch_service.py — TwitchService

Coordinates the Twitch account-linking integration: a logged-in user completes a one-time Twitch OAuth login so we can record their verified Twitch identity (id / login / display name) on their `User`. Identity only — the user's Twitch access token is used once during linking and discarded. Mock mode is gated by [`MOCK_TWITCH`](#mock_twitchpy).

| Method | Returns | Description |
|---|---|---|
| `is_configured()` (static) | `bool` | OAuth app credentials are present (or mock is on). |
| `player_authorize_url(state)` (static) | `str` | Twitch OAuth authorize URL to redirect the browser to. |
| `redirect_uri()` (static) | `str` | The registered OAuth redirect URI (`TWITCH_REDIRECT_URI` or derived from `BASE_URL`). |
| `exchange_player_code(code)` | `{user_id, username, display_name}` | Exchange a user's auth code and return their identity (token used once, discarded). |
| `record_player_link(user, twitch_user_id, twitch_username, actor)` | `None` | Persist the linked Twitch identity; rejects ids already linked elsewhere (`ValueError`); audits `twitch.linked`. |
| `unlink_player(user, actor)` | `None` | Clear a user's Twitch link; audits `twitch.unlinked`. |

Collaborators: `AuditService`, [`twitch_client.py`](#twitch_clientpy) (`TwitchClient`/`MockTwitchClient`), [`mock_twitch.py`](#mock_twitchpy). Consumers: the Twitch OAuth pages ([`pages/twitch_oauth.py`](../../pages/twitch_oauth.py)) and the profile "Link Twitch" card ([`pages/home_tabs/twitch_link_section.py`](../../pages/home_tabs/twitch_link_section.py)).

### user_service.py — UserService

User lookup, profile edits (self- and admin-driven), activation, global role grants, and tournament enrollment management. Audited under `user.*`; role grants gated by `can_grant_roles`, admin fields by `is_staff`.

| Method | Returns | Description |
|---|---|---|
| `get_user_by_discord_id(discord_id)` | `User \| None` | Lookup by Discord id. |
| `get_current_user_from_storage(storage_discord_id)` | `User \| None` | Resolve a storage-held Discord id to a `User` (`UserService` variant of the module-level `get_user_from_discord_id`). |
| `provision_from_discord_login(discord_id, username)` | `(User, bool)` | Get-or-create the account for a real Discord OAuth login; returns `(user, created)`. A new account writes a self-attributed `user.provisioned` audit entry; an existing active account has its username synced (inactive accounts are returned untouched for the caller to reject). |
| `create_mock_login_user(discord_id, username, display_name=None, role_values=None)` | `User` | Dev-only (`MOCK_DISCORD`) account + role provisioning for the mock login picker; no permission check, but writes a `user.provisioned` audit entry (`source: mock_login`). |
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

## Volunteering

The onsite volunteer subsystem spans five services plus a background reminder loop. The data flow is: any user opts in (`VolunteerProfileService`) and declares availability (`VolunteerAvailabilityService`); coordinators define positions (`VolunteerPositionService`) and generate/assign shifts (`VolunteerScheduleService`), optionally seeding a draft from the pool (`VolunteerAutoscheduleService`); the `volunteer_reminder` loop DMs upcoming-shift reminders. All coordinator-side mutations are gated by `AuthService.can_manage_volunteers` and audited under `volunteer.*`.

### volunteer_profile_service.py — VolunteerProfileService

Opt-in lifecycle (self-service for any logged-in user) plus the assignable-volunteer pool the coordinator UI and auto-scheduler read.

| Method | Returns | Description |
|---|---|---|
| `get_or_create(user)` | `VolunteerProfile` | The user's profile, creating an empty one if needed. |
| `is_opted_in(user)` | `bool` | Whether the user has an `opted_in_at` timestamp. |
| `opt_in(user, note=None)` | `VolunteerProfile` | Stamp `opted_in_at` (idempotent) and optionally set the note; audits `volunteer.opted_in`. |
| `opt_out(user)` | `VolunteerProfile` | Clear `opted_in_at`; audits `volunteer.opted_out` only when it was set. |
| `update_note(user, note)` | `VolunteerProfile` | Set the free-text note (no audit). |
| `assignable_volunteers()` | `list[User]` | All opted-in users, ordered by preferred name. |

Collaborators: `VolunteerProfileRepository`, `AuditService`.

### volunteer_availability_service.py — VolunteerAvailabilityService

Self-service availability for opted-in volunteers, plus the coordinator-picker lookups that flag who is available for a shift. Windows carry a `VolunteerAvailabilityStatus` and are replaced wholesale on each save. (Mirrors `PlayerAvailabilityService` but requires an active volunteer opt-in.)

| Method | Returns | Description |
|---|---|---|
| `availability_for(user)` | `list[VolunteerAvailability]` | The user's declared windows. |
| `set_windows(user, windows)` | `list[VolunteerAvailability]` | Replace availability with `(starts_at, ends_at, status, note)` tuples; **requires the user to be opted in** (`ValueError`); each window must end after it starts; transactional. Audits `volunteer.availability_updated`. |
| `clear(user)` | `None` | Delete all windows; audits `volunteer.availability_updated` with `window_count: 0`. |
| `availability_map(user_ids, start, end)` | `dict[int, list[VolunteerAvailability]]` | user_id → windows overlapping `[start, end]`. |
| `covers(windows, start, end)` (static) | `VolunteerAvailabilityStatus \| None` | Strongest signal for a shift (unavailable > preferred > available; `None` if nothing overlaps). |
| `effective_segments(windows, start, end)` (static) | `list[(datetime, datetime, status \| None)]` | Split `[start, end]` into maximal constant-availability segments. |

Collaborators: `VolunteerAvailabilityRepository`, `VolunteerProfileRepository`, `AuditService`. Consumers: `VolunteerScheduleService` (assignment availability warnings) and `VolunteerAutoscheduleService` (candidate scoring).

### volunteer_position_service.py — VolunteerPositionService

CRUD for the arbitrary, coordinator-defined position/job list. Positions optionally configure staggered rolling shifts via `shift_length_minutes`/`stagger_minutes` (both set or both blank).

| Method | Returns | Description |
|---|---|---|
| `list_all()` / `list_active()` | `list[VolunteerPosition]` | All positions, or only active ones. |
| `get(position_id)` | `VolunteerPosition \| None` | Lookup by id. |
| `create(actor, name, description=None, color=None, display_order=0, is_active=True, shift_length_minutes=None, stagger_minutes=None)` | `VolunteerPosition` | Coordinator-only; non-empty unique name required; validates the stagger config (positive, stagger ≤ shift length). Audits `volunteer.position_created`. |
| `update(actor, position, **fields)` | `VolunteerPosition` | Coordinator-only partial update; re-validates name uniqueness and stagger config when those fields change. Audits `volunteer.position_updated`. |
| `delete(actor, position)` | `None` | Coordinator-only; audits `volunteer.position_deleted`. |

Collaborators: `VolunteerPositionRepository`, `AuthService`, `AuditService`.

### volunteer_schedule_service.py — VolunteerScheduleService

Core shift/assignment operations: creating shifts (including bulk day generation with optional staggered rolling shifts), placing and removing volunteers, self-acknowledgment, and coverage. Mirrors the crew signup/approve/acknowledge flow for Discord notifications. Assignment acknowledgment timestamps are stamped in Eastern.

| Method | Returns | Description |
|---|---|---|
| `list_shifts_for_window(start, end)` | `list[VolunteerShift]` | Shifts overlapping `[start, end]`. |
| `get_shift(shift_id)` | `VolunteerShift \| None` | Lookup by id. |
| `create_shift(actor, position_id, starts_at, ends_at, label=None, slots_needed=1, notes=None)` | `VolunteerShift` | Coordinator-only; requires end after start and ≥1 slot. Audits `volunteer.shift_created`. |
| `generate_day_shifts(actor, date_str, position_ids, blocks)` | `list[VolunteerShift]` | Coordinator-only; create a day's shifts from `(label, start_HHMM, end_HHMM)` blocks (a block ending ≤ its start crosses midnight). Staggered positions instead get rolling shifts spanning the day window. Transactional; audits `volunteer.shift_created`. |
| `update_shift(actor, shift, **fields)` | `VolunteerShift` | Coordinator-only partial update; same end>start / slots≥1 validation. Audits `volunteer.shift_updated`. |
| `delete_shift(actor, shift)` | `None` | Coordinator-only; audits `volunteer.shift_deleted`. |
| `reset_all_shifts(actor)` | `int` | Coordinator-only; delete every shift; returns the count; audits `volunteer.shifts_reset`. |
| `assign(actor, shift, user, *, auto_generated=False, notify=True)` | `(VolunteerAssignment, list[str])` | Coordinator-only. Hard-fails (`ValueError`) on duplicate or overlapping assignment; returns soft warnings for overfilled shifts and stated-unavailability. Enqueues an acknowledgment-request DM unless auto-generated. Audits `volunteer.assigned`. |
| `unassign(actor, assignment)` | `None` | Coordinator-only; audits `volunteer.unassigned`. |
| `acknowledge(assignment_id, user)` | `VolunteerAssignment` | Self-acknowledge (idempotent); rejects other users' assignments (`ValueError`). Audits `volunteer.acknowledged`. |
| `assignments_for_user(user, upcoming_after=None)` | `list[VolunteerAssignment]` | A user's assignments, optionally only those starting after a cutoff. |
| `coverage(start, end)` | `list[dict]` | Per-shift filled/needed counts (flagging understaffed shifts). |

Collaborators: `VolunteerShiftRepository`, `VolunteerAssignmentRepository`, `VolunteerPositionRepository`, `VolunteerAvailabilityService`, `DiscordService` (via `discord_queue`), `AuditService`, `AuthService`, [`discord_messages.py`](#discord_messagespy), [`timezone.py`](#timezonepy). Consumers: the coordinator schedule tab, the volunteer's own shift list, and `discordbot/` (the volunteer-acknowledge DM button).

### volunteer_autoschedule_service.py — VolunteerAutoscheduleService

Greedy/heuristic draft generator. Fills open shift slots from the opted-in pool using qualifications, availability, no-overlap, and hour load-balancing, producing `auto_generated` assignments the coordinator then reviews. Candidate ranking prefers qualified volunteers, then `PREFERRED`/`AVAILABLE` availability, then fewest assigned hours, then name.

| Method | Returns | Description |
|---|---|---|
| `generate_draft(actor, start, end, *, position_ids=None, clear_existing_drafts=True)` | `dict` | Coordinator-only; build a draft over `[start, end]` (optionally one or more positions); returns `{created, unfilled, pool_size}`. Transactional; audits `volunteer.draft_generated`. |
| `clear_draft(actor, start, end)` | `int` | Coordinator-only; remove auto-generated assignments in the window; returns the count; audits `volunteer.draft_cleared`. |

Collaborators: `VolunteerShiftRepository`, `VolunteerAssignmentRepository`, `VolunteerProfileService`, `VolunteerAvailabilityService`, `VolunteerScheduleService`, `AuthService`, `AuditService`; reads `VolunteerQualification` directly. Consumers: the coordinator auto-fill action.

### volunteer_qualification_service.py — VolunteerQualificationService

Reads and replaces the set of positions a volunteer is qualified to fill. Qualifications are used by `VolunteerAutoscheduleService` when scoring and ranking candidates for a shift. All writes are gated by `AuthService.can_manage_volunteers` and audited under `volunteer.*`.

| Method | Returns | Description |
|---|---|---|
| `get_qualified_position_ids(user)` | `Set[int]` | Position ids the user is qualified for. |
| `get_qualified_user_ids_for_position(position_id)` | `Set[int]` | User ids qualified for a position. |
| `set_qualifications(actor, user, position_ids)` | `None` | Coordinator-only; replace the user's qualification set atomically; audits `volunteer.qualifications_updated`. |

Collaborators: `VolunteerQualificationRepository`, `AuthService`, `AuditService`. Consumers: the coordinator volunteer management tab, `VolunteerAutoscheduleService` (reads qualifications directly from the model for performance).

### volunteer_reminder.py — module functions

A lightweight background worker (modeled on `discord_queue`) that periodically finds upcoming volunteer assignments within the configured lead time, enqueues a reminder DM with an acknowledge button, and stamps `reminder_sent_at` so each assignment is reminded only once (the stamp is written before the DM so a delivery failure or restart cannot re-fire). Module constant: `TICK_SECONDS = 60`.

| Function | Returns | Description |
|---|---|---|
| `start()` | `None` | Create the loop task on the running event loop (idempotent). Called from `main.py` lifespan startup. |
| `stop()` (async) | `None` | Cancel the loop and await its exit. Called from lifespan shutdown. |

Collaborators: `VolunteerAssignmentRepository`, `SystemConfigService.get_volunteer_reminder_lead_minutes`, `DiscordService` (via `discord_queue`), [`discord_messages.py`](#discord_messagespy), [`timezone.py`](#timezonepy). Imported as a module (`from application.services import volunteer_reminder`).

### web_push_service.py — WebPushService

Per-device browser push notifications ("Device Notifications"): subscription CRUD (audited via `AuditActions.WEB_PUSH_*`) plus the encrypted delivery path. `mirror_dm(discord_id, message)` is enqueued fire-and-forget from `DiscordService.send_dm` onto the event dispatch worker for every outgoing DM (never raises; no-op unless VAPID is configured and the user has subscriptions); `notify_user(user, *, title, body, navigate=None)` targets one user directly. Sends the Declarative Web Push JSON shape (`web_push: 8030`) — rendered natively on Safari/iOS 18.4+ and by the `static/sw.js` `push` handler elsewhere — encrypted per RFC 8291 (in a worker thread) with a per-origin-cached VAPID `Authorization` header, delivered concurrently per user through a shared `httpx.AsyncClient` (closed via `aclose_http_client()` in the app lifespan). Prunes subscriptions the push service reports gone (404/410). Configured by `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` (resolved once per env tuple, so misconfiguration warns once, not per DM); `is_configured()` / `get_public_key()` gate the settings UI. Collaborators: `WebPushRepository`, `AuditService`, [`web_push.py`](#web_pushpy), `application.utils.environment.get_base_url`. Feature doc: [web-push.md](../features/web-push.md).

### webhook_service.py — WebhookService

Staff-managed outbound webhooks: CRUD (all gated on `AuthService.is_staff` and audited via `AuditActions.WEBHOOK_*`) plus the delivery path. `deliver_event(event)` is registered on the [event bus](../features/event-system.md) in `main.py`; for each active webhook subscribed to the event it enqueues `_deliver_one` onto the event dispatch worker, which POSTs an HMAC-SHA256-signed JSON body via `httpx.AsyncClient` (bounded retry + `WebhookDelivery` logging). Validates `https://` + SSRF host rules (production) and event-type names; generates the signing secret with `secrets.token_urlsafe`. Collaborators: `WebhookRepository`, `WebhookDeliveryRepository`, `AuditService`, `AuthService`, `application.events`.

> The event bus itself (`application/events/`) — the publish/subscribe backbone these deliveries hang off — is documented in [event-system.md](../features/event-system.md).

## Utilities (`application/utils/`)

### challonge_client.py

Thin async `aiohttp` wrapper over the Challonge v2.1 (JSON:API) endpoints the integration needs, plus OAuth token exchange/refresh ([challonge_client.py](../../application/utils/challonge_client.py)). Returns **normalized** Python dicts so `ChallongeService` never sees the JSON:API wire shape. Authenticated calls obtain a bearer token via an injected `token_provider` callback and transparently refresh-on-401 and retry once; an optional `on_request` hook counts real outbound requests for quota tracking. Module constants: `AUTHORIZE_URL`, `TOKEN_URL`, `BASE_URL`.

| Member | Returns | Description |
|---|---|---|
| `build_authorize_url(client_id, redirect_uri, scope, state)` (function) | `str` | Challonge OAuth authorize URL to redirect the browser to. |
| `ChallongeAPIError` (exception) | — | Raised on an API error or unexpected payload. |
| `ChallongeClient.exchange_code(code, redirect_uri)` | `dict` | Exchange an auth code for a token payload. |
| `ChallongeClient.refresh(refresh_token)` | `dict` | Exchange a refresh token for a new token payload. |
| `ChallongeClient.get_me(access_token)` | `{user_id, username}` | The authenticated account identity for a raw token. |
| `ChallongeClient.get_tournament(tournament_id)` | `{id, name, url, state}` | A tournament's summary. |
| `ChallongeClient.list_participants(tournament_id)` | `list[dict]` | Normalized participant records. |
| `ChallongeClient.list_matches(tournament_id)` | `list[dict]` | Normalized match records. |
| `ChallongeClient.get_tournament_full(tournament_id)` | `{tournament, participants, matches}` | Tournament plus embedded participants and matches in one request. |
| `ChallongeClient.update_match(tournament_id, match_id, winner_participant_id, loser_participant_id, winner_score='1', loser_score='0')` | `None` | Report a match result (winner flagged `advancing`). |
| `MockChallongeClient` | — | `MOCK_CHALLONGE` stub returning a canned 4-player single-elim bracket so local dev can click through connect/link/sync/schedule/push. |

### twitch_client.py

Thin async `aiohttp` wrapper over the two Twitch endpoints the account-linking flow needs — the OAuth token exchange and the Helix `users` lookup ([twitch_client.py](../../application/utils/twitch_client.py)). Returns a **normalized** identity dict so `TwitchService` never sees the wire shape. Module constants: `AUTHORIZE_URL`, `OAUTH_EXCHANGE_URL`, `USERS_URL`.

| Member | Returns | Description |
|---|---|---|
| `build_authorize_url(client_id, redirect_uri, scope, state)` (function) | `str` | Twitch OAuth authorize URL to redirect the browser to. |
| `TwitchAPIError` (exception) | — | Raised on an API error or unexpected payload. |
| `TwitchClient.exchange_code(code, redirect_uri)` | `dict` | Exchange an auth code for a token payload. |
| `TwitchClient.get_me(access_token)` | `{user_id, username, display_name}` | The authenticated account identity for a raw token (sends the required `Client-Id` header). |
| `MockTwitchClient` | — | `MOCK_TWITCH` stub returning a deterministic canned identity (chosen via `MOCK_TWITCH_IDENTITY`) so local dev can click through link/unlink. |

### csv_export.py

CSV rendering for the report tables ([csv_export.py](../../application/utils/csv_export.py)).

| Function | Returns | Description |
|---|---|---|
| `rows_to_csv_bytes(columns, rows)` | `bytes` | Render NiceGUI-style column descriptors (`name`, `label`, optional `hidden`) plus row dicts as UTF-8-with-BOM CSV; hidden columns are skipped. |
| `timestamped_filename(prefix, ext='csv')` | `str` | `prefix-20251130T143015Z.csv`-style download filename (UTC stamp). |

**CSV-injection safety:** every non-numeric cell whose stripped value starts with `=`, `+`, `-`, or `@` is prefixed with an apostrophe so spreadsheet apps treat it as text rather than a formula. Numbers are exempt (so negative values export cleanly); booleans render as `true`/`false`; datetimes as ISO strings; `None` as empty.

### discord_messages.py

The single source of all Discord DM and ephemeral message text ([discord_messages.py](../../application/utils/discord_messages.py)). Service and handler code imports builder functions and constants from here rather than inlining strings, so wording stays consistent and centrally editable. Messages deliberately never expose raw match id numbers — a match is identified by players, scheduled time, and stage.

Notable members:

- **Shared constants:** `MSG_NO_ACCOUNT`, `MSG_UNEXPECTED_ERROR_MATCH`, `MSG_UNEXPECTED_ERROR_CREW`.
- **Match scheduling DMs** (sent by `MatchScheduleService`/`MatchService`): `scheduled_dm`, `rescheduled_dm`, `acknowledgment_request_dm`, `checked_in_dm`, `state_changed_dm`, `stream_candidate_dm`, `seed_dm`.
- **Crew DMs** (`CrewService`): `crew_assignment_dm`.
- **Volunteer DMs** (`VolunteerScheduleService`, `volunteer_reminder`): `volunteer_assignment_dm`, `volunteer_reminder_dm`, `volunteer_ack_confirmation`.
- **Ephemeral button replies** (`discordbot/`): `match_ack_confirmation`, `crew_ack_confirmation`, `crew_signup_confirmation`, `unwatch_confirmation`.

All builders are pure functions returning `str`; optional fields passed as `None`/`''` are omitted from the rendered message.

### easter_eggs.py

A small bank of trivia strings surfaced in incidental UI spots ([easter_eggs.py](../../application/utils/easter_eggs.py)). `random_fact() -> str` returns a uniformly-random fact drawn from the combined topic lists (roller coasters, cats, Balatro, Diablo, WoW, Hamilton, Cloverpit). No external dependencies or side effects.

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

### mock_challonge.py

The Challonge counterpart to `mock_discord` ([mock_challonge.py](../../application/utils/mock_challonge.py)). Lets local development exercise the full Challonge flow (connect, link, sync, schedule, push results) without a real OAuth app or bracket.

| Function | Returns | Description |
|---|---|---|
| `is_mock_challonge()` | `bool` | True when `MOCK_CHALLONGE` is `1`/`true`/`yes`. Because it fakes an authenticated Challonge connection, it **raises `RuntimeError` when enabled while `ENVIRONMENT=production`**. |

`ChallongeService` reads this to choose `MockChallongeClient` over `ChallongeClient` and to report `is_configured()` as true in mock mode.

### mock_twitch.py

The Twitch counterpart to `mock_challonge` ([mock_twitch.py](../../application/utils/mock_twitch.py)). Lets local development exercise the full Twitch link/unlink flow without a real OAuth app.

| Function | Returns | Description |
|---|---|---|
| `is_mock_twitch()` | `bool` | True when `MOCK_TWITCH` is `1`/`true`/`yes`. Because it fakes a verified Twitch identity, it **raises `RuntimeError` when enabled while `ENVIRONMENT=production`**. |

`TwitchService` reads this to choose `MockTwitchClient` over `TwitchClient` and to report `is_configured()` as true in mock mode.

### qrcode_util.py

QR code generation for equipment assets ([qrcode_util.py](../../application/utils/qrcode_util.py)). Each code encodes the absolute URL of an asset's detail page (`{BASE_URL}/equipment/{asset_id}`, login required) so scanning jumps straight to it.

| Function | Returns | Description |
|---|---|---|
| `asset_url(asset_id)` | `str` | The asset's absolute detail-page URL. |
| `asset_qr_png_bytes(asset_id)` | `bytes` | The QR code rendered as PNG bytes. |
| `asset_qr_data_uri(asset_id)` | `str` | The QR code as a `data:image/png;base64` URI for inline `<img>` display. |

### sentry.py

Sentry error-monitoring initialization ([sentry.py](../../application/utils/sentry.py)). Wires the Sentry Python SDK into the process; a no-op unless `SENTRY_DSN` is set, so local dev and tests are unaffected. Once initialized it auto-instruments FastAPI/Starlette and stdlib `logging`, capturing unhandled exceptions and `logger.error`/`logger.exception` records across the request path, NiceGUI pages, and the Discord bot.

| Function | Returns | Description |
|---|---|---|
| `init_sentry()` | `None` | Initialize the SDK when `SENTRY_DSN` is configured; must run before the FastAPI app/middleware are built. Sets `environment` from `get_environment()`, `send_default_pii=False`, an optional `SENTRY_TRACES_SAMPLE_RATE`, and a `before_send` hook that scrubs `Authorization`/`Cookie`/`Set-Cookie`/`X-API-Key` headers and cookies from every outgoing event. |

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

### web_push.py

Pure Web Push protocol primitives — no I/O, no ORM ([web_push.py](../../application/utils/web_push.py)). Used by `WebPushService`; pinned to the RFC 8291 Appendix A test vector in `tests/test_web_push_protocol.py`.

| Function | Returns | Description |
|---|---|---|
| `encrypt_payload(plaintext, p256dh, auth)` | `bytes` | RFC 8291 `aes128gcm` message body encrypted to the subscription's client keys. |
| `vapid_authorization(endpoint, private_key, subject)` | `str` | `vapid t=<ES256 JWT>, k=<pubkey>` Authorization header value (RFC 8292). |
| `generate_vapid_keys()` | `(str, str)` | Fresh `(private, public)` VAPID keypair, base64url (see `scripts/generate_vapid_keys.py`). |
| `load_vapid_private_key(value)` | `EllipticCurvePrivateKey` | Parse the base64url raw 32-byte `VAPID_PRIVATE_KEY`. |
| `public_key_b64url(private_key)` | `str` | Derived `applicationServerKey` browsers subscribe with. |
| `b64url_encode(bytes)` / `b64url_decode(str)` | — | Padding-tolerant base64url helpers. |

## Testing the service layer

Service tests live in `tests/services/` — broadly one `test_<service>.py` module per service (covering audit, auth, challonge, crew, discord role-mapping/member-sync, equipment, feedback, match/match-schedule/match-watcher, reports, stream room, system config, tournament/tournament-notification, triforce text, user, and volunteer scheduling). Several modules — including `discord_queue`, `discord_service`, `seedgen_service`, the availability/suggestion services, `volunteer_reminder`, and the volunteer profile/position/availability/autoschedule services — have no dedicated suite. Key fixtures:

- [`tests/conftest.py`](../../tests/conftest.py) provides a function-scoped `db` fixture: a fresh in-memory SQLite database per test via `Tortoise.init(db_url="sqlite://:memory:")` + `generate_schemas()`, torn down by closing connections — no state leaks between tests.
- [`tests/services/conftest.py`](../../tests/services/conftest.py) adds an autouse `stub_discord_queue` fixture that monkeypatches `discord_queue.enqueue` to capture coroutines instead of running them, letting tests assert that notifications were enqueued while closing the coroutines to avoid "never awaited" warnings.
- `asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions need no decorator.

For the full development workflow (running tests, CI, suite scope and known gaps) see [development.md](../development.md).
