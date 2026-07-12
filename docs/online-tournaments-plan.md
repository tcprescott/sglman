# Online Tournaments Plan (proposal)

> Status: **proposed, not implemented.** This is a design/implementation plan for
> adapting SGLMan — today an *on-site* tournament manager — to also run **online
> tournaments**, porting the relevant functionality from
> [SahasrahBot](https://github.com/tcprescott/sahasrahbot). No code in this plan
> has shipped. When work begins, track progress in
> [current-state.md](current-state.md) and split each phase into its own PR.
>
> _Drafted 2026-07-12 against the post-multitenancy codebase (38 models; Challonge
> + Twitch identity linking, seed generation, event bus, webhooks, and logical
> multitenancy all present)._

## Context

SGLMan runs **SpeedGaming Live**: an *on-site* event where players are physically
present, staff schedule matches onto stream stages, crew (commentators/trackers)
sign up per match, and a seed is rolled per match from the admin schedule. The
whole model assumes staff-driven scheduling and co-located play.

**Online tournaments invert several of those assumptions:**

| On-site (today) | Online (target) |
|---|---|
| Players are co-located; staff seat them at stations | Players race remotely on their own machines |
| Staff schedule every match onto a stage | Players self-schedule; some formats have no fixed schedule at all |
| Seed rolled by staff, DM'd to players | Seed distributed **automatically at race start** by a race-room bot |
| Result entered by staff post-match | Result **captured automatically** when the race finishes |
| One head-to-head match at a scheduled time | Also **async qualifiers**: play once within a window, submit a time, ranked leaderboard |
| Stream stage = physical station | "Stage" = a restream channel; most races are *not* restreamed |

The connective tissue for online play is **[racetime.gg](https://racetime.gg)** —
the race-room platform the ALTTPR/SMZ3/OoTR communities already use. A race room
is a live, stateful object (open → pending → in-progress → finished) that a bot
joins over a websocket, seeds at the countdown, and reads finish times from.
SahasrahBot is exactly this bot, plus the tournament/async/scheduling machinery
layered on top. **This plan ports that machinery into SGLMan's three-layer
architecture** rather than running SahasrahBot as a separate service.

### Why this is a good fit

- **SahasrahBot was refactored to SGLMan's exact architecture** —
  `alttprbot/{models,repositories,services,presentation}`. Its service modules map
  almost 1:1 onto `application/services/`, so ports are translations, not rewrites.
- **The identity-linking pattern already exists.** `User` carries verified
  `challonge_*` and `twitch_*` links captured via one-time OAuth
  ([data-model.md](reference/data-model.md)). racetime.gg identity is a third
  instance of the same pattern.
- **Seed generation is already partially ported.**
  `SeedGenerationService` rolls `alttpr`/`ootr`/`smmap`/`ff1r`/`z1r`
  ([seed-generation.md](reference/seed-generation.md)) — the exact seed backends a
  race room needs. The gap is *preset selection* (see below), not seed rolling.
- **Challonge bracket mirroring exists.** Online brackets need result
  *reporting back* to Challonge; the read/mirror half is already built.
- **The bot-as-peer-of-web-UI pattern exists.** A racetime.gg bot is a second
  persistent connection alongside the Discord bot, and its handlers call the same
  service layer — identical to how `discordbot/` handlers work today.

## Scope decisions (proposed — confirm before building)

1. **racetime.gg is the online race substrate.** We integrate against it rather
   than building a race timer. A category-scoped racetime **bot** account rolls
   and monitors rooms; individual **players link their racetime identity** by
   OAuth (mirrors Twitch linking).
2. **One racetime bot connection per process**, started in the FastAPI lifespan
   alongside the Discord bot, subject to the same **single-uvicorn-worker**
   constraint ([architecture.md](architecture.md)). See
   [The single-worker constraint](#risk-the-single-worker-constraint) — this is
   the sharpest architectural risk.
3. **Extend the existing `Match` model for scheduled online races; add a new
   `AsyncTournament` subsystem for async qualifiers.** Scheduled head-to-head
   online matches are the current `Match` plus a race room; async qualifiers are a
   genuinely new paradigm (no `Match`, no schedule) and get their own models.
4. **Multitenant from day one.** Everything new is tenant-scoped exactly like the
   rest of the app ([multitenancy.md](features/multitenancy.md)): a `tenant` FK,
   scoped repositories, per-tenant racetime category config. A racetime room is
   routed back to its tenant the same way a Discord guild is.
5. **Reuse, don't fork, the crew/restream layer.** Online restreams reuse
   `StreamRoom`, `Commentator`, `Tracker`, and the crew signup/ack flow. "Station"
   assignment is simply unused for non-restreamed races.
6. **Presets become first-class.** Port SahasrahBot's preset system so a
   tournament/match/async pool can name a preset (settings file) instead of the
   current hard-coded-path-per-randomizer scheme.

---

## SahasrahBot inventory → port mapping

From `alttprbot/services/` (the authoritative subsystem list). Each row is
classified **Port** (bring it in), **Have** (already in SGLMan), **Adapt** (port
but reshape to SGLMan's models), or **Skip** (out of scope for tournament running).

| SahasrahBot service | Disposition | SGLMan home |
|---|---|---|
| `race_room_service` | **Port** | new `racetimebot/` + `RaceRoomService` — create/monitor racetime rooms |
| `async_tournament_service` and friends (`_live_race`, `_permissions`, `_scoring`) | **Adapt** | new `AsyncTournament*` models + `AsyncTournamentService` |
| `tournament_scheduling_service` | **Adapt** | fold into `MatchScheduleService`; add self-service scheduling |
| `tournament_results_service` | **Adapt** | new `RaceResultService`; report to Challonge |
| `tournament_games_service` | **Adapt** | multi-game matches (best-of-N) on `Match` |
| `preset_service` | **Port** | new `PresetService` over `presets/` (see [Presets](#presets)) |
| `seedgen/` | **Have** (partial) | `SeedGenerationService` — extend with preset selection |
| `racer_verification_service`, `verified_racer_service`, `nick_verification_service` | **Adapt** | racetime identity linking on `User` (OAuth, like Twitch) |
| `spoiler_race_service` | **Port** (later) | spoiler-log races — a race-room variant |
| `daily_service` | **Skip** (later) | recurring community dailies — not tournament-critical |
| `ranked_choice_service` | **Port** (later) | settings voting for finals |
| `triforce_text_service` | **Have** | already ported ([triforce-texts.md](features/triforce-texts.md)) |
| `audit_service`, `audit_messages_service` | **Have** | `AuditService` |
| `user_service`, `authorization/`, `guild_config_service` | **Have** | `UserService`, `AuthService`, multitenancy `config` |
| `discord_server_service`, `reaction_role_service`, `voice_role_service`, `holy_image_service`, `konot_service`, `inquiry_message_config_service`, `_notify` | **Skip** | Discord-community features unrelated to running tournaments |

**Takeaway:** the *tournament-running* core reduces to four new things —
**racetime bot + room service**, **async tournaments**, **presets**, and
**racetime identity linking** — plus adapting scheduling/results to close the loop.
Everything else is either already here or out of scope.

---

## Architecture additions

### `racetimebot/` — the racetime.gg bot (peer of `discordbot/`)

A new top-level package, structurally the sibling of `discordbot/`:

- **One persistent connection** to racetime.gg for the bot account, started from
  `main.py`'s lifespan (`init_racetime_bot()`), gated by `RACETIME_*` env vars and
  a **`MOCK_RACETIME`** flag mirroring `MOCK_DISCORD` so the app is fully
  developable with no racetime credentials. Skipped entirely when unset (logs a
  warning and continues — like the Discord token today).
- **A handler per race room.** SahasrahBot uses the `racetime-bot` framework
  (websocket per category, a `RaceHandler` spawned per room). Each handler is a
  long-lived task that reacts to room state transitions and **calls the service
  layer** — the same "bot handlers are presentation" rule the architecture hook
  enforces on `discordbot/`. Handlers must **not** import repositories.
- **Tenant routing.** A room is created by a tenant's tournament; its handler runs
  inside `tenant_scope(tenant_id)` (from `application.tenant_context`) so every
  service call it makes is correctly scoped — exactly the discipline the Discord
  bot loop already follows for guild routing.

`RaceRoomService` (in `application/services/`) is the business layer the handlers
and the web UI both call: create a room for a match, attach the seed, record the
opening/start/finish, and hand off to `RaceResultService`.

### racetime.gg identity linking (third instance of an existing pattern)

Add to the global `User` (identity is global, never tenant-scoped):

| Field | Mirrors |
|---|---|
| `racetime_user_id` (unique, nullable) | `twitch_user_id` |
| `racetime_username` (cached) | `twitch_username` |
| `racetime_linked_at` | `twitch_linked_at` |

Captured via one-time racetime OAuth (scope: read identity), token discarded after
linking — **identity only**, exactly like the Twitch link
([data-model.md](reference/data-model.md) `User`). A new
`pages/racetime_oauth.py` mirrors `pages/challonge_oauth.py`. This is the
prerequisite that lets a race room's finish times resolve to SGLMan users.

### Presets

SGLMan today hard-codes one preset path per randomizer and has **no
preset-selection mechanism** ([seed-generation.md](reference/seed-generation.md)).
Online tournaments need to choose settings per tournament/pool (SGL settings vs.
open vs. a finals ruleset). Port SahasrahBot's preset concept:

- A `PresetService` that enumerates and loads presets under `presets/<randomizer>/`
  (namespaced files already exist there).
- `Tournament` (and the new async pool) name a **preset**, not just a randomizer.
  `SeedGenerationService.generate_seed` takes an optional preset key.
- Keep the existing hard-coded presets working as the default when none is named
  (backward compatible).

### Async tournaments (new paradigm)

Async qualifiers have no `Match` and no schedule: a **pool** of permalinks, players
each play **once within a window**, submit (or auto-capture via a race room) their
time, and a **par-based score** ranks them. This needs its own models and service,
adapted from SahasrahBot's `async_tournament_*`:

- `AsyncTournament` — window, pool, scoring config; tenant-scoped, FK to `Tournament`.
- `AsyncTournamentPermalink` — a seed/permalink in the pool.
- `AsyncTournamentRace` — one player's attempt: permalink, start/end, time,
  status (reattempt/forfeit/live), review state.
- `AsyncTournamentService` / `AsyncTournamentScoringService` — draw a permalink,
  enforce one-attempt rules, compute par scores, build the leaderboard.

This is the largest new surface and is deliberately a **later phase** — scheduled
online races (below) deliver value first and exercise the racetime plumbing that
async also depends on.

### Data-model additions (summary)

All new tenant-scoped models get a `tenant` FK (NOT NULL, CASCADE), scoped repos,
and a leak test, per the multitenancy rules ([multitenancy.md](features/multitenancy.md)).

| Model / change | Purpose |
|---|---|
| `Match.racetime_room_slug` (+ opened/room state) | link a scheduled match to its racetime room |
| `RaceResult` or fields on `MatchPlayers` | captured finish time / place per player |
| `User.racetime_*` (global) | racetime identity link |
| `Tournament.preset` / async pool preset | preset selection |
| new `SystemConfiguration` / tenant `config` keys | per-tenant racetime category + bot settings |
| `AsyncTournament`, `AsyncTournamentPermalink`, `AsyncTournamentRace` | async subsystem |
| new `AuditActions` + `EventType` members | `race.room_created`, `race.started`, `race.finished`, `async.race_submitted`, … (EventType is an external contract — add, don't rename) |

---

## Phased roadmap

Each phase is independently shippable and PR-sized. Phases 1–2 are the foundation
everything else builds on.

> **Decided direction (2026-07-12):** the first target is **scheduled restreamed
> brackets** (Phase 3), **ALTTPR-only** to start. Phases 0–3 are the committed
> path; async tournaments (Phase 5) are explicitly deferred until the scheduled
> loop is proven. Keeping the initial game scope to ALTTPR means the existing
> `alttpr` seedgen + presets carry the whole end-to-end loop with no new randomizer
> backends.

**Phase 0 — racetime identity linking.** `User.racetime_*` fields + migration,
`pages/racetime_oauth.py`, profile UI to link/unlink. Small, self-contained, and a
hard prerequisite for results attribution. _No racetime bot yet — just OAuth._

**Phase 1 — racetime bot skeleton + `MOCK_RACETIME`.** Stand up `racetimebot/` as
a lifespan-managed connection with a mockable boundary, `RACETIME_*` env vars, and
a no-op handler that connects and logs room state. Proves the single-worker /
long-lived-websocket architecture in isolation before wiring business logic.

**Phase 2 — presets + seed selection.** `PresetService`, preset selection on
`Tournament`, `SeedGenerationService` preset arg. Unblocks meaningful room seeding
and is useful on its own (on-site staff can pick presets too).

**Phase 3 — scheduled online races (the core loop).** From a scheduled `Match`,
create a racetime room; the handler seeds it at the countdown, records
start/finish, and `RaceResultService` writes results and reports to Challonge.
This is the first end-to-end online match and reuses the entire existing crew /
restream / notification stack.

**Phase 4 — self-service scheduling.** Let players (not just staff) propose/confirm
match times using the existing `PlayerAvailability` + Challonge matchup data. Turns
the on-site "staff schedules everyone" model into player-driven scheduling.

**Phase 5 — async tournaments.** The `AsyncTournament*` models, permalink pools,
one-attempt enforcement, par scoring, leaderboard page, and live-race review.

**Phase 6+ — extras.** Spoiler races, settings ranked-choice voting for finals,
community dailies — port opportunistically once the core is stable.

---

## Risks & sharp edges

### Risk: the single-worker constraint

The process already **must** run one uvicorn worker because it hosts the Discord
bot, the DM queue, and NiceGUI websocket state ([architecture.md](architecture.md)).
Adding a racetime websocket + a task per live room raises the stakes: a busy
tournament could have dozens of concurrent room handlers in the same event loop
that also serves the web UI. Mitigations to design in from Phase 1: strict
non-blocking I/O (`aiohttp`/`httpx` only, already the house rule), bounded
concurrency, per-room error isolation (a crashing handler must not take down the
bot), and reconnect/resume logic. If load ever outgrows one process, the racetime
bot is the natural first thing to split into a sidecar that talks to the same DB —
but that is explicitly **not** in scope now.

### Risk: tenant routing for inbound race events

Discord already solved "one bot, many guilds" by routing on `guild_id` and wrapping
work in `tenant_scope`. racetime rooms must do the same: the room→tenant mapping has
to be established at creation and re-resolved on every inbound websocket event,
because handlers run entirely outside any HTTP request (the same
"websocket trap" the multitenancy plan calls out). Forgetting a `tenant_scope`
surfaces loudly via `require_tenant_id()` raising — that is the safety net, keep it.

### Risk: result attribution depends on identity linking

A race room reports finishes by racetime user; results only attach if that user has
linked their racetime identity (Phase 0). Need a graceful path for unlinked
racers: capture the raw racetime handle on the result and let staff reconcile later,
rather than dropping the finish.

### Risk: scope creep from SahasrahBot's Discord-community features

SahasrahBot is also a general community bot (reaction roles, voice roles, dailies,
holy images, inquiries). Those are explicitly **Skip** — porting them would balloon
scope with nothing to do with running tournaments. Hold the line at the four core
subsystems.

---

## Open questions (for the maintainer)

_Resolved 2026-07-12:_ **Games** — start **ALTTPR-only**. **Priority** —
**scheduled restreamed brackets** first (Phase 3); async qualifiers deferred.

Still open:

1. **Coexistence with SahasrahBot.** Is the intent to eventually *replace*
   SahasrahBot with SGLMan, or run both (SGLMan for SGL events, SahasrahBot for the
   broader community)? Affects whether the racetime bot needs its own category or
   shares SahasrahBot's.
2. **racetime bot account/category.** One shared SGLMan bot category, or
   per-tenant categories? (Per-tenant is cleaner isolation but more operational
   overhead; shared with `guild_id`-style routing is simpler.)

---

## Related docs

- [architecture.md](architecture.md) — process model, single-worker constraint, bot-as-peer pattern
- [reference/data-model.md](reference/data-model.md) — `User` identity links, `Match`, `Tournament`, Challonge models
- [reference/seed-generation.md](reference/seed-generation.md) — current seedgen + the preset gap
- [features/multitenancy.md](features/multitenancy.md) — tenant context, `tenant_scope`, one-bot-many-guilds routing
- [reference/discord-integration.md](reference/discord-integration.md) — the bot/handler pattern the racetime bot mirrors
- [multitenancy-plan.md](multitenancy-plan.md) — the house style this plan follows
