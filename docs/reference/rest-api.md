# REST API Reference

_Reference for Wizzrobe's REST API: the router package in [`api/`](../../api/) and the FastAPI app metadata in [`main.py`](../../main.py). Part of the [documentation index](../README.md)._

## Overview

| | |
|---|---|
| Title | Wizzrobe API |
| Version | 1.0.0 |
| Base path | `/api` |
| Swagger UI | `/api/docs` |
| ReDoc | `/api/redoc` |
| Source | [`api/`](../../api/) package — `routers/`, `schemas/`, `dependencies.py`, `rate_limit.py`; mounted in [`main.py`](../../main.py) |

The API is served by the same Uvicorn process as the NiceGUI frontend. The interactive Swagger UI at `/api/docs` is the authoritative, always-current catalogue (every endpoint, schema, and example); this page summarises the model.

## Authentication

**Every endpoint requires a personal bearer token**, with two exceptions: the unauthenticated `GET /api/health` liveness probe (see [Health](#health-apihealth)) and `POST /api/web-push/rotate` (see [Web push](#web-push-apiweb-push)), whose only caller is a service worker with no session to present.

Generate a token on the home **Profile** tab (the *API tokens & AI clients* card), then send it on each request:

```
Authorization: Bearer wizzrobe_pat_xxxxxxxx...
```

- A token is **bound to exactly one tenant**, chosen at creation. `resolve_token` reads `token.tenant_id`, returns `403` if that tenant is missing or inactive, and sets the request tenant context — the API is excluded from `TenantMiddleware`, so the **token, not the URL, is what scopes the request**. A router-level `tenant_context_scope` dependency baselines the contextvar to `None` and resets it after the response, so a tenant never leaks to the next request on a reused task.
- A token **acts as its owning user** and inherits that user's exact permissions and scope *within that tenant* — the same `AuthService` role checks that gate the web UI apply. A non-staff token gets `403` from staff-only routes; a Tournament Admin token can edit only its own tournaments; a self-action (acknowledge, sign up, edit own profile) only ever affects the token's user.
- A token may be flagged **read-only**, in which case it can call read (`GET`) endpoints only; any write returns `403`.
- Tokens are stored as a SHA-256 hash (the plaintext is shown once at creation), support an optional expiry, and can be revoked at any time. Implementation: [`ApiToken`](../../models/user.py) model, [`ApiTokenService`](../../application/services/api_token_service.py), auth dependency in [`api/dependencies.py`](../../api/dependencies.py).

Tokens can also be managed programmatically via the `/api/tokens` endpoints (creating/revoking a token requires a non-read-only token, so a read-only token can never mint a more privileged one).

**MCP tokens are not REST credentials.** `ApiToken` also stores the platform-wide OAuth tokens issued to MCP clients (`origin='oauth'`, `tenant=NULL`); those are refused here with `401`, and a personal access token is refused at `/mcp` with `401` plus the OAuth challenge. A credential minted for one surface can never be replayed against the other. The MCP server is a sibling entry surface, not part of this API — see [features/mcp-server.md](../features/mcp-server.md).

### Status codes

| Code | Meaning |
|---|---|
| `401` | Missing, malformed, unknown, revoked, or expired token |
| `403` | Inactive account, read-only token used for a write, or the user lacks the required role/scope (`PermissionError` from a service) |
| `400` | Validation/business-rule error (`ValueError` from a service) |
| `404` | Entity not found (including a feature-flag-gated router the tenant hasn't enabled) |
| `422` | Request body/query failed schema validation |
| `429` | Rate limit exceeded — carries a `Retry-After` header |
| `503` | `GET /health` only: the database is unreachable |

`PermissionError`/`ValueError` → `403`/`400` translation is handled by `ServiceErrorRoute` in [`api/dependencies.py`](../../api/dependencies.py), scoped to the API routers so the NiceGUI frontend is unaffected.

### Rate limiting

`rate_limit` ([`api/rate_limit.py`](../../api/rate_limit.py)) is a dependency on the aggregating router, so it applies to **every** endpoint including `/health`. It is an in-process fixed-window counter (the app runs single-worker), `API_RATE_LIMIT_PER_MIN` requests per minute, default 120.

It runs **before** authentication, so unauthenticated floods are capped too. The client IP is always enforced as a ceiling; a *well-formed* bearer token additionally gets its own bucket (keyed by SHA-256 hash, never the raw secret) so one client's traffic is throttled independently below that ceiling. Garbage or rotating bearer values fall through to the IP key — the `wizzrobe_pat_` prefix is public, so bucketing solely on a presented token would let an attacker mint a fresh empty bucket per request. `X-Forwarded-For` is trusted only when `TRUST_PROXY_FORWARDED_FOR` is set, since the header is client-spoofable.

## Architecture

API handlers are a thin presentation layer: they authenticate, then delegate to the **service layer**, passing the token's user as `actor`. Services enforce permissions, validate, write audit logs, and queue Discord notifications — so the API automatically inherits all of that behaviour. Handlers contain no business logic and (aside from simple read lookups) no direct ORM writes.

## Endpoint catalogue

Grouped by domain (tag). See `/api/docs` for parameters, request/response schemas, and examples.

One module per group under [`api/routers/`](../../api/routers/), named after the group, with a matching module under [`api/schemas/`](../../api/schemas/). The cross-cutting pieces are `dependencies.py` (auth deps + `tenant_context_scope` + `require_feature` + `ServiceErrorRoute`), `rate_limit.py`, `_helpers.py` (shared load-or-404), and `_match_view.py` (match serialization).

### Health (`/api/health`) · `health.py`
- `GET /health` — **unauthenticated** liveness probe. Performs a trivial DB round-trip and returns `{"status": "ok"}`; returns `503` when the database is unreachable. Used by the container `HEALTHCHECK`.

### Web push (`/api/web-push`) · `web_push.py`
- `POST /web-push/rotate` — **unauthenticated**. Called by `static/sw.js` on `pushsubscriptionchange` to re-point a stored device row at the subscription its push service reissued. There is no session or token in that context; the request authenticates by carrying the retired subscription's `auth` secret, and a wrong secret returns the same `404` as an unknown endpoint. Detail: [features/web-push.md](../features/web-push.md#authenticating-a-rotation).

### Matches (`/api/matches`) · `matches.py`, `match_actions.py`
- `GET /matches` — list with filters (`match_id`, `stream_room_id`, `tournament_id`, `start_date`, `end_date`, `limit`); only approved crew are exposed.
- `GET /matches/{id}` — single match. Alongside the lifecycle timestamps the response carries `needs_review` (the proctor's dispute flag) and `review_note` (their words for why). Confirming clears the flag and leaves the note, so a confirmed match can return a note with `needs_review: false`.
- `POST /matches` — create (Staff/TA). `POST /matches/request` — player-initiated request.
- `PATCH /matches/{id}` · `DELETE /matches/{id}`.
- `POST /matches/{id}/stream-candidate` · `/stage` · `/stations`.
- Lifecycle: `POST /matches/{id}/seat` · `/start` · `/finish` · `/confirm` · `/result` · `/seed`. `/confirm` returns `400` unless the match is finished **and** a winner has been recorded.
- `POST /matches/{id}/review` — `{needs_review, note?}`. Raises or drops the dispute flag on a recorded result, returning the updated match. The two directions gate differently: flagging is `can_run_match` (the proctor's own call, and `400` unless the match is finished), clearing is `can_confirm_match` (`403` for a proctor). Clearing never touches `review_note`, and `/confirm` clears the flag on its own — see [match-participation.md](../features/match-participation.md#disputed-results).
- Self-actions: `POST /matches/{id}/crew` (sign up) · `DELETE /matches/{id}/crew/{role}` · `POST /matches/{id}/acknowledge`.
- Watching: `GET /matches/watching` (matches you watch) · `POST /matches/{id}/watch` · `DELETE /matches/{id}/watch`.

### Crew (`/api/crew`) · `crew.py`
- `POST /crew/{crew_type}/{crew_id}/approval` — approve/reject (Staff/TA/Crew Coordinator).
- `POST /crew/{crew_type}/{crew_id}/acknowledge` — crew member acknowledges their own approved assignment.

### Tournaments (`/api/tournaments`) · `tournaments.py`, `tournament_actions.py`
- `GET /tournaments?active_only=` (`active_only` returns only active tournaments, default `false`) · `GET /tournaments/{id}`.
- `POST` · `PATCH /{id}` · `DELETE /{id}`. `POST`/`PATCH` accept an optional per-tournament **tournament-days** override — `event_start_date`, `event_end_date` (`YYYY-MM-DD`), and `tournament_hours` (`{"YYYY-MM-DD": ["HH:MM open", "HH:MM close"]}`); each is nullable and falls back to the community setting when omitted (on `PATCH`, sending `null` clears an override back to inherit). An end before start, or a close not after open, returns `400`.
- `POST/DELETE /{id}/admins` and `/{id}/crew-coordinators` (Staff).
- `GET /tournaments/{id}/match-suggestion?player_ids=[&bracket_match_id=]` — suggested UTC start time for the given players (400 if no slot fits). `bracket_match_id` confines the suggestion to that matchup's round window.

### Stream rooms (`/api/stream-rooms`) · `stream_rooms.py`, `stream_room_actions.py`
- `GET /stream-rooms?active_only=` (`active_only` returns only active rooms, default `false`) · `GET /stream-rooms/{id}` · `POST` · `PATCH /{id}` · `DELETE /{id}` (Staff or Stream Manager).

### Users & roles (`/api/users`) · `users.py`
- `GET /users?role=` (Staff) returns the **members of the token's community**, not every account on the platform — identity is global but this list is not. `role` filters to users holding that role in the token's tenant. **Behaviour change:** it previously returned every `User` row on the deployment; there is deliberately no `?scope=all`, which would re-open the leak behind a parameter. A user appears once they are a member — granted a role, added from the Users tab, or created there. · `GET /users/me` · `GET /users/{id}` (self or Staff).
- `POST /users` (Staff) · `PATCH /users/me` · `PATCH /users/{id}` · `PATCH /users/{id}/admin` (Staff) · `PUT /users/{id}/tournaments`.
- `POST /users/{id}/roles` · `DELETE /users/{id}/roles/{role}` (Staff) — grant/revoke a role. Roles are per-tenant except `SUPER_ADMIN`; see [authentication.md § Roles](authentication.md#roles). (The Swagger `summary` strings still say "global role" — a stale docstring, not a different behaviour.)

### Player availability (`/api/users/me/availability`) · `player_availability.py`
- `GET` (own windows) · `PUT` (replace all windows) · `DELETE` (clear). Self-service for any authenticated user; windows feed match-time suggestions.

### Volunteers (`/api/volunteers`) · `volunteers.py`
Positions, shifts, and assignments for volunteer scheduling; the `/me/*` routes are self-service. All routes require an authenticated actor; writes use a non-read-only token.
- **Positions:** `GET /volunteers/positions?active_only=` (list; `active_only` limits to active positions, default `false`) · `POST /volunteers/positions` (create) · `PATCH /volunteers/positions/{id}` · `DELETE /volunteers/positions/{id}`.
- **Shifts:** `GET /volunteers/shifts?start=&end=` (list shifts in a UTC ISO-8601 window; `start`/`end` required) · `GET /volunteers/shifts/{id}` · `POST /volunteers/shifts` (create) · `DELETE /volunteers/shifts/{id}`.
- **Assignments:** `POST /volunteers/shifts/{shift_id}/assignments` (assign a volunteer; returns the assignment plus any warnings) · `DELETE /volunteers/assignments/{id}` (remove) · `POST /volunteers/assignments/{id}/acknowledge` (acknowledge your own assignment).
- **Coverage:** `GET /volunteers/coverage?start=&end=` — per-shift coverage across a UTC ISO-8601 window (`start`/`end` required).
- **Hours:** `GET /volunteers/hours?start=&end=` — every opted-in volunteer's served hours against the comp tiers, coordinator-only (staff or volunteer coordinator; 403 otherwise) · `GET /volunteers/hours/me` — your own. `start`/`end` are optional **local dates** that narrow the count; both default to the tenant's event window. Published assignments only, overlapping shifts counted once.
- **Self-service (`/me`):** `GET /volunteers/me/profile` · `POST /volunteers/me/opt-in` · `POST /volunteers/me/opt-out` · `GET /volunteers/me/availability` · `PUT /volunteers/me/availability` (replace windows) · `GET /volunteers/me/assignments?upcoming_only=` (your shift assignments; `upcoming_only` defaults to `true`, and unpublished drafts are never listed) · `DELETE /volunteers/me/assignments/{id}` (give a shift back, optional `{"reason": …}` body → 204; the coordinators are DMed).

### Triforce texts (`/api/triforce-texts`) · `triforce.py`
- `GET /mine?tournament_id=` (own; `tournament_id` required) · `GET ?tournament_id=&status=` (moderation, Staff/TA).
- `POST` (submit) · `POST /{id}/moderate` · `DELETE /{id}` (Staff/TA).

### Notifications (`/api/notifications`) · `notifications.py`
- `GET /preferences` · `PUT /preferences`.

### Audit (`/api/audit-logs`) · `audit.py`
- `GET /audit-logs` — paginated, admin only. Filters: `start`/`end` (UTC time bounds), `user_id`, `action_contains` (substring match on the action string); paginate with `limit` (1–500, default 100) and `offset` (default 0). Response includes the matching-entry `total`.

### System config (`/api/config`) · `system_config.py`
- `GET /config` · `GET /config/{key}` · `PUT /config/{key}` (Staff).

### Webhooks (`/api/webhooks`) · `webhooks.py`
- `GET /webhooks` (Staff) · `POST /webhooks` (Staff-write; response includes the signing `secret` once) · `GET/PUT/DELETE /webhooks/{id}` · `POST /webhooks/{id}/regenerate-secret` (returns a new secret once) · `GET /webhooks/{id}/deliveries`. Staff-managed outbound webhooks; see [webhooks.md](../features/webhooks.md).

### API tokens (`/api/tokens`) · `tokens.py`
- `GET /tokens` · `POST /tokens` · `DELETE /tokens/{id}` — manage your own tokens.

### Discord role mappings (`/api/discord-role-mappings`) · `discord_role_mappings.py`
- `GET /discord-role-mappings?guild_id=` (list, optionally per guild) · `POST` (create) · `DELETE /{id}` — manage Discord-guild-role → app-role mappings (Staff).

## Feature-flag gating

When the caller's tenant has not enabled a router's flag, the **whole router 404s** — as if the feature did not exist — rather than 403'ing. See [features/feature-flags.md](../features/feature-flags.md).

| Group | Flag |
|---|---|
| Triforce texts | `TRIFORCE_TEXTS` |
| Volunteers | `VOLUNTEERS` |
| Race room profiles, Race rooms | `RACETIME_ROOMS` |
| SpeedGaming | `SPEEDGAMING_ETL` |
| Async qualifiers, Async qualifier live races | `ASYNC_QUALIFIERS` |
| Brackets | `BRACKETS` |

Every other group stays open, including presets, seeds, racetime bots, discord events and service health. `GET /seeds/randomizers` filters on a different axis — the randomizer API credentials the tenant has configured, not a flag (see [seed-generation.md](seed-generation.md#per-tenant-credentials)).

## Online-tournament features

Two of these groups are **global / platform** resources gated by `require_super_admin` / `require_super_admin_write` ([`api/dependencies.py`](../../api/dependencies.py)), which check the global `SUPER_ADMIN` role (`UserRole` with `tenant=NULL`) rather than tenant STAFF. The tenant-role-gated groups (presets, sync, qualifiers) use the coarse `require_api_actor` / `require_write_actor` HTTP dep and let the service enforce the finer role (`PRESET_MANAGER` / `SYNC_ADMIN` / `QUALIFIER_ADMIN` beyond STAFF), so a sub-STAFF token with the right role is accepted rather than 403'd.

### Presets (`/api/presets`) · `presets.py`
Tenant-authored seed presets (service gate `can_manage_presets`).
- `GET /presets` (opt `?randomizer=`) · `GET /presets/selectable` · `GET /presets/{id}`.
- `POST /presets` · `PATCH /presets/{id}` · `DELETE /presets/{id}` · `POST /presets/import-builtins` (import the built-in preset files).

### Race room profiles (`/api/race-room-profiles`) · `race_room_profiles.py`
Reusable racetime room settings (service gate `can_manage_sync`).
- `GET /race-room-profiles` · `/selectable` · `/{id}`; `POST` · `PATCH /{id}` · `DELETE /{id}`.

### Racetime bots (`/api/racetime-bots`) — **super-admin, global** · `racetime_bots.py`
Platform-managed racetime bots (no tenant FK). Responses are the secret-free
`RacetimeBotService.serialize(bot)` projection — `client_secret` is never returned.
- `GET /racetime-bots` · `/active` · `/{id}` (super-admin).
- `POST` · `PATCH /{id}` · `DELETE /{id}` (super-admin write).
- `GET /racetime-bots/{id}/grants` · `POST /{id}/grants` (`{tenant_id}`) · `DELETE /{id}/grants/{tenant_id}` — tenant authorization grants.

### Race rooms (`/api/race-rooms`) · `race_rooms.py`
- `GET /race-rooms/open` (Staff; filtered to your tenant) · `GET /race-rooms/by-match/{match_id}`.
- `POST /race-rooms` (`{match_id}`, manual create) · `POST /{id}/cancel` (`{reason?}`) · `PATCH /{id}/status` (`{status}`). Cancel/status add an explicit `can_manage_sync` gate (the service transitions are system-path/ungated). System internals (`get_by_slug`, `record_finish`, websocket event dispatch, auto-create) are **not** exposed.

### SpeedGaming (`/api/speedgaming`) · `speedgaming.py`
SpeedGaming schedule ETL event links (service gate `can_manage_sync`).
- `GET /speedgaming/links` · `GET /links/{id}/episodes` (episode `payload` blob omitted).
- `POST /links` · `PATCH /links/{id}` · `DELETE /links/{id}` · `POST /links/{id}/sync` (returns the `SyncResult` tallies).

### Discord events (`/api/discord-events`) · `discord_events.py`
Discord Scheduled Events mirror (service gate `can_manage_sync`).
- `GET /discord-events/tournaments` (per-tournament opt-in settings) · `GET /discord-events/events` (mirrored events).
- `PATCH /discord-events/tournaments/{id}` (settings) · `POST /discord-events/reconcile` (returns the `ReconcileResult` tallies).

### Service health (`/api/service-health`) · `service_health.py`
External-dependency health board (the HTTP dep is the only authz; the service does not re-gate).
- `GET /service-health` — tenant subset (Staff).
- `GET /service-health/board` — full snapshot (super-admin).
- `POST /service-health/refresh` — force a refresh (super-admin write; always `alert=False`, so an API call never DMs).

### Seeds (`/api/seeds`) · `seeds.py`
- `GET /seeds/randomizers` — the randomizers this community can actually roll + their `supports_triforce_texts` flag. A key-gated backend (`ootr`, `smmap`, `dk64r`) appears only once the community has configured its credential.
- `POST /seeds` (`{randomizer, preset_id?}`) — roll a seed (loads the tenant-scoped preset when given; unsupported randomizer → 400; honors `MOCK_SEEDGEN`). Generation is ungated, so the write token is the authz. A key-gated randomizer the community has not configured → **400** naming the missing credential.

### Async qualifiers (`/api/async-qualifiers`) · `async_qualifiers.py`
Self-paced permalink-pool qualifiers (mixed auth: admin reads/writes gate
`can_admin_qualifier`; player run methods enforce ownership; `/open` and `/{id}/public`
are public-but-authenticated; the leaderboard is hidden while the window is open for non-admins).
- **Reads:** `GET /async-qualifiers` · `/open` · `/{id}` · `/{id}/public` · `/{id}/admins` · `/{id}/pools` · `/{id}/pools/available` · `/{id}/review-queue` · `/{id}/leaderboard` · `/{id}/me/runs` · `/{id}/me/active-run` · `/runs/{run_id}/notes`.
- **Qualifier/admin/pool/permalink writes:** `POST /async-qualifiers` · `PATCH`/`DELETE /{id}`; `POST`/`DELETE /{id}/admins[/{user_id}]`; `POST /{id}/pools`, `PATCH`/`DELETE /pools/{pool_id}`; `POST /pools/{pool_id}/permalinks` (+ `/bulk`, `/roll`), `PATCH`/`DELETE /permalinks/{permalink_id}`.
- **Player run lifecycle:** `POST /{id}/runs` (start) · `POST /runs/{run_id}/submit|forfeit|reattempt`.
  `submit` 400s when the claimed `elapsed_seconds` exceeds the wall clock since the
  server stamped `started_at` — a run cannot have taken longer than it has existed.
  The run stays in progress, so the client can correct the time and resubmit. Every
  successful submit records `measured_seconds` (that wall clock) on the run response
  beside the runner's claim.
- **Review:** `POST /runs/{run_id}/claim|release|review` · `POST /runs/{run_id}/grant-reattempt`
  (admin; voids a runner's terminal run ignoring their `allowed_reattempts`, reason
  required) · `GET /{qualifier_id}/runs` (admin; every run, since the review queue holds
  only finished+pending rows and a forfeit is written straight to approved).
  `review` 400s on a rejection with a blank `note` — the reason is stored as a run note
  and DM'd to the runner. An approval's note stays optional.

### Async qualifier live races (`/api/async-qualifiers/live-races`) · `async_qualifier_live_races.py`
Synchronous racetime races for a qualifier pool (service gate `can_admin_qualifier`).
- `GET /async-qualifiers/live-races?qualifier_id=` · `/{id}` · `/{id}/runs`.
- `POST /async-qualifiers/live-races` (create) · `POST /{id}/open-room` · `DELETE /{id}` (cancel). Inbound racetime capture (`mark_in_progress`, `record_finish`) is **not** exposed.

### Brackets (`/api/brackets`) · `brackets.py`
Native tournament brackets. Reads take any token and are tenant-scoped in-service; writes reject read-only tokens at the HTTP layer and re-gate in `BracketService` — **Staff** everywhere except `POST /matches/{id}/games`, which also accepts the tournament's admins and the matchup's own two entrants (in a bracket-run tournament the bracket is the only way a player schedules at all). Thin wrappers over the service; schemas in [`api/schemas/brackets.py`](../../api/schemas/brackets.py). Behaviour — formats, advancement, roster rules, series semantics, who may schedule — is documented in [brackets.md](../features/brackets.md).
- **Reads:** `GET /brackets?tournament_id=` (stages) · `/brackets/entrants?tournament_id=` (roster) · `/brackets/{id}` · `/brackets/{id}/matches` · `/brackets/{id}/open-matches` · `/brackets/{id}/entries` · `/brackets/matches/{match_id}` (one matchup with its `games`) · `/brackets/my-open-matches?tournament_id=` (the **caller's** OPEN matchups with a free game slot and both entrants user-linked — the peer of the Challonge unscheduled-match list) · `/brackets/{id}/standings` · `/brackets/advancing-preview?tournament_id=&from_stage_order=` (dry run of the advance, writing nothing).
- **Authoring / roster:** `POST /brackets` · `PATCH /brackets/{id}` (`{name?, stage_order?, config?, format?}`, DRAFT-only, omitted fields left alone; the **format** is editable because a DRAFT stage has no match graph) · `DELETE /brackets/{id}` (204, DRAFT-only) · `PUT /brackets/{id}/rounds` (`{rounds}` — the per-round `{best_of, scheduled_at, scheduled_end}` metadata, or null to clear — `scheduled_end` must be after `scheduled_at`, and the pair bounds match-time suggestions for the round; the one definition edit allowed **after** a stage starts, since round chrome never touches the graph) · `PATCH /brackets/{id}/seeds` (`{seeds: {entry_id: seed|null}}`, DRAFT-only; the whole resulting seeding is validated before any write, so a duplicate or `<1` seed changes nothing, and the new entry order is returned) · `POST /brackets/entrants` · `POST /brackets/entrants/import` (`{tournament_id}` — one linked entrant per enrolled player not already rostered, returning only the new ones; idempotent) · `PATCH /brackets/entrants/{entrant_id}/user` (`{user_id}`, null to unlink — allowed in any state, since the link is what makes the entrant schedulable and notifiable) · `POST /brackets/entrants/{entrant_id}/drop` · `POST /brackets/{id}/entries` · `DELETE /brackets/entries/{entry_id}` (204, DRAFT-only un-enrollment) · `POST /brackets/entries/{entry_id}/retire` (mark the entry DROPPED — allowed in any state; the played results stand while Swiss stops pairing them and advancement skips them).
- **Lifecycle:** `POST /brackets/{id}/start` · `POST /brackets/matches/{match_id}/result` (`{winner_entry_id, entry1_score?, entry2_score?, forfeit?}`) · `PATCH /brackets/matches/{match_id}/result` (same body — staff correction of an already-COMPLETE match) · `POST /brackets/{id}/complete` (optional `{tie_breaks: {entry_id: rank}}` — resolves entries the standings pass left sharing a rank, applied on both Swiss and round robin) · `POST /brackets/{id}/cancel` (abandon a started stage: terminal, no `final_rank`, no champion; rejected on a COMPLETE stage) · `POST /brackets/advance-stage?tournament_id=` (`{from_stage_order}`).
- **Series:** `PATCH /brackets/matches/{match_id}/best-of` (`{best_of}` — odd, or null to fall back to the round's value; rejected once games exist) · `POST /brackets/matches/{match_id}/games` (`{scheduled_date, scheduled_time, stream_room_id?, comment?}` — books the **next** game into a real `Match`; the game number is server-assigned, so call it once per game, and all N slots may be booked up front). `stream_room_id` is staff-only and 400s for an entrant rather than being silently dropped.
- **Linking (staff):** `POST /brackets/matches/{match_id}/games/link` (`{scheduled_match_id}`) attaches an already-created `Match` as the matchup's next game — for a match scheduled through the ordinary editor. Its players must be exactly the matchup's two entrants (400 otherwise), same tournament, not already linked. `DELETE /brackets/games/by-match/{scheduled_match_id}` detaches an unplayed one (404 when the match backs no game, 400 once it has a result); the `Match` itself is left in place.

Two response shapes are worth calling out because they differ from the UI's view of the same data:

- `BracketMatchResponse` has **no `match_id`** — a bracket match is a *series*, so its scheduled matches live in the nested `games` list (empty until a game is booked; rows are created lazily and unneeded ones are cancelled when the series clinches). It also carries `best_of`, `entry1_score`/`entry2_score`/`forfeit`, and a derived **`status`** — the cross-surface `MatchStatus` (`pending` / `unscheduled` / `scheduled` / `checked_in` / `live` / `awaiting_result` / `complete` / `needs_reschedule`) the web bracket paints and the Discord DM quotes, so a consumer sees `live` mid-race instead of re-deriving it from game timestamps. Populated on the two list reads (`/matches`, `/open-matches`); `null` elsewhere.
- `GET /brackets/{id}/standings` returns `[{group_number, rows}]` — round robin one group per pool (ascending, `null` last), Swiss a single `null` group. Each row carries `display_name`, `seed`, both drop levels (`status` = this stage's entry, `entrant_status` = the roster), live `rank`, `points`, `wins`/`draws`/`losses`/`byes`, the `tiebreakers` chain and `tied_with`, and the persisted `final_rank` (null until the stage completes; it can differ from `rank` when staff hand-resolved a tie). Rows come back in rank order and dropped entries stay listed. Elimination formats have no points table and **400** — read their placement from `/matches` and each entry's `final_rank`.

## Tests

Integration tests live in [`tests/`](../../tests/) as `test_api_<resource>.py`, roughly one per group. They use the in-memory SQLite `db` fixture and the helpers in [`tests/api_helpers.py`](../../tests/api_helpers.py) (full app + token-authenticated client; pass `roles=[Role.SUPER_ADMIN]` for a global super-admin token).

Every group covers the same baseline matrix plus its own resource-specific cases: happy-path read, `401` unauthenticated, `403` read-only-token write, cross-tenant isolation, and `403` for a role-less token.
