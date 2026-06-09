# REST API Reference

_Reference for SGLMan's public REST API: the router in [`api.py`](../../api.py) and the FastAPI app metadata in [`main.py`](../../main.py). Part of the [documentation index](../README.md)._

## Overview

| | |
|---|---|
| Title | Speedgaming Live Manager API |
| Version | 1.0.0 |
| Description | API for managing tournaments, matches, players, commentators, and trackers for Speedgaming Live events |
| Base path | `/api` |
| Swagger UI | `/api/docs` |
| ReDoc | `/api/redoc` |
| Source | [`api.py`](../../api.py) (router, models, handler), [`main.py`](../../main.py) (app metadata, mounting) |

The FastAPI app is created in [`main.py`](../../main.py) with custom docs URLs (`docs_url="/api/docs"`, `redoc_url="/api/redoc"` instead of the FastAPI defaults `/docs` and `/redoc`). It mounts the `APIRouter` from [`api.py`](../../api.py) under the `/api` prefix. The router carries a `Matches` tag and a shared `404 Not found` response in its OpenAPI metadata; `main.py` adds a second `api` tag at include time, so the endpoint appears under both groups in Swagger. The API is served by the same Uvicorn process as the NiceGUI frontend — see [deployment.md](../deployment.md) for ports and topology and [architecture.md](../architecture.md) for the process model.

### Public, unauthenticated, read-only

No `/api` route requires authentication, and the router defines only `GET` endpoints. The implications:

