# REST API coverage for the online-tournament features

> **Status: implemented.** The online-tournament features (presets, racetime
> bots/rooms, SpeedGaming ETL, Discord Events sync, service health, async
> qualifiers + live races, seed rolling) now have full read + write REST parity
> via ten new routers under [`api/routers/`](../../api/) — see the live catalogue
> in [reference/rest-api.md](../reference/rest-api.md#online-tournament-features)
> and the always-current Swagger UI at `/api/docs`. This doc is retained as the
> design record: the endpoint tables, the two `require_super_admin` dependencies,
> the deliberate exclusions, and the test plan below describe what was built and
> why. The design was implemented essentially as written; a handful of field/method
> names were reconciled to the actual service/model code during implementation.

## Why this is a gap

The existing REST API (see [reference/rest-api.md](../reference/rest-api.md)) is a
fairly full CRUD + action surface, split by convention into a read router
(`api/routers/<resource>.py`, GET-only, `Depends(require_api_actor)`) paired with a
writes router (`api/routers/<resource>_actions.py`, `require_write_actor`). A grep
of `api/` for every new-feature keyword (`preset`, `racetime`, `race_room`,
`speedgaming`, `service_health`, `async_qualifier`, `qualifier`, `leaderboard`,
`scheduled_event`, `seedgen`) returns **zero** matches. So an API consumer can drive
matches and tournaments but cannot, e.g., read a qualifier leaderboard, list
presets, roll seeds, or check service health — even though the service layer for
all of it exists and already enforces the same authorization the web UI uses.

Exposing these is low-risk because the **service layer is authoritative**: handlers
authenticate, pass the token's user as `actor`, and let the service's
`AuthService.ensure(...)` / `ValueError` bubble up through `ServiceErrorRoute`
(`PermissionError`→403, `ValueError`→400). The REST layer adds no business logic.

## Conventions any implementation must follow

- **Coarse HTTP dep, authoritative service.** For tenant-role-gated resources
  (presets, sync, qualifiers) the service allows roles *beyond* STAFF
  (`PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN`). Use `require_api_actor` /
  `require_write_actor` at the HTTP layer (**not** `require_staff`, which is
  tenant-STAFF-only and would wrongly 403 those roles) and let the service gate.
- **Two new deps needed** for global/platform resources (RacetimeBot, ServiceHealth
  board): `require_super_admin` and `require_super_admin_write` in
  [`api/dependencies.py`](../../api/dependencies.py) (mirror `require_staff` /
  `require_staff_write` but call `AuthService.is_super_admin`). `is_super_admin` is
  **global** (`UserRole` with `tenant=None`); `is_staff`/`can_*` are **tenant-scoped**
  — this is why a global model like `RacetimeBot` cannot be gated with
  `require_staff`.
- **Where the service does *not* gate**, the HTTP dep is the only authz — this is
  the case for `ServiceHealthService` (snapshot/tenant_subset/refresh),
  `SeedGenerationService.generate_seed`, and the RaceRoom "system-path" transitions
  (`cancel_room`, `set_status`, `mark_in_progress`). Those handlers must add an
  explicit `AuthService.ensure(...)` gate.
- **404 convention.** Services raise `ValueError("… not found")` → 400. To honor the
  documented 404, add a `_load_<x>_or_404` helper doing
  `Model.get_or_none(id=…, tenant_id=require_tenant_id())` (global models omit the
  tenant filter) and delegate to the service after.
- **Tenancy from the token, not the URL.** `/api` is excluded from
  `TenantMiddleware`; the bearer token sets the tenant context. Routers must never
  import `application.repositories`; every router sets
  `route_class=ServiceErrorRoute`.
- **Schemas** in `api/schemas/<resource>.py`, `ConfigDict(from_attributes=True)`,
  naming `<Resource>Response` / `<Resource>CreateRequest` / `<Resource>UpdateRequest`;
  PATCH uses `body.model_dump(exclude_unset=True)`. All the new services are already
  exported from `application.services`.
- **Never serialize secrets.** `RacetimeBot.client_secret` must not appear in any
  response — build responses from the existing `RacetimeBotService.serialize(bot)`
  projection, not `from_attributes` on the raw ORM.

## Proposed endpoints

Legend for the auth dep: **A** `require_api_actor` · **W** `require_write_actor` ·
**SA** `require_super_admin` · **SAW** `require_super_admin_write` · **ST**
`require_staff`. Read router + `_actions.py` writes router per resource unless noted
"combined".

### Presets — `/presets` (service gate `can_manage_presets`)
| Method + path | Dep | Service |
|---|---|---|
| GET `/presets` (opt `?randomizer=`) | A | `list_presets(actor)` / `list_by_randomizer(r)` |
| GET `/presets/selectable` | A | `list_selectable()` |
| GET `/presets/{id}` | A | `get_preset(actor, id)` |
| POST `/presets` | W | `create_preset(actor, …)` |
| PATCH `/presets/{id}` | W | `update_preset(actor, id, …)` |
| DELETE `/presets/{id}` | W | `delete_preset(actor, id)` |
| POST `/presets/import-builtins` | W | `import_builtins(actor)` |

### Race room profiles — `/race-room-profiles` (gate `can_manage_sync`)
GET `` / `/selectable` / `/{id}` (A); POST / PATCH `/{id}` / DELETE `/{id}` (W) →
`list_profiles` / `list_selectable` / `get_profile` / `create_profile` /
`update_profile` / `delete_profile`.

### Racetime bots — `/racetime-bots` **(global / super-admin, combined)**
Lookups are **not** tenant-scoped (`RacetimeBot` has no tenant FK). Responses built
from `RacetimeBotService.serialize(bot)` (never `client_secret`).
| Method + path | Dep | Service |
|---|---|---|
| GET `` · `/active` · `/{id}` | SA | `list_bots` / `list_active_bots` / `get_bot` |
| POST `` · PATCH `/{id}` · DELETE `/{id}` | SAW | `create_bot` / `update_bot` / `delete_bot` |
| GET `/{id}/grants` | SA | `list_grants` |
| POST `/{id}/grants` `{tenant_id}` · DELETE `/{id}/grants/{tenant_id}` | SAW | `grant_tenant` / `revoke_tenant` |

### Race rooms — `/race-rooms`
| Method + path | Dep | Service / note |
|---|---|---|
| GET `/open` | A/ST | `RacetimeRoomService.list_open_rooms()` — verify repo tenant-scoping; if unscoped, gate ST |
| GET `/by-match/{match_id}` | A | `get_for_match(match)` (404 if none) |
| POST `` `{match_id}` | W | `RaceRoomService.manual_create_room(actor, match_id)` |
| POST `/{id}/cancel` `{reason?}` | W | handler `ensure(can_manage_sync)`; `cancel_room(room, actor=, reason=)` |
| PATCH `/{id}/status` `{status}` | W | handler `ensure(can_manage_sync)`; `set_status(room, status)` |

**Excluded (inbound/system internals):** `get_by_slug` (webhook reverse-lookup,
deliberately global/unscoped — exposing enables cross-tenant slug probing),
`record_finish` and `RaceRoomEventHandler.handle_event`/`_route_qualifier` (websocket
event dispatch that maps race results → players), `create_room_for_match` (internal
auto-toggle).

### SpeedGaming — `/speedgaming` (gate `can_manage_sync`)
GET `/links`, GET `/links/{id}/episodes` (A); POST `/links`, PATCH `/links/{id}`,
DELETE `/links/{id}`, POST `/links/{id}/sync` (W). `sync_now` returns a `SyncResult`
dataclass → serialize via `.as_dict()`. Episode responses omit the large `payload`
blob.

### Discord events — `/discord-events` (gate `can_manage_sync`)
GET `/tournaments`, GET `/events` (A); PATCH `/tournaments/{id}` (settings),
POST `/reconcile` (W). `reconcile_now` returns a `ReconcileResult` dataclass →
`.as_dict()`. **Excluded:** `get_tenant()` and reconciler internals.

### Service health — `/service-health` **(combined; HTTP dep is the authz)**
| Method + path | Dep | Service |
|---|---|---|
| GET `` (tenant subset) | ST | `tenant_subset(require_tenant_id())` |
| GET `/board` (full snapshot) | SA | `snapshot()` |
| POST `/refresh` | SAW | `refresh(alert=False)` — never DMs on an API call |
`ProbeResult` is a frozen dataclass with `.as_dict()` (status already `.value`,
`checked_at` an isoformat string). `snapshot()`/`tenant_subset()` read a
process-global cache and may be `[]` before the first refresh.

### Async qualifiers — `/async-qualifiers` (mixed auth)
Admin reads/writes gate `can_admin_qualifier`; player methods take the resolved
actor and enforce ownership; public methods (`/open`, `/{id}/public`) are ungated by
design; the leaderboard is hidden while the window is open for non-admins.
- **Reads (A):** GET `` · `/{id}` · `/{id}/admins` · `/{id}/pools` ·
  `/{id}/review-queue` · `/runs/{run_id}/notes` · `/open` · `/{id}/public` ·
  `/{id}/pools/available` · `/{id}/me/runs` · `/{id}/me/active-run` ·
  `/{id}/leaderboard`.
- **Writes (W):** qualifier `POST`/`PATCH /{id}`/`DELETE /{id}`; admins
  `POST`/`DELETE /{id}/admins/{user_id}`; pools `POST /{id}/pools`,
  `PATCH`/`DELETE /pools/{pool_id}`; permalinks `POST /pools/{pool_id}/permalinks`
  (+ `/bulk`, `/roll`), `PATCH`/`DELETE /permalinks/{permalink_id}`; player run
  lifecycle `POST /{id}/runs` (start), `/runs/{run_id}/submit|forfeit|reattempt`;
  review `/runs/{run_id}/claim|release|review`.
- **Excluded:** `recompute_par_and_scores` (internal scoring maintenance, auto-run
  after review/reattempt) and `is_results_public` (predicate, surfaced via
  leaderboard access).
- **Serialization note:** `LeaderboardEntry` is a dataclass; with
  `from_attributes=True`, `response_model=List[LeaderboardEntryResponse]` maps it
  directly.

### Async qualifier live races — `/async-qualifiers/live-races` (gate `can_admin_qualifier`)
GET `` `?qualifier_id=` · `/{id}` · `/{id}/runs` (A); POST `` (create),
POST `/{id}/open-room`, DELETE `/{id}` (cancel) (W). **Excluded:** `mark_in_progress`
and `record_finish` (inbound racetime capture that maps entrants → runs).

### Seeds — `/seeds` **(combined; `generate_seed` ungated → HTTP dep is authz)**
GET `/randomizers` (A) → `AVAILABLE_RANDOMIZERS` + the `supports_triforce_texts`
map; POST `/seeds` `{randomizer, preset_id?}` (W) → `generate_seed` (loads the
tenant-scoped preset when `preset_id` is given; unsupported randomizer → 400; honors
`MOCK_SEEDGEN`).

## Response/serialization cheatsheet

Most responses are ORM objects via `from_attributes`. The exceptions return
**dicts/dataclasses** and need an explicit response model built from a projection:
`ServiceHealth` `ProbeResult.as_dict()`, SpeedGaming `SyncResult.as_dict()`, Discord
`ReconcileResult.as_dict()`, RacetimeBot `RacetimeBotService.serialize(bot)`
(secret-free), and the qualifier `LeaderboardEntry` dataclass (maps under
`from_attributes`). These dataclass response models are the likeliest place an
OpenAPI-schema build error would surface.

## Test plan

One `tests/test_api_<resource>.py` per group, using
[`tests/api_helpers.py`](../../tests/api_helpers.py) (`build_api_app`,
`create_user_token`, `client_for`) over the in-memory SQLite `db` fixture. Baseline
per file: (1) happy-path read with a correctly-roled token; (2) unauthenticated →
401; (3) read-only token → 403 on a representative write; (4) **cross-tenant
isolation** — create the row inside `with tenant_scope(tenant_a.id)`, mint the token
inside `with tenant_scope(tenant_b.id)`, assert 404 on `/{id}` and the list omits A's
row; (5) a role-less token → 403 on a gated read/write.

**Tenancy gotcha:** `create_user_token(roles=[…])` stamps each `UserRole` with the
currently scoped tenant, so tenant-scoped roles must be created inside
`with tenant_scope(tenant.id)` (as `tests/test_api_tenant_isolation.py` does). For
`SUPER_ADMIN` (RacetimeBot / ServiceHealth board) the role row must be stored with
`tenant=None` — verify the helper yields a NULL-tenant row (or extend it).

Resource extras worth explicit tests: RacetimeBot never leaks `client_secret` and
403s any non-super-admin; ServiceHealth tenant-staff reads the subset but the board
needs super-admin, and `POST /refresh` uses `alert=False` (no DM side effects);
async-qualifier player can start→submit their own run but `review_run` on their own
run → 400, `/review-queue` for a non-admin → 403, and the leaderboard is hidden
while open; seeds return the mock URL under `MOCK_SEEDGEN` and 400 on an unsupported
randomizer.

## Suggested delivery

One commit per resource group (each lands its router pair + schema + tests green,
registering its own routers in [`api/__init__.py`](../../api/__init__.py)), preceded
by the `require_super_admin` dependencies commit. The async-qualifier group is the
largest and may split management vs. player/review. Verify with
`poetry run pytest tests/test_api_*.py`, `ruff check api/`, and a live `/api/docs`
smoke (confirm every new tag group renders, the dataclass response models build, and
a sub-STAFF role token — `PRESET_MANAGER`/`SYNC_ADMIN`/`QUALIFIER_ADMIN` — returns
200 rather than 403).

## Related

- [reference/rest-api.md](../reference/rest-api.md) — the current API surface.
- [gap-analysis.md](gap-analysis.md) — other pre-implementation gaps.
- Service layer: `application/services/` (all listed services are exported from its
  `__init__.py`).
