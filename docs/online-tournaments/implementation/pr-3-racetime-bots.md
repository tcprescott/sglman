# PR 3 — Racetime bots + authorization + room model

> Feature 5. Roadmap phase 3 (data/admin half). Models + `/platform` management +
> per-tournament selection. **No live websocket yet** — that's PR 4.

**Goal:** the data model and admin surfaces for racetime bots, their per-tenant
authorization, per-tournament selection, and the room record.

**Depends on:** PR 0. **Unblocks:** PR 4 (runtime), PR 6 (lifecycle).

## Deliverables

- **`RacetimeBot`** (**global**, not tenant-scoped — like the Discord token/VAPID
  keys): `category` (unique), `client_id`, `client_secret` (secret; never returned/
  logged), `name`, `description`, `is_active`, `handler_class`, and health fields
  (`status` `BotStatus` enum, `status_message`, `last_connected_at`,
  `last_checked_at`). Repo + service. Managed on `/platform` by SUPER_ADMIN.
- **`RacetimeBotTenant`** junction (`bot` × `tenant`, `is_active`,
  `unique_together`): the SUPER_ADMIN authorization grant. **Many-to-many** — a
  tenant may hold several categories; a category serves many tenants.
- **`RacetimeRoom`** (own model, not a slug on `Match`): `slug` (unique, indexed),
  `category`, `room_name`, `status`, `OneToOne → Match` (`SET_NULL`),
  `FK → RacetimeBot`. Include an **explicitly-unscoped** repo lookup by `slug` for
  tenant routing ([gap 4.2](../gap-analysis.md)).
- **`Tournament` racetime config columns**: `racetime_bot` FK (constrained to the
  tenant's authorized, game-matching categories), `racetime_auto_create_rooms`,
  `room_open_minutes_before`, `require_racetime_link`, `racetime_default_goal`, and
  an optional `RaceRoomProfile` FK (reusable room settings). Admin UI to set them
  (gated by `SYNC_ADMIN`).
- **`/platform` UI**: CRUD `RacetimeBot` rows; assign/unassign to tenants
  (`RacetimeBotTenant`), mirroring the Discord-bot-organizations pattern.
- Migrations + leak tests (the tenant-scoped junction and `RacetimeRoom`).

## Decisions that apply

Shared DB-managed bots, SUPER_ADMIN-authorized via junction, many categories per
tenant; `RacetimeRoom` as its own model; secrets stay platform-level.

## Reference implementations

- **sahabot2**: `models/racetime_bot.py` (`RacetimeBot` + `RacetimeBotOrganization`
  + `BotStatus`), `models/racetime_room.py`, `models/race_room_profile.py`,
  `application/services/racetime/racetime_bot_service.py` (CRUD, assign/unassign,
  `restart_bot`), `.../race_room_profile_service.py`.
- **sglman**: `pages/platform.py` (super-admin surface),
  `application/services/discord_link_service.py` (verified-authorization pattern),
  `application/services/challonge_service.py` (secret handling — never log/return).

## Acceptance criteria

- SUPER_ADMIN creates a bot and grants it to two tenants; each tenant's `SYNC_ADMIN`
  can select it on a tournament of the matching game, but not a category they aren't
  granted. `client_secret` never appears in any tenant-facing response. Verify via
  `ui-validation`.

## Out of scope

The websocket connection, health *updates*, and room creation (PR 4/6). Health
*fields* exist here but are written by PR 4.
