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
| `FeatureFlagService` | [feature_flag_service.py](../../application/services/feature_flag_service.py) | Per-tenant feature gating: effective-state resolution (override → group → default), group (tier) CRUD + assignment, availability/enable writes | [feature-flags.md](../features/feature-flags.md) |
| `FeedbackService` | [feedback_service.py](../../application/services/feedback_service.py) | In-app feedback submission and review | — |
| `MatchDisplayService` | [match_display_service.py](../../application/services/match_display_service.py) | Read + format matches into table-row dicts (filters, display shape) | [frontend.md](frontend.md) |
| `MatchScheduleService` | [match_schedule_service.py](../../application/services/match_schedule_service.py) | Match lifecycle transitions, seed rolls, DM fan-out | [discord-notifications.md](../features/discord-notifications.md) |
| `MatchService` | [match_service.py](../../application/services/match_service.py) | Match CRUD, lifecycle, station/stage, acknowledgments | [match-acknowledgment.md](../features/match-acknowledgment.md) |
| `MatchSuggestionService` | [match_suggestion_service.py](../../application/services/match_suggestion_service.py) | Suggest match start times that minimise venue occupancy | — |
| `MatchWatcherService` | [match_watcher_service.py](../../application/services/match_watcher_service.py) | Watch/unwatch matches for DM updates | [match-watcher.md](../features/match-watcher.md) |
| `PlayerAvailabilityService` | [player_availability_service.py](../../application/services/player_availability_service.py) | Player-declared availability windows | — |
| `availability_windows` (module) | [availability_windows.py](../../application/services/availability_windows.py) | Pure window algorithms (`covers`, `effective_segments`, `group_by_user`) shared by the player + volunteer availability services | — |
| `PresetService` | [preset_service.py](../../application/services/preset_service.py) | Tenant-authored seed-rolling presets (CRUD + built-in import) | [seed-generation.md](seed-generation.md#presets-db-backed) |
| `ReportsService` | [reports_service.py](../../application/services/reports_service.py) | Capacity, operations, crew, and stage reports | [admin-reports.md](../features/admin-reports.md) |
| `reporting_shared` (module) | [reporting_shared.py](../../application/services/reporting_shared.py) | Shared reporting constants (`DEFAULT_MATCH_DURATION_MIN`, `ON_TIME_THRESHOLD_MIN`) + `eastern`/`window_hours` helpers used by both Reports and Insights (so on-time % can't drift) | — |
| `SeedGenerationService` | [seedgen_service.py](../../application/services/seedgen_service.py) | Randomizer seed generation | [seed-generation.md](seed-generation.md) |
| `StreamRoomService` | [stream_room_service.py](../../application/services/stream_room_service.py) | Stream room (stage) CRUD | — |
| `SystemConfigService` | [system_config_service.py](../../application/services/system_config_service.py) | Typed access to `SystemConfiguration` keys | [admin-reports.md](../features/admin-reports.md) |
| `TelemetryService` / `TelemetryCategory` / `TelemetryEventType` | [telemetry_service.py](../../application/services/telemetry_service.py) | Engagement telemetry capture + Staff-gated engagement report | [telemetry.md](../features/telemetry.md) |
| `TenantService` | [tenant_service.py](../../application/services/tenant_service.py) | Tenant resolution (cached slug/guild/domain lookup), tenant CRUD, membership, super-admin grant | [multitenancy.md](../features/multitenancy.md) |
| `TenantThemeService` | [tenant_theme_service.py](../../application/services/tenant_theme_service.py) | Per-tenant brand palette (STAFF-editable colours on `Tenant.config['theme']`) | [frontend.md](../reference/frontend.md#per-tenant-theme-colours) |
| `TournamentNotificationService` | [tournament_notification_service.py](../../application/services/tournament_notification_service.py) | Per-tournament notification preferences | [tournament-notifications.md](../features/tournament-notifications.md) |
| `TournamentService` | [tournament_service.py](../../application/services/tournament_service.py) | Tournament CRUD, TA/CC membership | — |
| `TriforceTextService` | [triforce_text_service.py](../../application/services/triforce_text_service.py) | Triforce text submission and moderation | [triforce-texts.md](../features/triforce-texts.md) |
| `TwitchService` | [twitch_service.py](../../application/services/twitch_service.py) | Twitch account-linking OAuth (verified identity capture) | — |
| `RacetimeService` | [racetime_service.py](../../application/services/racetime_service.py) | racetime.gg account-linking OAuth (verified identity capture) | — |
| `IdentityLinkService` / `IdentityLinkProvider` | [identity_link_service.py](../../application/services/identity_link_service.py) | Provider-parameterized account-linking engine (redirect/authorize/exchange/record/unlink + duplicate-account guard) that `TwitchService` and `RacetimeService` both delegate to | — |
| `RacetimeBotService` | [racetime_bot_service.py](../../application/services/racetime_bot_service.py) | Platform CRUD + tenant authorization grants for shared racetime bots | — |
| `RaceRoomProfileService` | [race_room_profile_service.py](../../application/services/race_room_profile_service.py) | SYNC_ADMIN CRUD for reusable racetime room settings | — |
| `RacetimeRoomService` | [racetime_room_service.py](../../application/services/racetime_room_service.py) | Race-room record lookup (unscoped by-slug routing) + status writes | — |
| `RaceRoomService` | [race_room_service.py](../../application/services/race_room_service.py) | Racetime room lifecycle mapped onto a `Match` (create/open/seed/finish/cancel + result capture) | — |
| `SpeedGamingETLService` | [speedgaming_etl_service.py](../../application/services/speedgaming_etl_service.py) | One-way SpeedGaming→SGLMan schedule ETL (extract/transform/load into `Match`) | — |
| `SpeedGamingSyncService` | [speedgaming_sync_service.py](../../application/services/speedgaming_sync_service.py) | Tenant-facing SpeedGaming event-link CRUD + on-demand "sync now" | — |
| `UserService` | [user_service.py](../../application/services/user_service.py) | User CRUD, profiles, roles, enrollments | [role-based-auth.md](../features/role-based-auth.md) |
| `VolunteerAutoscheduleService` | [volunteer_autoschedule_service.py](../../application/services/volunteer_autoschedule_service.py) | Greedy draft generator for the volunteer schedule | — |
| `VolunteerAvailabilityService` | [volunteer_availability_service.py](../../application/services/volunteer_availability_service.py) | Volunteer-declared availability windows | — |
| `VolunteerPositionService` | [volunteer_position_service.py](../../application/services/volunteer_position_service.py) | Coordinator-defined volunteer position CRUD | — |
| `VolunteerQualificationService` | [volunteer_qualification_service.py](../../application/services/volunteer_qualification_service.py) | Read and set which positions a volunteer is qualified to fill | — |
| `VolunteerProfileService` | [volunteer_profile_service.py](../../application/services/volunteer_profile_service.py) | Volunteer opt-in lifecycle and assignable pool | — |
| `volunteer_reminder` (module) | [volunteer_reminder.py](../../application/services/volunteer_reminder.py) | Background loop sending shift-reminder DMs | — |
| `VolunteerScheduleService` | [volunteer_schedule_service.py](../../application/services/volunteer_schedule_service.py) | Volunteer shifts, assignments, acknowledgment, coverage | — |

All classes and `get_user_from_discord_id` are re-exported from [`application/services/__init__.py`](../../application/services/__init__.py); the helper modules `discord_queue`, `volunteer_reminder`, `async_qualifier_access`, `async_qualifier_scoring`, `availability_windows`, and `reporting_shared` are imported as modules (`from application.services import discord_queue`). `NotFoundError` / `require_found` (from [`application/errors.py`](../../application/errors.py)) are also re-exported here.

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
| `is_system(user)` | `bool` | Field check (`User.is_system`) — the reserved automation actor. Sync (no DB). The `can_manage_*`/`can_admin_qualifier` gates short-circuit on it so workers/bots never hit a `PermissionError`. |
| `can_manage_presets(user)` | `bool` | System actor, super-admin, Staff, or `PRESET_MANAGER` — gates seed-rolling preset management (online tournaments). |
| `can_manage_sync(user)` | `bool` | System actor, super-admin, Staff, or `SYNC_ADMIN` — gates upstream sync config (SpeedGaming links, Discord events, racetime bot/room config). |
| `can_admin_qualifier(user, qualifier=None)` | `bool` | System actor, super-admin, Staff, `QUALIFIER_ADMIN`, or — when a `qualifier` is passed — a per-entity admin on its `admins` M2M. |
| `ensure(allowed, message="Permission denied")` | `None` | Raises `PermissionError(message)` when `allowed` is falsy; the standard gate inside mutating services. |

**Module-level helper:** `get_user_from_discord_id(discord_id) -> User | None` resolves a Discord id — typically `app.storage.user.get('discord_id')`, read in the page layer — to a `User` model (or `None` when logged out / deleted). Call it once at page entry and pass the result into the helpers above — don't re-resolve per check.

Consumers: `middleware/auth.py` (`protected_page` role enforcement), nearly every page and dialog (`pages/home.py`, `pages/admin.py`, `pages/admin_tabs/*`, `theme/dialog/*`, `theme/tables/*`), and all mutating services via `ensure`.

### oauth_handoff_service.py — module functions

Design B cross-host login handoff for custom tenant domains (`HOST_OAUTH_MODE=handoff`): Discord OAuth always completes on the platform host, which **mints** a short-lived (30s TTL), single-use, host-bound token and redirects to the target domain's `/session/claim`, which **claims** it and writes the host-local session. Only the nonce + host travel in the URL; identity (`discord_id`/username/avatar) stays server-side in a bounded in-process store (single-worker deployment precondition, like the tenant caches). Signed with `STORAGE_SECRET` via `itsdangerous`.

| Function | Returns | Description |
|---|---|---|
| `mint(*, discord_id, username, avatar, target_host, next_path, bind_commit=None)` | `str \| None` | Mint a handoff token bound to `target_host` (must already be a validated active tenant domain); `None` if the host won't normalize. `bind_commit` ties the token to the initiating browser (login-CSRF guard). |
| `claim(token, request_host)` | `dict \| None` | Validate + consume the token on `request_host`; returns the stored payload or `None` for invalid/expired/wrong-host/replayed tokens. Single-use — the nonce is popped regardless of outcome. |
| `reset()` | `None` | Clear the pending store (test isolation). |

Consumers: `pages/auth.py` (platform-host OAuth callback → mint; `/session/claim` route → claim). Detail: `docs/host-based-routing-plan.md`.

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

### discord_event_reconciler_service.py — DiscordEventReconcilerService (PR 8)

Mirrors the SGLMan schedule into a tenant guild's **Discord Scheduled Events** as idempotent reconciliation. `reconcile_tenant(tenant, *, actor, now=None)` reads the tenant's opted-in tournaments' scheduled matches in a forward window, then per match creates / updates (content-hash change) / leaves unchanged its `DiscordScheduledEvent` link, and cancels links whose source match finished or vanished. **Shared-guild safety**: the working set is only the tenant's own link rows (the repository is tenant-scoped), so a sibling tenant's event in a shared guild is never enumerated or cancelled; the target guild is the verified `Tenant.discord_guild_id`. Renders title/description from `{tournament}`/`{match}`/`{players}` templates. Audits + emits `discord_event.created`/`updated`/`cancelled` (the per-run summary is audit-only). Collaborators: `DiscordScheduledEventRepository`, `MatchRepository`, `DiscordService`, `AuditService`, event bus.

**discord_event_worker.py** — the reconcile background loop (peer of `speedgaming_sync_worker`). Every 5 min it scans (cross-tenant, unscoped) every tenant with a linked guild, then reconciles each inside `tenant_scope` as the system user. Idempotent, so an unchanged schedule is a cheap no-op. Started from the lifespan only when `DISCORD_EVENTS_SYNC_ENABLED` is on.

### discord_event_sync_service.py — DiscordEventSyncService (PR 8)

The human-driven surface over the reconciler, gated by `AuthService.can_manage_sync`. `list_tournaments` / `update_settings(actor, tournament_id, *, enabled, duration_minutes, title_template, description_template)` manage per-tournament opt-in (audits `discord_event.settings_updated`); `list_events` feeds the admin observability table; `reconcile_now(actor)` runs the reconciler for the ambient tenant on demand (raises `ValueError` when no guild is linked). Consumer: the admin **Discord Events** tab.

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
| `get_match_for_display(match_id)` | `dict \| None` | One match formatted for the UI (state, Eastern-formatted times, players with rank/station, acknowledgment summary, crew with approval/ack state, seed URL, and `is_racetime` — true when the tournament is racetime.gg-enabled, which hides on-site controls). |
| `get_matches_for_display(*, tournament_ids=None, stream_room_ids=None, only_upcoming=False, user_discord_id=None)` | `list[dict]` | Filtered match list in the same display shape, with acknowledgments batch-loaded. |
| `get_tournaments_for_filter()` | `dict[int, str]` | Tournament id → name for filter dropdowns. |
| `get_stream_rooms_for_filter()` | `dict[int, str]` | Stream room id → name for filter dropdowns. |

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentRepository`, `StreamRoomRepository`. Consumers: `theme/tables/match.py` (`self.display_service` — filters, `refresh`, and single-row updates).

### match_schedule_service.py — MatchScheduleService

Match lifecycle transitions (seat → start → finish → confirm), seed rolling, and all Discord DM fan-out for match events. Every transition is gated by `AuthService.can_transition_match`, validates ordering (e.g. "Match must be checked in before starting" as `ValueError`), stamps the timestamp, writes the matching `match.*` audit action, and enqueues a participant DM. Feature docs: [discord-notifications.md](../features/discord-notifications.md), [match-acknowledgment.md](../features/match-acknowledgment.md), [match-watcher.md](../features/match-watcher.md).

| Method | Returns | Description |
|---|---|---|
| `seat_match(match, actor=None)` | `None` | Set `seated_at` (rejects double check-in; rejects racetime.gg tournaments — the race room owns the lifecycle); audits `match.seated`; DMs participants. |
| `start_match(match, actor=None)` | `None` | Set `started_at` (requires seated, rejects restart); audits `match.started`; DMs participants. |
| `finish_match(match, actor=None)` | `None` | Set `finished_at` (requires started, rejects re-finish); audits `match.finished`; DMs participants. |
| `confirm_match(match, actor=None)` | `None` | Set `confirmed_at` (requires finished, rejects re-confirm); audits `match.confirmed`; DMs participants. |
| `generate_seed(match_id, actor=None)` | `(bool, str, str \| None)` | Roll a seed via `SeedGenerationService`, resolving the tournament's `preset` FK (randomizer + settings) when set, else the legacy `seed_generator` string. Per-match `asyncio.Lock` (class-level `_seed_locks` dict) rejects concurrent rolls; also fails softly when a seed already exists, no generator is configured, the generator is unknown, or permission is denied. On success creates the `GeneratedSeeds` row, audits `match.seed_rolled`, and enqueues seed DMs to opted-in players. Exceptions are caught and returned as `(False, error, None)`. |
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
| `assign_stations(match_id, assignments, actor=None)` | `Match` | Set `MatchPlayers.assigned_station` from a `{match_player_id: station}` mapping; gated by `can_transition_match`; rejected for racetime.gg tournaments (on-site-only — players race remotely). |
| `ensure_players_enrolled(tournament_id, player_ids)` | `None` | Enroll any of the given users not yet in the tournament (`ValueError` on unknown id). |
| `delete_match(match_id, actor=None)` | `None` | Delete; gated by `can_crud_match`; audits `match.deleted`. |
| `seat_players(match_id, actor=None)` | `Match` | Set `seated_at` and DM participants (older sibling of `MatchScheduleService.seat_match`, without the already-seated guard). |
| `finish_match(match_id, actor=None)` | `Match` | Set `finished_at`; requires `seated_at` (older sibling of `MatchScheduleService.finish_match`). |
| `record_match_result(match_id, winner_id, actor)` | `Match` | Two-player results: winner gets `finish_rank` 1, the other 2. `winner_id` is a **`MatchPlayers` row id**, not a User id. Gated by `can_transition_match`. |
| `acknowledge_match(match_id, user)` | `MatchAcknowledgment` | Player confirms they have seen their match. Only current players may acknowledge; double-acknowledge raises `ValueError`. Audits `match.acknowledged`. |

**Creation/reschedule flow.** `create_match` resolves every referenced user up front (so a bad id cannot leave an orphan `Match` row), creates the row, enrolls players in the tournament if needed, attaches commentators/trackers as pre-approved, audits `match.created`, then seeds per-player acknowledgment rows (the actor auto-acknowledges their own). Finally it hands the whole scheduled-notification fan-out to `MatchScheduleService.notify_match_scheduled` (ack request + crew DM + subscriber fan-out, plus stream-candidate when flagged). `update_match` re-seeds acknowledgments when `scheduled_at` or the player set changed; on a time change it calls `notify_match_scheduled(rescheduled=True)`, otherwise it enqueues just the acknowledgment request.

Collaborators: `MatchRepository`, `MatchAcknowledgmentRepository`, `TournamentRepository`, `UserRepository`, `CommentatorRepository`, `TrackerRepository`, `AuditService`, `MatchScheduleService` (lifecycle notify + `notify_match_scheduled`/`notify_stream_candidate`), `AuthService`, `discord_queue`. Consumers: `theme/tables/match.py` (acknowledge, plus reads via `MatchDisplayService`), `theme/dialog/match_dialog.py` (create/update/delete/request), `theme/dialog/match_result_dialog.py`, `theme/dialog/station_assignment_dialog.py`, `theme/dialog/stream_room_dialog.py` (stage + candidate flag), `pages/home_tabs/schedule.py`, `pages/home_tabs/stage_timeline.py`, `pages/home_tabs/player.py`, `discordbot/match_acknowledgment.py` (DM button handler).

**match_source_guard.py** — the per-field half of the SpeedGaming read-only contract, extracted from `MatchService` to keep it focused (and under the file-length guideline). `assert_sg_fields_unchanged(match, *, tournament_id, scheduled_date, scheduled_time, players_changed)` raises `ValueError` when a staff edit would change an ETL-owned field (schedule, players, tournament) on an SG-sourced match (`speedgaming_episode_id` set); a no-op for non-sourced matches. Comparison is by *value*, so the edit dialog can resubmit the disabled fields unchanged — only a genuine change is rejected. The UI also disables these fields, but this is the enforcement: a gap here would be silently reverted on the next sync and look like a bug. Called by `MatchService.update_match`.

**match_participants.py** — `MatchParticipants`, the participant-row orchestration extracted from `MatchService` to keep it under the file-length guideline. Pure repository plumbing (no audit, no events): `resolve_users` (id list → `User`s, one query, `ValueError` on the first missing id), `ensure_enrolled` (batch-enroll players not yet in the tournament), `sync_players`/`sync_crew` (reconcile the player and commentator/tracker rows to a target id set), and `seed_acknowledgments` (reset and re-create per-player ack rows, auto-acking the actor). `MatchService` composes it lazily via a `participants` property bound to its own repositories, so create/update/request all share one roster path.

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
| `generate_seed(randomizer, preset=None)` | `str` | Dispatch to the named generator; returns the seed URL/string. ALTTPR uses `preset.settings` when a `Preset` is supplied (else the built-in `casualboots` settings); other backends ignore the preset (hard-coded until PR 11). `ValueError` for unsupported keys. |
| `generate_alttpr_for_tournament(tournament_id, balanced=True)` | `str` | ALTTPR seed with an approved community triforce text embedded — balanced selection weights every submitter equally; falls back to a plain seed when no approved texts exist. `ValueError` for unknown tournaments. |

Collaborators: `TriforceTextService` (text selection), `pyz3r`/`aiohttp` for external randomizer APIs. Consumers: `MatchScheduleService.generate_seed` (the match seed-roll path, passing the resolved `Preset`), `theme/dialog/tournament_edit_dialog.py` (reads `AVAILABLE_RANDOMIZERS`).

### preset_service.py — PresetService

Tenant-authored seed-rolling presets (a named `randomizer` + `settings` blob). Deep dive: [seed-generation.md](seed-generation.md#presets-db-backed).

| Member | Returns | Description |
|---|---|---|
| `list_presets(actor)` | `list[Preset]` | All of the tenant's presets. Gated by `AuthService.can_manage_presets`. |
| `list_selectable()` | `list[Preset]` | All presets (ungated read) — populates the tournament dialog's Seed Preset select. |
| `create_preset(actor, *, name, randomizer, settings, description=None)` | `Preset` | Validate (known randomizer, dict settings, unique `(randomizer, name)`) and insert. Audits `preset.created`. |
| `update_preset(actor, preset_id, *, name=None, randomizer=None, settings=None, description=None)` | `Preset` | Partial update with the same validation + uniqueness re-check. Audits `preset.updated`. |
| `delete_preset(actor, preset_id)` | `None` | Delete. Audits `preset.deleted`. Detaches linked tournaments (`SET_NULL`). |
| `import_builtins(actor)` | `list[Preset]` | Import the committed `presets/` files as rows, idempotent by `(randomizer, name)`. Audits `preset.imported`. |

All mutations gated by `AuthService.can_manage_presets` (STAFF / `PRESET_MANAGER` / super-admin / system). Collaborators: `PresetRepository`, `AuditService`, `AuthService`, `SeedGenerationService` (randomizer validity). Consumers: `pages/admin_tabs/admin_presets.py` (admin Presets tab), `theme/dialog/tournament_edit_dialog.py` (Seed Preset select).

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

### tenant_theme_service.py — TenantThemeService

The per-tenant **brand palette**. The app ships a fixed "Phoenix" palette (gold/ember); a community's STAFF may override four brand colours — `primary`, `secondary`, `accent`, and the header bar — stored under `Tenant.config['theme']` (no dedicated columns). Semantic status colours (positive/negative/warning/info) are intentionally not editable. Reads merge stored overrides onto the defaults so callers always get a full palette; writes are STAFF-gated (`AuthService.ensure(is_staff, …)`), validated to 6-digit hex, and audited (`theme.updated`, tenant-scoped). `Tenant` is the tenancy discriminator (never tenant-scoped), so this service reads/writes through the cross-tenant `TenantRepository`. Applied by `BaseLayout` — see [frontend.md § Per-tenant theme colours](../reference/frontend.md#per-tenant-theme-colours).

| Method | Returns | Description |
|---|---|---|
| `get_theme(tenant_id)` | `dict[str, str]` | Full palette for a tenant (overrides merged onto `DEFAULT_THEME`). Fresh read (`get_by_id` is uncached). |
| `get_current_theme()` | `dict[str, str]` | Best-effort palette for the in-scope tenant; the shipped defaults when there is no tenant (platform surface / error page). Non-raising. |
| `set_theme(actor, colors)` | `dict[str, str]` | STAFF-gated; validates hex, persists to `Tenant.config['theme']`, audits. A blank value clears that key; clearing all keys resets to defaults. |
| `is_customized(colors)` | `bool` | Whether a resolved palette differs from the shipped defaults. |
| `list_presets()` | `dict[str, dict]` | Curated, contrast-verified palettes (`THEME_PRESETS`) for the editor's preset picker. |
| `contrast_report(colors)` | `dict[str, dict]` | Per-colour WCAG-AA contrast (`{ratio, ok, threshold, against}`) of each colour against the surface it's used on — pure, skips invalid/blank values. |
| `contrast_warnings(colors)` | `list[str]` | Human-readable warnings for colours below the 4.5:1 AA target. |

Contrast math lives in [`application/utils/color_contrast.py`](../../application/utils/color_contrast.py) (pure WCAG relative-luminance / contrast-ratio). Presets are held to the same bar the shipped defaults meet — `tests/test_color_contrast.py` asserts every preset field passes, so a preset can never ship failing AA. Collaborators: `TenantRepository`, `AuthService`, `AuditService`, `color_contrast`. Consumers: `theme/base.py` (`BaseLayout` chrome), `pages/admin_tabs/admin_theme.py` (the Appearance editor, presets + live warnings).

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

Tournament CRUD plus Tournament Admin / Crew Coordinator membership. Creation and deletion are Staff-only; updates allow the tournament's TAs; membership grants are Staff-only (`can_grant_roles`). All mutations audited under `tournament.*`. The optional `config` blob is validated by `validate_tournament_config` (from [`tournament_config.py`](../../application/services/tournament_config.py)) before persistence — unknown keys raise `ValueError`.

| Method | Returns | Description |
|---|---|---|
| `create_tournament(name, description=None, seed_generator=None, bracket_url=None, rules_url=None, tournament_format=None, average_match_duration=None, max_match_duration=None, is_active=True, players_per_match=2, team_size=1, staff_administered=False, config=None, actor=None)` | `Tournament` | Create; trims strings; treats the literal string `"None"` as no seed generator; non-empty name required; validates `config`. |
| `update_tournament(tournament, ...same optional fields..., config=None, actor=None)` | `Tournament` | Partial update of any subset of the same fields; validates `config` when provided; audits the changed-field list. |
| `delete_tournament(tournament, actor=None)` | `None` | Staff-only delete. |
| `add_admin(tournament, target, actor=None)` | `None` | Grant Tournament Admin (M2M add). |
| `remove_admin(tournament, target, actor=None)` | `None` | Revoke Tournament Admin. |
| `add_crew_coordinator(tournament, target, actor=None)` | `None` | Grant Crew Coordinator. |
| `remove_crew_coordinator(tournament, target, actor=None)` | `None` | Revoke Crew Coordinator. |
| `get_all_tournaments(active_only=False)` | `list[Tournament]` | List tournaments. |
| `get_tournament_by_id(tournament_id)` | `Tournament \| None` | Lookup by id. |

Collaborators: `TournamentRepository`, `AuditService`. Consumers: `theme/dialog/tournament_edit_dialog.py`, `theme/dialog/user_edit_dialog.py`, `pages/admin_tabs/reports/shared.py` (filter options).

### tournament_config.py + tournament_strategies/ — hybrid-config substrate

Foundations for online-tournament user-definable logic ([online-tournaments](../online-tournaments/README.md)). `tournament_config.py` defines `TournamentConfig` (a Pydantic model with `extra='forbid'`) and `validate_tournament_config(config)`, which normalizes the blob and raises `ValueError` on any unknown key — the single entry point `TournamentService` calls before persisting `Tournament.config`. `tournament_strategies/` is the register/lookup registry for the finite set of named strategy primitives (`register_strategy(kind, name)`, `get_strategy(kind, name)`, `available_strategies(kind)`); config picks and parameterizes them — **never `eval`**. PR 0 ships the substrate empty; feature PRs add concrete config keys and strategies.

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

### racetime_service.py — RacetimeService

Coordinates the racetime.gg account-linking integration: a logged-in user completes a one-time racetime OAuth login (read scope) so we can record their verified racetime identity (id / name) on their `User`. Identity only — the access token is used once during linking and discarded (mirrors `TwitchService`). Mock mode is gated by [`MOCK_RACETIME`](#mock_racetimepy). These are the **identity-link** OAuth credentials only; the race-room bots use their own per-category credentials on `RacetimeBot` rows.

| Method | Returns | Description |
|---|---|---|
| `is_configured()` (static) | `bool` | OAuth app credentials are present (or mock is on). |
| `player_authorize_url(state)` (static) | `str` | racetime OAuth authorize URL to redirect the browser to. |
| `redirect_uri()` (static) | `str` | The registered OAuth redirect URI (`RACETIME_REDIRECT_URI` or derived from `BASE_URL`). |
| `exchange_player_code(code)` | `{user_id, username}` | Exchange a user's auth code and return their identity (token used once, discarded). |
| `record_player_link(user, racetime_user_id, racetime_username, actor)` | `None` | Persist the linked racetime identity; rejects ids already linked elsewhere (`ValueError`); audits `racetime.linked`. |
| `unlink_player(user, actor)` | `None` | Clear a user's racetime link; audits `racetime.unlinked`. |

Collaborators: `AuditService`, [`racetime_client.py`](#racetime_clientpy) (`RacetimeClient`/`MockRacetimeClient`), [`mock_racetime.py`](#mock_racetimepy). Consumers: the racetime OAuth pages ([`pages/racetime_oauth.py`](../../pages/racetime_oauth.py)) and the profile "Link racetime.gg" card ([`pages/home_tabs/racetime_link_section.py`](../../pages/home_tabs/racetime_link_section.py)).

### racetime_bot_service.py — RacetimeBotService

Platform administration of the shared, **global** racetime bots (one per game category, each holding that category's OAuth credentials). All mutations are SUPER_ADMIN-gated and run on `/platform` with no tenant context, so their audit rows are platform-level (`tenant=NULL`). The `client_secret` is a privileged secret: `serialize()` omits it, `update_bot` only rewrites it when a new value is supplied (blank = unchanged), and the audit log records only that the field changed — never its value.

| Method | Returns | Description |
|---|---|---|
| `serialize(bot)` (static) | `dict` | Secret-free view for admin tables (omits `client_secret`). |
| `list_bots(actor)` / `get_bot(actor, id)` | `[RacetimeBot]` / `RacetimeBot` | SUPER_ADMIN reads. |
| `create_bot(actor, *, category, client_id, client_secret, name, …)` | `RacetimeBot` | Create; unique category; audits `racetime_bot.created`. |
| `update_bot(actor, id, *, client_secret=None, …)` | `RacetimeBot` | Update; blank secret keeps the stored one; audits `racetime_bot.updated`. |
| `delete_bot(actor, id)` | `None` | Delete; audits `racetime_bot.deleted`. |
| `grant_tenant(actor, bot_id, tenant_id)` | `RacetimeBotTenant` | Authorize a tenant (idempotent; re-activates a suspended grant); audits `racetime_bot.granted`. |
| `revoke_tenant(actor, bot_id, tenant_id)` | `None` | Remove a grant; audits `racetime_bot.revoked`. |
| `list_grants(actor, bot_id)` | `[RacetimeBotTenant]` | Grants for a bot (SUPER_ADMIN). |
| `list_authorized_for_tenant(tenant_id)` | `[RacetimeBot]` | Tenant-facing: active bots a tenant may select (no secret exposed; explicit tenant id). |
| `is_authorized_for_tenant(bot_id, tenant_id)` | `bool` | Whether a tenant may select a given bot. |

Runtime health methods (PR 4) are **not** SUPER_ADMIN-gated — the caller is the trusted in-process connection loop acting as the system user, writing platform-level (`tenant=NULL`) health rows. `client_secret` never appears in them.

| Method | Returns | Description |
|---|---|---|
| `list_active_bots()` | `[RacetimeBot]` | Active bots the runtime should hold a connection for. |
| `get_runtime_bot(id)` | `RacetimeBot?` | Load a bot with no permission gate (runtime/restart). |
| `record_connected(id, actor)` | `None` | `status=connected`, `last_connected_at`/`last_checked_at`; audits `racetime_bot.connected`. |
| `record_heartbeat(id)` | `None` | Refresh `last_checked_at` only (un-audited liveness tick). |
| `record_error(id, actor, msg, *, auth_failed=False)` | `None` | `status=error` + message; audits `racetime_bot.error` (with `auth_failed`). |
| `mark_disconnected(id, actor, msg=None)` | `None` | `status=disconnected`; audits `racetime_bot.disconnected`. |

Collaborators: `AuditService`, `RacetimeBotRepository`. Consumers: the `/platform` bot CRUD + tenant-assignment UI ([`pages/platform.py`](../../pages/platform.py)), `TournamentService` (validating a tournament's selected bot against the tenant's grants), and the `racetimebot/` runtime (health writes).

#### racetimebot/ — the racetime bot runtime (PR 4)

A peer of `discordbot/` (presentation layer: calls services, never repositories). Started from the FastAPI lifespan when `RACETIME_BOT_ENABLED` is on; a no-op otherwise. Modules: `manager.py` (`RacetimeBotManager` singleton — one `CategoryConnection` task per active bot, re-adopts open rooms on boot, `restart(actor, id)`), `connection.py` (`CategoryConnection` — the supervised loop: authenticate → `record_connected` → run with heartbeats; auth error → `record_error(auth_failed=True)` and stop; transient → `record_error` + exponential backoff capped 5 min; graceful stop → `mark_disconnected`), `handler.py` (`RaceHandler` — resolves slug → room → tenant via the unscoped lookup, binds `tenant_scope`, delegates to a lifecycle object; a raised handler is caught so it never kills the bot), `transport.py` (`RacetimeTransport` seam: `RealRacetimeTransport` does a real `client_credentials` token fetch + liveness loop; `RaceRoomEvent`/`RaceEntrant`/`EntrantStatus` value types; `RacetimeAuthError`/`RacetimeTransientError`), and `mock.py` (`MockRacetimeTransport` — the scripted fake for `MOCK_RACETIME` and tests).

### race_room_profile_service.py — RaceRoomProfileService

Tenant-scoped CRUD for reusable racetime room settings (the `startrace` parameters a community reuses). Gated by `AuthService.can_manage_sync` (SYNC_ADMIN/STAFF/super-admin); audited (`race_room_profile.created|updated|deleted`). `list_selectable()` is an ungated read used to populate the tournament dialog's profile select.

| Method | Returns | Description |
|---|---|---|
| `list_profiles(actor)` / `get_profile(actor, id)` | `[RaceRoomProfile]` / `RaceRoomProfile` | Gated reads. |
| `list_selectable()` | `[RaceRoomProfile]` | Ungated read for the tournament dialog. |
| `create_profile(actor, *, name, **fields)` | `RaceRoomProfile` | Create; per-tenant unique name; rejects negative timers. |
| `update_profile(actor, id, *, name=None, **fields)` | `RaceRoomProfile` | Update. |
| `delete_profile(actor, id)` | `None` | Delete. |

Collaborators: `AuditService`, `RaceRoomProfileRepository`. Consumers: the admin **Racetime** tab ([`pages/admin_tabs/admin_racetime.py`](../../pages/admin_tabs/admin_racetime.py)) and the tournament dialog's profile select.

### racetime_room_service.py — RacetimeRoomService

Record lookup + status writes for race-room→tenant routing. `get_by_slug(slug)` is the **unscoped** entry point the inbound-event router uses (a racetime event carries only the slug, no tenant); `get_for_match(match)` finds a match's room; `list_open_rooms()` returns not-yet-terminal rooms across all tenants (unscoped, for boot-time re-adoption); `set_status(room, status)` writes the cached lifecycle status (stamping `opened_at` the first time a room reaches `in_progress`). The richer create/seed/result lifecycle lands in PR 6.

Collaborators: `RacetimeRoomRepository`. Consumers: the `racetimebot/` runtime (re-adoption + status writes).

### race_room_service.py — RaceRoomService (PR 6)

The racetime room lifecycle mapped onto a `Match` — the business layer both the auto-open worker and the `racetimebot/` handlers call. Tenant-scoped (callers bind the tenant); **acts as the system user**; audits + publishes a `race_room.*` event on every transition.

| Method | Returns | Description |
|---|---|---|
| `create_room_for_match(match, *, actor=None, attach_seed=True)` | `RacetimeRoom` | Idempotent open: one room per match; requires the tournament's authorized bot (its category names the room); attaches the seed via `MatchScheduleService.generate_seed`. Emits `race_room.created` + `race_room.opened`. |
| `manual_create_room(actor, match_id)` | `RacetimeRoom` | STAFF/`SYNC_ADMIN`-gated manual open, ignoring the auto toggle. |
| `mark_in_progress(room, *, actor=None)` | `None` | Sets the match's `started_at`; emits `race_room.started`. |
| `record_finish(room, entrants, *, actor=None)` | `None` | Maps entrants → linked `User`, records `finish_rank` (place) + `finish_time` (seconds), closes the match, feeds the existing result path (+ optional Challonge push). Handles forfeit / no-show / DQ / one-finisher; unmatched handles go to the audit for reconcile. Emits `race_room.finished` + `race_room.result_recorded` + `match.result_recorded`. |
| `cancel_room(room, *, actor=None, reason=None)` | `None` | Marks the room cancelled; emits `race_room.cancelled`. |

`RaceRoomLifecycle` (same module) is the adapter the PR 4 handler injects: it translates a transport `RaceRoomEvent` into the matching transition. Collaborators: `RacetimeRoomRepository`, `AuditService`, `AuthService`, `UserService`, `MatchScheduleService`, `ChallongeService`, the event bus. Consumers: the auto-open worker, the `racetimebot/` handlers, and the admin match dialog (manual create).

**race_room_worker.py** — the auto-open background loop (peer of `volunteer_reminder`). Every 60 s it scans (cross-tenant, unscoped) not-yet-finished matches on auto-create tournaments in a wide window, then per match — inside `tenant_scope` — opens a room when it enters that tournament's `room_open_minutes_before` lead, is idempotent (one room per match), has an authorized bot, and every entrant has a linked racetime identity. Started from the lifespan only when `RACETIME_BOT_ENABLED` is on.

### service_health_service.py — ServiceHealthService (PR 5)

Platform external-service health monitor. **Computed-and-cached, no persistence model**: an async probe registry (`_PROBES`) whose results live in a process-global in-memory cache (`_CACHE`, owned by the single worker/on-demand refresh — safe module-level state). `ServiceStatus` = `healthy / degraded / credential_warning / down / unknown` (`credential_warning` is the distinct "up but a credential is expiring/rejected" signal). Each probe is wrapped with a hard timeout so one hung dependency can't stall the board; a raising probe becomes `down`.

| Method | Returns | Description |
|---|---|---|
| `refresh(*, alert=True)` | `list[ProbeResult]` | Run every probe concurrently, update the cache, and — on a transition *into* down / credential-warning — fire an alert. Sorted worst-first. |
| `snapshot()` | `list[ProbeResult]` | Cached results (UNKNOWN placeholders for not-yet-probed keys); the board's instant initial paint. |
| `tenant_subset(tenant_id)` | `list[ProbeResult]` | The read-only subset a tenant's STAFF may see — its authorized racetime bots + its own Challonge connection — probed live (not from the platform cache). Caller binds the tenant scope. |

Probes: PostgreSQL (DB round-trip), Discord bot (gateway readiness / mock), Discord OAuth (config), racetime bots (reads `RacetimeBot.status`, maps `error` w/ auth message → credential-warning), SpeedGaming (reachability / mock), Challonge (API reachability **+** token expiry across all tenants via `ChallongeRepository.list_all_connections()`, an explicitly-unscoped read), Twitch OAuth (config), seed-gen upstreams alttpr.com / ootrandomizer.com / maprando.com (reachability), web-push/VAPID (config), Sentry (config). Alerting: `refresh` publishes `EventType.SERVICE_HEALTH_ALERT` (platform-level → no tenant webhook; the real channels are Sentry `capture_message` + optional super-admin DM under `SERVICE_HEALTH_ALERT_DM`). Consumers: `/platform` board (full, refreshable) and the admin **Service Health** tab (tenant subset) via `pages/service_health_view.py`.

**service_health_worker.py** — the periodic probe loop (peer of `discord_event_worker`). Every 120 s it calls `ServiceHealthService().refresh()` with **no tenant scope** (all probes are platform-level). Started from the lifespan only when `SERVICE_HEALTH_ENABLED` is on; the board still refreshes on demand regardless. The loop never dies — a failing tick is logged and retried.

### speedgaming_etl_service.py — SpeedGamingETLService (PR 7)

One-way SpeedGaming → SGLMan schedule ETL, ported from sahabot2 and adapted to the three-layer + multitenant shape. Per active `SpeedGamingEventLink` the sync worker (never a UI caller) drives the pipeline: **extract** a forward schedule window from the SG API (`SpeedGamingClient`), **transform** each episode to UTC and resolve every player to a `User` via the placeholder pattern, **load** by upserting a `SpeedGamingEpisode` staging row and materializing/refreshing its `Match` + `MatchPlayers`. Runs as the reserved **system `User`** (audit/event actor), always inside the worker's `tenant_scope`. Two race-day guards uphold the hybrid read-only contract: a re-sync **skips** a match that is finished / manually progressed / racetime-linked, and **auto-finishes** SG-sourced matches more than 4h past their scheduled time (unless a room is linked). The per-field read-only lock on a sourced match lives in [`match_source_guard.py`](#match_servicepy--matchservice) / `MatchService.update_match`; this service owns the sync side. Audited under `sg_sync.*`; module constant `BACKFILL_GRACE_HOURS = 1`.

| Method | Returns | Description |
|---|---|---|
| `sync_event_link(link, *, actor, now=None)` | `SyncResult` | Sync one active link (assumes ambient tenant = `link.tenant`): import every episode in the window, soft-detach episodes that vanished upstream, auto-finish stale matches, and record the link's observability fields (`last_synced_at`/`last_status`/`last_error`). Never raises on a per-episode failure — failures are tallied. |
| `import_episode(link, raw, *, actor, now=None)` | `str` | Transform+load one raw SG episode: upsert its staging row and materialize/refresh its match. Returns the outcome key (`'imported'`/`'unchanged'`/`'skipped'`) for the caller to tally; raises on a transform/load failure so the caller can mark that episode ERROR. |

`SyncResult` (same module) is the per-run tally dataclass — `imported`, `unchanged`, `skipped`, `cancelled`, `auto_finished`, `errors`, `error_messages` — with `as_dict()` for the audit/observability payload. Collaborators: `SpeedGamingEpisodeRepository`, `SpeedGamingEventLinkRepository`, `MatchRepository`/`MatchService`, `UserRepository`, `AuditService`, the event bus, `SpeedGamingClient`. Consumers: `speedgaming_sync_worker` and `SpeedGamingSyncService.sync_now`.

### speedgaming_sync_service.py — SpeedGamingSyncService (PR 7)

The human-driven management surface over the SG ETL: CRUD of `SpeedGamingEventLink` rows (which SG event slug feeds which tournament) and an on-demand "sync now" for one link. Every mutation is gated by `AuthService.can_manage_sync` (STAFF / super-admin / `SYNC_ADMIN`) and audited under `sg_sync.*`. The background worker calls the ETL directly as the system user; this service is the admin-facing peer.

| Method | Returns | Description |
|---|---|---|
| `list_links(actor)` | `list[SpeedGamingEventLink]` | The tenant's event links. |
| `list_episodes(actor, event_link_id)` | `list[SpeedGamingEpisode]` | Staging episodes imported for one link (observability). |
| `create_link(actor, *, tournament_id, event_slug, content_type=None, sync_interval_minutes=15, lookahead_hours=72, active=True)` | `SpeedGamingEventLink` | Link an SG event slug to a tournament; non-empty slug and existing tournament required; rejects a duplicate `(tournament, slug)` (`ValueError`). Audits `sg_sync.event_link_created`. |
| `update_link(actor, link_id, *, event_slug=None, content_type=None, sync_interval_minutes=None, lookahead_hours=None, active=None)` | `SpeedGamingEventLink` | Partial edit; re-checks slug uniqueness on change. Audits `sg_sync.event_link_updated`. |
| `delete_link(actor, link_id)` | `None` | Remove a link; audits `sg_sync.event_link_deleted`. |
| `sync_now(actor, link_id)` | `SyncResult` | Run `SpeedGamingETLService.sync_event_link` for one link on demand and return the run tally. |

Collaborators: `SpeedGamingEventLinkRepository`, `SpeedGamingEpisodeRepository`, `TournamentRepository`, `SpeedGamingETLService`, `AuthService`, `AuditService`. Consumer: the admin **SpeedGaming** sync tab.

### user_service.py — UserService

User lookup, profile edits (self- and admin-driven), activation, global role grants, and tournament enrollment management. Audited under `user.*`; role grants gated by `can_grant_roles`, admin fields by `is_staff`.

| Method | Returns | Description |
|---|---|---|
| `get_user_by_discord_id(discord_id)` | `User \| None` | Lookup by Discord id. |
| `get_system_user()` | `User` | Resolve the reserved automation actor (get-or-create on the sentinel `discord_id`, idempotent). Workers/bots pass it as `actor` so audit rows snapshot a real username. |
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

### async_qualifier_service.py — AsyncQualifierService (PR 9)

The self-paced permalink-pool qualifier — a peer aggregate of `Tournament` with its own state machine (window opens → draw → run → review → scored leaderboard → close). Owns every rule the repositories don't:

- **Management** — qualifier/pool/permalink CRUD + per-qualifier `admins`, gated by `AuthService.can_admin_qualifier` (STAFF/`QUALIFIER_ADMIN`/super-admin, or a per-qualifier admin). `roll_permalinks` rolls N seeds from the pool's `Preset` via `SeedGenerationService`; `add_permalinks_bulk` pastes many. Config validated by `validate_async_qualifier_config` (`application/services/async_qualifier_config.py`).
- **Draw** (`start_run`) — an atomic, row-locked (`in_transaction` + `lock_user_for_draw`) transaction enforcing one active run per player, the `runs_per_pool` cap, and permalink no-repeat, then picking a permalink by **imbalance-forcing fairness** (random unless a pool's play-count spread crosses `draw_imbalance_threshold`, then the least-played). Reveal == start (web-first).
- **Run lifecycle** — `submit_run` (→ review), `forfeit_run` (irreversible, scores 0), `reattempt_run` (voids the prior run, frees the slot, requires a reason, limited by `allowed_reattempts`).
- **Review** — reviewers = the qualifier's `admins`; **self-review blocked**; `claim_run`/`release_claim` claim-locking; `review_run` approves/rejects, then recomputes the permalink's par and rescores its approved runs.
- **Scoring / leaderboard** — par + score math in `async_qualifier_scoring.py` (`compute_par` = mean of the N fastest approved runs; `compute_score` = `clamp(0,105,(2−elapsed/par)·100)`; `build_leaderboard` = per-pool slots, unfilled = 0, plus an estimate). `get_leaderboard` enforces the **active-window information lockdown** (`is_results_public`): the board/pools/pars are staff-only until the qualifier closes (inactive or past `closes_at`).

Audits every state change (`AuditActions.ASYNC_QUALIFIER_*`) and mirrors `run_submitted`/`run_reviewed` onto the event bus (`EventType.ASYNC_QUALIFIER_RUN_*`). Best-effort Discord DM on review. Collaborators: the five `AsyncQualifier*` repositories, `PresetRepository`, `SeedGenerationService`, `AuthService`, `AuditService`, `application.events`. Admin UI: `pages/admin_tabs/admin_qualifiers.py`; player UI: `pages/qualifiers.py`. Plan: [pr-9-async-qualifiers.md](../online-tournaments/implementation/pr-9-async-qualifiers.md). `recompute_par_and_scores(permalink_id)` is the public entry the live-race capture path (below) reuses.

Two sibling helpers keep the service under the file-length guideline (both extracted from it, same three-layer standing as `async_qualifier_config.py`/`async_qualifier_scoring.py`):

- **async_qualifier_rules.py** — side-effect-free rule functions: `validate_counts`/`validate_window` (input validation), `ensure_window_open` (raises when the window is closed/not-yet-open), `is_results_public` (the lockdown predicate), `par_sample_size`/`imbalance_threshold` (read tunables off `qualifier.config` with defaults), and `display_name`. `is_results_public` stays a thin `AsyncQualifierService` method delegating here, so `pages/qualifiers.py` keeps calling `service.is_results_public`.
- **async_qualifier_access.py** — shared access helpers the two split qualifier services both use: `ensure_qualifier_admin(...)` (the repeated admin gate) and `require_qualifier`/`require_pool`/`require_permalink`/`require_run` (load-or-`NotFoundError` lookups), so the gate + entity-resolution ladder lives in one place.
- **async_qualifier_draw.py** — `AsyncQualifierDraw`, the fairness draw + par/score recompute engine that touches repositories. `draw_candidates`/`pick_permalink` implement the imbalance-forcing draw; `recompute_par_and_scores` recomputes a permalink's par (via `async_qualifier_scoring`) and rescores its approved runs. Composed by `AsyncQualifierService.__init__` as `self.draw`; `start_run` and the review/reattempt/live-race recompute paths call through it.

### async_qualifier_live_race_service.py — AsyncQualifierLiveRaceService (PR 10)

Synchronous racetime qualifier races whose results flow into `AsyncQualifierRun`s, **reusing the PR 4/6 racetime subsystem** rather than a second integration:

- **Author** (`create_live_race`) — schedule a race for a pool, optionally pinning a permalink and an SG `episode`; gated by `AuthService.can_admin_qualifier`.
- **Open** (`open_room`) — create a `RacetimeRoom` (with `match=None`) named by one of the tenant's authorized bots (`RacetimeBotService.list_authorized_for_tenant`), mirror its slug onto the live race (`racetime_slug`), and move it to `PENDING`. Idempotent.
- **Capture** (`record_finish`) — map each racetime entrant to a `User` (by `racetime_user_id`), write an `AsyncQualifierRun` (`done`→finished, `dnf`→forfeit, `dq`→disqualified; `finish_time`→`elapsed_seconds`), then par-score via `AsyncQualifierService.recompute_par_and_scores`. Live-race runs **skip reviewer sign-off** (written `APPROVED` — the racetime result is self-attributing); non-finishers score 0. **Refuses to record while any entrant is still racing.**

`RaceRoomLifecycle` (in `race_room_service.py`) routes a finished/started/cancelled room to this service instead of the match path when `RacetimeRoom.match_id` is null and the room's slug resolves to a live race. Audits `AuditActions.ASYNC_QUALIFIER_LIVE_RACE_*` (create/open/cancel are audit-only; the captured finish also emits `EventType.ASYNC_QUALIFIER_LIVE_RACE_RECORDED`). Collaborators: `AsyncQualifierLiveRaceRepository`, `AsyncQualifierRunRepository`, `RacetimeRoomRepository`, `RacetimeBotService`, `AsyncQualifierService`, `UserService`, `AuditService`. Admin UI: the **Live Races** sub-tab in `pages/admin_tabs/admin_qualifiers.py`. Plan: [pr-10-qualifier-live-races.md](../online-tournaments/implementation/pr-10-qualifier-live-races.md).

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

### racetime_client.py

Thin async `aiohttp` wrapper over the two racetime.gg endpoints the account-linking flow needs — the OAuth token exchange and the `o/userinfo` lookup ([racetime_client.py](../../application/utils/racetime_client.py)). Returns a **normalized** identity dict so `RacetimeService` never sees the wire shape. Module constants: `AUTHORIZE_URL`, `OAUTH_EXCHANGE_URL`, `USERINFO_URL`, `IDENTITY_SCOPE`.

| Member | Returns | Description |
|---|---|---|
| `build_authorize_url(client_id, redirect_uri, scope, state)` (function) | `str` | racetime OAuth authorize URL to redirect the browser to. |
| `RacetimeAPIError` (exception) | — | Raised on an API error or unexpected payload. |
| `RacetimeClient.exchange_code(code, redirect_uri)` | `dict` | Exchange an auth code for a token payload. |
| `RacetimeClient.get_me(access_token)` | `{user_id, username}` | The authenticated racetime account identity for a raw token. |
| `MockRacetimeClient` | — | `MOCK_RACETIME` stub returning a deterministic canned identity (chosen via `MOCK_RACETIME_IDENTITY`) so local dev can click through link/unlink. |

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

### mock_racetime.py

The racetime.gg counterpart to `mock_twitch` ([mock_racetime.py](../../application/utils/mock_racetime.py)). Lets local development exercise the full racetime link/unlink flow without a real OAuth app. Also gates the bot runtime added in a later PR; both halves share the one production-refusal switch.

| Function | Returns | Description |
|---|---|---|
| `is_mock_racetime()` | `bool` | True when `MOCK_RACETIME` is `1`/`true`/`yes`. Because it fakes a verified racetime identity, it **raises `RuntimeError` when enabled while `ENVIRONMENT=production`**. |

`RacetimeService` reads this to choose `MockRacetimeClient` over `RacetimeClient` and to report `is_configured()` as true in mock mode.

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