- The API exposes only data that is already public on the web UI's schedule pages: match times, titles, tournaments, stream rooms, players, and generated seeds.
- Commentators and trackers are returned **only when approved** — pending crew signups are never exposed (see [Approved-only crew filtering](#approved-only-crew-filtering)).
- No session, cookie, or token is read; nothing in the API grants write access.

The web app's Discord OAuth routes are separate from the API — see [Auth-related HTTP routes](#auth-related-http-routes).

## GET /api/matches

Returns a list of matches with related tournament, stream room, seed, player, and approved-crew data. This is currently the only API endpoint.

### Query parameters

All parameters are optional. Filters combine with **AND**.

| Parameter | Type | Repeatable | Default | Constraints | Effect |
|---|---|---|---|---|---|
| `match_id` | int | yes | — | — | `id IN (...)` over all supplied values |
| `stream_room_id` | int | yes | — | — | `stream_room_id IN (...)` |
| `tournament_id` | int | yes | — | — | `tournament_id IN (...)` |
| `start_date` | ISO 8601 datetime | no | — | — | `scheduled_at >= start_date` (inclusive) |
| `end_date` | ISO 8601 datetime | no | — | — | `scheduled_at <= end_date` (inclusive) |
| `limit` | int | no | `100` | `1 ≤ limit ≤ 500` | Maximum number of matches returned |

Notes:

- **Repeatable parameters** are passed by repeating the key (`?stream_room_id=1&stream_room_id=2`). Multiple values of the same parameter OR together; different parameters AND together. For example, `?tournament_id=2&stream_room_id=1` returns only matches in tournament 2 *and* stream room 1.
- **`end_date` is inclusive.** The OpenAPI description text says "before this date/time", but the implemented filter is `scheduled_at__lte` — a match scheduled exactly at `end_date` is returned. (`start_date` is also inclusive, as documented.)
- **Unscheduled matches and date filters.** Both date filters compare against `scheduled_at`, so matches with no scheduled time never match a date-filtered request.
- **Datetime format.** FastAPI parses the values as ISO 8601 (e.g. `2026-03-01T18:00:00Z`). Prefer the `Z` suffix over a `+00:00` offset — a literal `+` in a query string decodes as a space. Stored values are UTC; passing a naive datetime leaves the aware-vs-naive comparison at the boundary ambiguous, so include an explicit offset.

### Ordering, limit, prefetching

- Results are ordered by `scheduled_at` ascending; `limit` is applied after ordering.
- There is no offset/pagination parameter — narrow the result set with date filters instead.
- The query prefetches every serialized relation in batched follow-up queries (no per-row N+1): `tournament`, `stream_room`, `generated_seed`, `players__user`, `commentators__user`, `trackers__user`.

### Approved-only crew filtering

Only approved commentators and trackers are public. The filtering happens **in Python, after the database query**, not in SQL:

1. Each fetched `Match` is converted to a `MatchResponse` with `MatchResponse.model_validate(match, from_attributes=True)`.
2. The `commentators` and `trackers` lists on the Pydantic copy are filtered to entries with `approved == True`.

Per the comment in [`api.py`](../../api.py), it works this way because:

- Tortoise reverse relations are **read-only** — the prefetched `match.commentators` / `match.trackers` collections on the ORM objects cannot be stripped in place.
- Under Pydantic v2, FastAPI's `response_model` serialization reads attributes directly and **never invokes a custom `from_orm` hook**, so there is no serialization-time hook where the filtering could live.

Converting to the response model first yields mutable Pydantic copies whose lists can be filtered before the (already-validated) objects are returned. As a result, `approved` is always `true` in API responses.

### Status codes

| Code | When |
|---|---|
| `200` | Success — JSON array, possibly empty. An empty filter result is `200` with `[]`, never `404`. |
| `422` | Validation error — `limit` outside 1–500, non-integer ID values, or unparseable datetimes. |

The router metadata declares a generic `404 Not found` response that shows up in the OpenAPI schema, but no current code path returns it.

## Response schema

The endpoint's `response_model` is `List[MatchResponse]`. All Pydantic models live in [`api.py`](../../api.py) and mirror a subset of the ORM models — see [data-model.md](data-model.md) for the underlying model semantics. All datetimes are UTC, serialized as ISO 8601.

### UserBase

| Field | Type | Description |
|---|---|---|
| `id` | int | Internal user ID |
| `username` | string | Discord username |
| `display_name` | string \| null | Preferred display name; null when unset |
| `discord_id` | int \| null | Discord snowflake ID (required on the ORM model; typed optional in the API schema) |
| `pronouns` | string \| null | User-set pronouns |

### TournamentBase

| Field | Type | Description |
|---|---|---|
| `id` | int | Tournament ID |
| `name` | string | Tournament name |
| `description` | string \| null | Free-text description |
| `seed_generator` | string \| null | Randomizer seed generator identifier (e.g. `alttpr`) |
| `bracket_url` | string \| null | Link to the bracket |
| `rules_url` | string \| null | Link to the rules document |
| `tournament_format` | string \| null | Free-text format label |
| `average_match_duration` | int \| null | Average match length, in minutes |
| `max_match_duration` | int \| null | Maximum match length, in minutes |

### StreamRoomBase

| Field | Type | Description |
|---|---|---|
| `id` | int | Stream room ID |
| `name` | string | Stage name (unique, e.g. "Stage 1") |
| `stream_url` | string \| null | Stream URL for the room |

### GeneratedSeedBase

| Field | Type | Description |
|---|---|---|
| `id` | int | Seed record ID |
| `seed_url` | string | URL of the generated seed |
| `seed_info` | string \| null | Generator-provided seed metadata |
| `created_at` | datetime | When the seed record was created (UTC) |

### PlayerInfo

| Field | Type | Description |
|---|---|---|
| `id` | int | `MatchPlayers` row ID (the player-in-match record, not the user ID) |
| `user` | UserBase | The player |
| `finish_rank` | int \| null | Final placement; null until recorded |
| `assigned_station` | string \| null | Assigned station label |

### CommentatorInfo

| Field | Type | Description |
|---|---|---|
| `id` | int | `Commentator` signup row ID |
| `user` | UserBase | The commentator |
| `approved` | bool | Always `true` in responses; unapproved signups are filtered out |

### TrackerInfo

| Field | Type | Description |
|---|---|---|
| `id` | int | `Tracker` signup row ID |
| `user` | UserBase | The tracker |
| `approved` | bool | Always `true` in responses; unapproved signups are filtered out |

### MatchResponse

| Field | Type | Description |
|---|---|---|
| `id` | int | Match ID |
| `tournament` | TournamentBase | Owning tournament (always present) |
| `title` | string \| null | Optional display title (e.g. round name) |
| `stream_room` | StreamRoomBase \| null | Assigned stage; null when unassigned |
| `generated_seed` | GeneratedSeedBase \| null | Seed attached to the match, if any |
| `scheduled_at` | datetime \| null | Scheduled start time (UTC) |
| `seated_at` | datetime \| null | Check-in time — set when the match reaches "Checked In" (UTC) |
| `finished_at` | datetime \| null | Completion time (UTC) |
| `comment` | string \| null | Free-text comment on the match |
| `players` | PlayerInfo[] | Players in the match; defaults to `[]` |
| `commentators` | CommentatorInfo[] | Approved commentators only; defaults to `[]` |
| `trackers` | TrackerInfo[] | Approved trackers only; defaults to `[]` |
| `created_at` | datetime | Row creation time (UTC) |
| `updated_at` | datetime | Last modification time (UTC) |

The ORM `Match` model also has `started_at`, `confirmed_at`, and `is_stream_candidate`; these are not part of the API schema, so the "Checked In" and "In Progress" lifecycle states are not distinguishable from a response.

### Example response

```json
[
  {
    "id": 42,
    "tournament": {
      "id": 3,
      "name": "ALTTPR Invitational",
      "description": "Round robin into a top-8 bracket.",
      "seed_generator": "alttpr",
      "bracket_url": "https://example.com/bracket",
      "rules_url": "https://example.com/rules",
      "tournament_format": "best-of-3",
      "average_match_duration": 105,
      "max_match_duration": 150
    },
    "title": "Winners Semifinal 1",
    "stream_room": {
      "id": 1,
      "name": "Stage 1",
      "stream_url": "https://twitch.tv/speedgaming"
    },
    "generated_seed": {
      "id": 88,
      "seed_url": "https://alttpr.com/h/AbCdEf1234",
      "seed_info": "Open 7/7, fast ganon",
      "created_at": "2026-03-01T16:30:00Z"
    },
    "scheduled_at": "2026-03-01T17:00:00Z",
    "seated_at": "2026-03-01T16:45:12Z",
    "finished_at": null,
    "comment": "Restream on the main channel",
    "players": [
      {
        "id": 301,
        "user": {
          "id": 12,
          "username": "runner_one",
          "display_name": "Runner One",
          "discord_id": 123456789012345678,
          "pronouns": "she/her"
        },
        "finish_rank": null,
        "assigned_station": "Station 2"
      },
      {
        "id": 302,
        "user": {
          "id": 27,
          "username": "runner_two",
          "display_name": null,
          "discord_id": 234567890123456789,
          "pronouns": null
        },
        "finish_rank": null,
        "assigned_station": "Station 3"
      }
    ],
    "commentators": [
      {
        "id": 51,
        "user": {
          "id": 33,
          "username": "caster",
          "display_name": "The Caster",
          "discord_id": 345678901234567890,
          "pronouns": "he/him"
        },
        "approved": true
      }
    ],
    "trackers": [
      {
        "id": 17,
        "user": {
          "id": 41,
          "username": "tracker_person",
          "display_name": null,
          "discord_id": 456789012345678901,
          "pronouns": "they/them"
        },
        "approved": true
      }
    ],
    "created_at": "2026-02-20T03:11:09Z",
    "updated_at": "2026-03-01T16:45:12Z"
  }
]
```

## Example requests

```bash
# Basic: next 100 matches (default limit), ordered by scheduled_at
curl 'http://localhost:8000/api/matches'

# Repeated filter params: matches on Stage 1 or Stage 2 within one tournament
curl 'http://localhost:8000/api/matches?stream_room_id=1&stream_room_id=2&tournament_id=3'

# Date window: everything scheduled on a given (UTC) day — both bounds inclusive
curl 'http://localhost:8000/api/matches?start_date=2026-03-01T00:00:00Z&end_date=2026-03-01T23:59:59Z'

# Specific matches with the maximum limit (limit=501 would return 422)
curl 'http://localhost:8000/api/matches?match_id=42&match_id=43&limit=500'
```

## Auth-related HTTP routes

`/login`, `/logout`, and `/oauth/callback` are Discord OAuth routes on the web application (registered by `middleware/auth.py`), not part of the `/api` router — they serve the NiceGUI frontend's session handling and are not usable as API authentication. See [authentication.md](authentication.md).

## Adding an endpoint

1. **Route** — add the path operation to the `router` in [`api.py`](../../api.py), or create a new `APIRouter` module and include it from [`main.py`](../../main.py) with the `/api` prefix. Set router-level `tags=[...]` so the endpoint groups sensibly in Swagger, and fill in `summary`/`description` for the generated docs.
2. **Response models** — define explicit Pydantic models for everything returned and set `response_model` on the route; never return ORM objects unshaped. Mark nullable columns `Optional` and default list relations with `Field(default_factory=list)`.
3. **Layering** — read-only queries directly against the ORM are acceptable in API handlers; anything that writes must go through the service layer (see [architecture.md](../architecture.md)).
4. **Keep it public-safe** — the API has no authentication, so a new endpoint must expose only already-public data. The approved-only crew filter in `GET /matches` is the precedent for stripping non-public rows.
5. **Tests** — follow [`tests/test_api_matches.py`](../../tests/test_api_matches.py): build a minimal `FastAPI` app with only the router mounted (`prefix='/api'`, which skips frontend init and Discord bot startup), drive it with `httpx.AsyncClient` over `ASGITransport`, and rely on the function-scoped `db` fixture for a fresh in-memory SQLite database per test. See [development.md](../development.md) for running the suite.
6. **Docs** — nothing to regenerate. FastAPI rebuilds the OpenAPI schema from route signatures, so the endpoint appears at `/api/docs` and `/api/redoc` immediately.
