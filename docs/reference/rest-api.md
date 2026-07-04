# REST API Reference

_Reference for SGLMan's REST API: the router package in [`api/`](../../api/) and the FastAPI app metadata in [`main.py`](../../main.py). Part of the [documentation index](../README.md)._

## Overview

| | |
|---|---|
| Title | SGL On Site API |
| Version | 1.0.0 |
| Base path | `/api` |
| Swagger UI | `/api/docs` |
| ReDoc | `/api/redoc` |
| Source | [`api/`](../../api/) package — `routers/`, `schemas/`, `dependencies.py`; mounted in [`main.py`](../../main.py) |

The API is served by the same Uvicorn process as the NiceGUI frontend. The interactive Swagger UI at `/api/docs` is the authoritative, always-current catalogue (every endpoint, schema, and example); this page summarises the model.

## Authentication

**Every endpoint requires a personal bearer token**, with one exception: the unauthenticated `GET /api/health` liveness probe (see [Health](#health-apihealth)).

Generate a token on your profile page (**Edit Your Information → API Tokens**), then send it on each request:

```
Authorization: Bearer sglman_pat_xxxxxxxx...
```

- A token **acts as its owning user** and inherits that user's exact permissions and scope — the same `AuthService` role checks that gate the web UI apply. A non-staff token gets `403` from staff-only routes; a Tournament Admin token can edit only its own tournaments; a self-action (acknowledge, sign up, edit own profile) only ever affects the token's user.
- A token may be flagged **read-only**, in which case it can call read (`GET`) endpoints only; any write returns `403`.
- Tokens are stored as a SHA-256 hash (the plaintext is shown once at creation), support an optional expiry, and can be revoked at any time. Implementation: [`ApiToken`](../../models.py) model, [`ApiTokenService`](../../application/services/api_token_service.py), auth dependency in [`api/dependencies.py`](../../api/dependencies.py).

Tokens can also be managed programmatically via the `/api/tokens` endpoints (creating/revoking a token requires a non-read-only token, so a read-only token can never mint a more privileged one).

### Status codes

| Code | Meaning |
|---|---|
| `401` | Missing, malformed, unknown, revoked, or expired token |
| `403` | Inactive account, read-only token used for a write, or the user lacks the required role/scope (`PermissionError` from a service) |
| `400` | Validation/business-rule error (`ValueError` from a service) |
| `404` | Entity not found |
| `422` | Request body/query failed schema validation |

`PermissionError`/`ValueError` → `403`/`400` translation is handled by `ServiceErrorRoute` in [`api/dependencies.py`](../../api/dependencies.py), scoped to the API routers so the NiceGUI frontend is unaffected.

## Architecture

API handlers are a thin presentation layer: they authenticate, then delegate to the **service layer**, passing the token's user as `actor`. Services enforce permissions, validate, write audit logs, and queue Discord notifications — so the API automatically inherits all of that behaviour. Handlers contain no business logic and (aside from simple read lookups) no direct ORM writes.

## Endpoint catalogue

Grouped by domain (tag). See `/api/docs` for parameters, request/response schemas, and examples.

### Router source files

| Router | Source |
|---|---|
| Health | [`api/routers/health.py`](../../api/routers/health.py) |
| Matches (read) | [`api/routers/matches.py`](../../api/routers/matches.py) |
| Match actions (write) | [`api/routers/match_actions.py`](../../api/routers/match_actions.py) |
| Crew | [`api/routers/crew.py`](../../api/routers/crew.py) |
| Tournaments (read) | [`api/routers/tournaments.py`](../../api/routers/tournaments.py) |
| Tournament actions (write) | [`api/routers/tournament_actions.py`](../../api/routers/tournament_actions.py) |
| Stream rooms | [`api/routers/stream_rooms.py`](../../api/routers/stream_rooms.py) |
| Stream room actions | [`api/routers/stream_room_actions.py`](../../api/routers/stream_room_actions.py) |
| Users | [`api/routers/users.py`](../../api/routers/users.py) |
| Player availability | [`api/routers/player_availability.py`](../../api/routers/player_availability.py) |
| Volunteers | [`api/routers/volunteers.py`](../../api/routers/volunteers.py) |
| Triforce texts | [`api/routers/triforce.py`](../../api/routers/triforce.py) |
| Notifications | [`api/routers/notifications.py`](../../api/routers/notifications.py) |
| Audit | [`api/routers/audit.py`](../../api/routers/audit.py) |
| System config | [`api/routers/system_config.py`](../../api/routers/system_config.py) |
| API tokens | [`api/routers/tokens.py`](../../api/routers/tokens.py) |
| Discord role mappings | [`api/routers/discord_role_mappings.py`](../../api/routers/discord_role_mappings.py) |
| Webhooks | [`api/routers/webhooks.py`](../../api/routers/webhooks.py) |

### Health (`/api/health`)
- `GET /health` — **unauthenticated** liveness probe. Performs a trivial DB round-trip and returns `{"status": "ok"}`; returns `503` when the database is unreachable. Used by the container `HEALTHCHECK`.

### Matches (`/api/matches`)
- `GET /matches` — list with filters (`match_id`, `stream_room_id`, `tournament_id`, `start_date`, `end_date`, `limit`); only approved crew are exposed.
- `GET /matches/{id}` — single match.
- `POST /matches` — create (Staff/TA). `POST /matches/request` — player-initiated request.
- `PATCH /matches/{id}` · `DELETE /matches/{id}`.
- `POST /matches/{id}/stream-candidate` · `/stage` · `/stations`.
- Lifecycle: `POST /matches/{id}/seat` · `/start` · `/finish` · `/confirm` · `/result` · `/seed`.
- Self-actions: `POST /matches/{id}/crew` (sign up) · `DELETE /matches/{id}/crew/{role}` · `POST /matches/{id}/acknowledge`.
- Watching: `GET /matches/watching` (matches you watch) · `POST /matches/{id}/watch` · `DELETE /matches/{id}/watch`.

### Crew (`/api/crew`)
- `POST /crew/{crew_type}/{crew_id}/approval` — approve/reject (Staff/TA/Crew Coordinator).
- `POST /crew/{crew_type}/{crew_id}/acknowledge` — crew member acknowledges their own approved assignment.

### Tournaments (`/api/tournaments`)
- `GET /tournaments?active_only=` (`active_only` returns only active tournaments, default `false`) · `GET /tournaments/{id}`.
- `POST` · `PATCH /{id}` · `DELETE /{id}`.
- `POST/DELETE /{id}/admins` and `/{id}/crew-coordinators` (Staff).
- `GET /tournaments/{id}/match-suggestion?player_ids=` — suggested UTC start time for the given players (400 if no slot fits).

### Stream rooms (`/api/stream-rooms`)
- `GET /stream-rooms?active_only=` (`active_only` returns only active rooms, default `false`) · `GET /stream-rooms/{id}` · `POST` · `PATCH /{id}` · `DELETE /{id}` (Staff or Stream Manager).

### Users & roles (`/api/users`)
- `GET /users?role=` (Staff; `role` optionally filters to users holding that global role) · `GET /users/me` · `GET /users/{id}` (self or Staff).
- `POST /users` (Staff) · `PATCH /users/me` · `PATCH /users/{id}` · `PATCH /users/{id}/admin` (Staff) · `PUT /users/{id}/tournaments`.
- `POST /users/{id}/roles` · `DELETE /users/{id}/roles/{role}` (Staff).

### Player availability (`/api/users/me/availability`)
- `GET` (own windows) · `PUT` (replace all windows) · `DELETE` (clear). Self-service for any authenticated user; windows feed match-time suggestions.

### Volunteers (`/api/volunteers`)
Positions, shifts, and assignments for volunteer scheduling; the `/me/*` routes are self-service. All routes require an authenticated actor; writes use a non-read-only token.
- **Positions:** `GET /volunteers/positions?active_only=` (list; `active_only` limits to active positions, default `false`) · `POST /volunteers/positions` (create) · `PATCH /volunteers/positions/{id}` · `DELETE /volunteers/positions/{id}`.
- **Shifts:** `GET /volunteers/shifts?start=&end=` (list shifts in a UTC ISO-8601 window; `start`/`end` required) · `GET /volunteers/shifts/{id}` · `POST /volunteers/shifts` (create) · `DELETE /volunteers/shifts/{id}`.
- **Assignments:** `POST /volunteers/shifts/{shift_id}/assignments` (assign a volunteer; returns the assignment plus any warnings) · `DELETE /volunteers/assignments/{id}` (remove) · `POST /volunteers/assignments/{id}/acknowledge` (acknowledge your own assignment).
- **Coverage:** `GET /volunteers/coverage?start=&end=` — per-shift coverage across a UTC ISO-8601 window (`start`/`end` required).
- **Self-service (`/me`):** `GET /volunteers/me/profile` · `POST /volunteers/me/opt-in` · `POST /volunteers/me/opt-out` · `GET /volunteers/me/availability` · `PUT /volunteers/me/availability` (replace windows) · `GET /volunteers/me/assignments?upcoming_only=` (your shift assignments; `upcoming_only` defaults to `true`).

### Triforce texts (`/api/triforce-texts`)
- `GET /mine` (own) · `GET ?tournament_id=&status=` (moderation, Staff/TA).
- `POST` (submit) · `POST /{id}/moderate` · `DELETE /{id}` (Staff/TA).

### Notifications (`/api/notifications`)
- `GET /preferences` · `PUT /preferences`.

### Audit (`/api/audit-logs`)
- `GET /audit-logs` — paginated, admin only. Filters: `start`/`end` (UTC time bounds), `user_id`, `action_contains` (substring match on the action string); paginate with `limit` (1–500, default 100) and `offset` (default 0). Response includes the matching-entry `total`.

### System config (`/api/config`)
- `GET /config` · `GET /config/{key}` · `PUT /config/{key}` (Staff).

### Webhooks (`/api/webhooks`)
- `GET /webhooks` (Staff) · `POST /webhooks` (Staff-write; response includes the signing `secret` once) · `GET/PUT/DELETE /webhooks/{id}` · `POST /webhooks/{id}/regenerate-secret` (returns a new secret once) · `GET /webhooks/{id}/deliveries`. Staff-managed outbound webhooks; see [webhooks.md](../features/webhooks.md).

### API tokens (`/api/tokens`)
- `GET /tokens` · `POST /tokens` · `DELETE /tokens/{id}` — manage your own tokens.

### Discord role mappings (`/api/discord-role-mappings`)
- `GET /discord-role-mappings?guild_id=` (list, optionally per guild) · `POST` (create) · `DELETE /{id}` — manage Discord-guild-role → app-role mappings (Staff).

## Tests

Integration tests live in [`tests/`](../../tests/): `test_api_tokens.py`, `test_api_matches.py`, `test_api_reads.py`, `test_api_match_writes.py`, `test_api_admin_writes.py`, `test_api_phase5_writes.py`. They use the in-memory SQLite `db` fixture and the helpers in [`tests/api_helpers.py`](../../tests/api_helpers.py) (full app + token-authenticated client).
