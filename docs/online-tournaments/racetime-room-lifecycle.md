# Feature 5: Racetime race-room lifecycle

> Part of the [Online Tournaments plan](README.md) (proposed, not implemented).
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).

**Wizzrobe owns the full lifecycle of a racetime.gg race room** for a scheduled
match — from creation through the race finishing or being cancelled — rather than
delegating any of it to SahasrahBot or to staff clicking through racetime.gg by
hand. This is the piece that makes an online scheduled bracket actually run, and it
is the backbone of the decided-first focus (scheduled restreamed brackets,
ALTTPR-first).

Source: `alttprbot/services/race_room_service`, the `racetime-bot` handler
framework.

## The `racetimebot/` subsystem (peer of `discordbot/`)

A new top-level package, structurally the sibling of `discordbot/`, following the
established "bot handlers are a presentation layer" rule (they call services, never
import repositories):

- **Shared, DB-managed bots, authorized to tenants by SUPER_ADMIN (decided).**
  Racetime bots/categories are first-class **`RacetimeBot` rows** (client-id/secret
  per game category) — the mature form of "one bot, many guilds," validated by
  [sahabot2](https://github.com/tcprescott/sahabot2). `RacetimeBot` is **global
  infrastructure** (not tenant-scoped, like the Discord bot token / VAPID keys),
  managed on `/platform`. A tenant cannot use a category until a SUPER_ADMIN grants
  it via a **`RacetimeBotTenant`** junction. That junction is **many-to-many**: a
  tenant may be authorized for **multiple categories** (e.g. alttpr *and* smz3 *and*
  sm — a community running several games), and a category bot serves many tenants.
  Then a tenant's `SYNC_ADMIN` selects, **per tournament**, the bot for that
  tournament's game via the `Tournament → RacetimeBot` FK — constrained to the
  categories the tenant is authorized for and matching the tournament's randomizer.
  A room records the bot managing it. The `client_secret` never surfaces to tenant
  admins (Staff/super-admin only, like `ChallongeConnection` tokens), and one
  racetime app registration serves every tenant. Not per-tenant credentials, not a
  single hard-coded connection. The `RacetimeBotTenant` grant follows the
  **verified-linking precedent** `DiscordLinkService` set on `main` (PR #85/#86): a
  STAFF/super-admin gate plus a server-verified step, never trusting a
  client-supplied id — the racetime identity OAuth applies the same discipline.
- **A connection per category, a handler per active room**, spawned via the
  `racetime-bot` framework. Each handler is a long-lived task that reacts to room
  state transitions and calls `RaceRoomService`. Gated by `RACETIME_*` env +
  `RacetimeBot` rows and a **`MOCK_RACETIME`** flag — a *scripted event-emitting
  fake* that drives the full lifecycle (not a no-op skip), refused under
  `ENVIRONMENT=production` like the other mock flags since it can fabricate finishes.
- **Autonomous actor (decided).** Handlers and the auto-open worker act as the
  reserved **system `User`**, so the state transitions and result capture they drive
  carry a valid `actor` for audit/events without tripping a permission gate. Tenant
  comes from `tenant_scope`.
- **Tenant routing (1:1, unlike Discord).** A room belongs to exactly **one**
  tenant — the one whose match created it — so routing is unambiguous: resolve the
  `RacetimeRoom`→`Match`→tenant mapping on every inbound event (an
  explicitly-unscoped lookup on the unique `slug`) and run the handler inside
  `tenant_scope(tenant_id)`. This is *simpler* than the Discord bot, which after PR
  #85/#86 fans a single guild's events out over **all** tenants sharing that guild;
  a racetime room never fans out. Same websocket-trap caveat applies
  ([multitenancy.md](../features/multitenancy.md)): handlers run outside any HTTP
  request, so the tenant is resolved from the mapping, never assumed.

## Bot health monitoring (decided)

Each `RacetimeBot` is a long-lived websocket connection that can silently fail
(expired/bad credentials, racetime.gg downtime, a dropped socket), so its health is
tracked as first-class state — the sahabot2 model, adopted directly:

- **Health fields on `RacetimeBot`**: a `status` enum
  (`unknown / connected / auth_failed / connection_error / disconnected`),
  `status_message`, `last_connected_at`, and `last_checked_at`.
- **Lifecycle-driven updates**, from the connection loop:
  - Successful connect → `connected`, stamp `last_connected_at`.
  - **Auth error (401 / unauthorized) → `auth_failed`, and stop retrying** — a
    credential problem needs a human, so retrying is pointless and noisy; this state
    must alert loudly.
  - Transient error → `connection_error`, retry with **exponential backoff capped at
    ~5 min**.
  - Manual stop → `disconnected`.
- **Liveness heartbeat**: `last_checked_at` is refreshed on a cadence so a task that
  died *without* raising (a wedged socket) is detectable as staleness, not just via
  the status column.
- **Every transition publishes an event** (`racetime_bot.connected` /
  `.auth_failed` / `.connection_error` / `.disconnected`) so it flows to Sentry, the
  [external-service health page](README.md#platform-external-service-health), and any
  webhook/DM alerting — a bot going `auth_failed` mid-event should page someone.
- **Manual controls** on `/platform` (SUPER_ADMIN): a per-bot restart/reconnect
  action and the status board (mirrors sahabot2's `restart_bot`).
- **Interaction with auto-open**: the auto-open worker checks the category bot's
  health first — if it isn't `connected`, it skips the match with a staff-visible
  error rather than wedging, and (per the reliability risk) allows manual retry once
  the bot recovers.

## Scheduled auto-creation (decided)

Rooms are **created on schedule, not on demand** — but **auto-open is opt-in per
tournament** (decided): a background worker (under `tenant_scope`, same pattern as
the SG sync and Discord-events workers) opens a racetime room for eligible upcoming
matches only in tournaments that have explicitly enabled auto-open and set a lead
time before `Match.scheduled_at` (e.g. "open the room 30 minutes before start").
Nothing opens unexpectedly; a tournament with auto-open off relies on manual
creation.

**Eligibility (decided): every entrant must have a linked racetime identity.** A
match auto-opens only when all its players have linked racetime (so finishes
attribute cleanly on capture); a match with any unlinked entrant is skipped by the
worker and left to manual creation, where staff accept the raw-handle-reconcile
path knowingly. Lead time, the auto-open toggle, room visibility, and the goal are
per-tournament config via the
[user-definable](README.md#design-principle-user-definable-tournament-logic)
surface — no per-tournament code. Staff can always trigger creation manually for a
one-off regardless of the toggle.

## Lifecycle state machine

`RaceRoomService` (in `application/services/`) is the business layer the handlers
and the auto-open worker both call. The room's lifecycle, mapped onto the `Match`:

| Room event | Wizzrobe action |
|---|---|
| **Create** (worker, on schedule) | open the racetime room from tournament config; store its slug + state on the `Match`; invite/announce to enrolled players |
| **Open → entrants join** | track readiness; surface room status on the match's web/admin views |
| **Attach seed** | roll (or use the already-rolled) seed via `SeedGenerationService` + the tournament's [`Preset`](seed-rolling.md), and post the permalink into the room at the configured moment (e.g. at `.setup`/countdown) |
| **In-progress** (race starts) | stamp `Match.started_at`; templated race-room messages via config |
| **Finish** | capture each entrant's finish time/place, map racetime users → `User` (via the racetime identity link below; unlinked → raw handle for staff reconcile), record results, stamp `Match.finished_at`, hand off to result reporting (Challonge) |
| **Cancel / abort / timeout** | mark the room closed, leave the `Match` re-openable, audit the reason |

Every transition writes an `AuditLog` and publishes an `EventType`
(`race_room.created`, `.opened`, `.started`, `.finished`, `.cancelled`) so
webhooks, telemetry, and UI refresh react through the existing bus.

## racetime identity linking (prerequisite)

Result capture only attributes to a `User` if that user has linked their
racetime.gg identity. This adds the third verified-identity link on the global
`User`, mirroring the existing Twitch/Challonge pattern exactly:

| Field | Mirrors |
|---|---|
| `racetime_user_id` (unique, nullable) | `twitch_user_id` |
| `racetime_username` (cached) | `twitch_username` |
| `racetime_linked_at` | `twitch_linked_at` |

Captured via one-time racetime OAuth (identity only, token discarded), a new
`pages/racetime_oauth.py` mirroring `pages/challonge_oauth.py`. Unlinked racers
don't block a finish — the raw racetime handle is stored on the result for staff to
reconcile later (same graceful-degradation rule as SG player matching). The link is
also what gates [auto-open eligibility](#scheduled-auto-creation-decided) and what
[Async Qualifier live races](async-qualifiers.md) reuse.

## Data model

- **`RacetimeRoom`** (its own model, decided — from sahabot2, not a slug column on
  `Match`): unique `slug`, `category`, `room_name`, `status`
  (open/pending/in_progress/finished/cancelled), `OneToOne → Match` (SET_NULL),
  `FK → RacetimeBot`, timestamps. Decouples room lifecycle from `Match`, gives the
  unique-slug reverse lookup for tenant routing, and prevents orphaned slugs.
- **`RacetimeBot`** (**global**, not tenant-scoped): per-category client-id/secret,
  friendly name, and health fields (`status` enum, `status_message`,
  `last_connected_at`, `last_checked_at`); managed by SUPER_ADMIN on `/platform`.
  New enum: bot `status`. New `racetime_bot.*` events.
- **`RacetimeBotTenant`** junction (`bot` × `tenant`, `is_active`, unique together):
  the SUPER_ADMIN authorization grant — **many-to-many**, so a tenant can be
  authorized for several categories and a category serves many tenants. `Tournament`
  selects one bot via FK, constrained to the tenant's authorized (and
  game-matching) categories.
- **`User.racetime_user_id` / `_username` / `_linked_at`** (global, unique, OAuth
  identity-only).
- **`MatchPlayers`** reuses the existing `finish_rank` for place and gains one
  finish-elapsed-time column; unlinked finishes fall back to the placeholder-user /
  raw-handle path ([Feature 4](speedgaming-etl.md)).
- Per-tournament config columns: `racetime_auto_create_rooms`,
  `room_open_minutes_before`, `require_racetime_link`, `racetime_default_goal`, +
  a `RaceRoomProfile` FK (reusable room settings) — the hybrid typed-columns side.
- New enum: race-room `status` (cached from racetime). `race_room.*` audit/event members.

## Roadmap

- **Phase 2** — racetime identity linking (`User.racetime_*` + OAuth page). Small;
  also unblocks Async Qualifier live races.
- **Phase 3** — racetime bot skeleton + `MOCK_RACETIME`: lifespan-managed
  connection, mockable boundary, a handler that connects and tracks room state.
- **Phase 4** — room lifecycle for scheduled matches: `RaceRoomService`, the
  scheduled auto-open worker, seed attach from `Preset`, full lifecycle → result
  capture → Challonge reporting. **Completes scheduled online brackets.**

(Full ordering across all features: [roadmap](README.md#phased-roadmap).)

## Feature-specific risks

- **Tenant routing for inbound race events.** racetime handlers run entirely
  outside any HTTP request (the websocket trap), so a room's tenant must be
  resolved from the stored room→tenant mapping on **every** inbound event and
  wrapped in `tenant_scope` — never inferred. A forgotten scope surfaces loudly via
  `require_tenant_id()` raising; keep that safety net rather than defaulting a
  tenant.
- **Scheduled room creation reliability.** The auto-open worker must be idempotent
  (exactly one room per match even across restarts/retries — guard on the presence
  of a `RacetimeRoom` for the match / its unique `slug`), tolerate racetime API
  failures without wedging the match (retry with backoff, surface a staff-visible
  error, allow manual creation as fallback), and re-attach live rooms on bot
  reconnect/redeploy by re-reading open `RacetimeRoom` rows. Getting "open 30 min
  before" wrong in either direction — no room, or a duplicate room — is a race-day
  incident.
- **Reschedule with an open room (decided): keep the room, update time only.** On
  an upstream reschedule after a room opened, update `scheduled_at` + the linked
  Discord event but **leave the open room as-is** — staff manually cancel/recreate
  if the new time warrants it. The auto-open worker never auto-disrupts an existing
  room. (Note the F4 interaction: `scheduled_at` is ETL-owned on SG-sourced matches,
  so the *SG sync* is what moves the time; the room is untouched either way.)

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks — the
**single-worker load + second persistent websocket** risk is driven mostly by this
feature (per-room error isolation, reconnect/resume, bounded concurrency).
