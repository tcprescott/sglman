# Online Tournaments Plan (proposal)

> Status: **proposed, not implemented.** This is the design/implementation plan for
> adapting SGLMan — today an *on-site* tournament manager — to also support **online
> tournaments**, forward-porting a defined set of functionality from
> [SahasrahBot](https://github.com/tcprescott/sahasrahbot). No code in this plan has
> shipped. When work begins, track progress in [current-state.md](current-state.md)
> and split each phase into its own PR.

## Decisions log

| Date | Decision |
|---|---|
| 2026-07-12 | First online focus: **scheduled restreamed brackets**; **ALTTPR-first** game scope |
| 2026-07-12 | Tournament logic is **user-definable** (declarative config, not code-per-tournament) — see [design principle](#design-principle-user-definable-tournament-logic) |
| 2026-07-12 | **SGLMan succeeds SahasrahBot** (full replacement of its tournament/racing mission, not coexistence) |
| 2026-07-13 | **Forward-port scope fixed at five features** (see [Scope](#scope-the-five-forward-ported-features)): Async Qualifiers, seed rolling, Discord Events sync, SpeedGaming ETL, racetime race-room lifecycle. Supersedes the earlier broad port map and the "parity items before cutover" framing |
| 2026-07-13 | **SGLMan owns the full racetime race-room lifecycle** (Feature 5, added after the initial four): create → open → in-progress → finished/cancelled, for scheduled matches. **Rooms are auto-created on schedule** (opened ahead of `Match.scheduled_at`), not on demand. Reverses the earlier "race-room automation out of scope" decision and resolves the corresponding open question. |
| 2026-07-13 | SahasrahBot's **Async Tournament** is renamed **Async Qualifier** in SGLMan — its workflow is completely different from a tournament's and the name collision with `Tournament` would mislead |
| 2026-07-13 | SpeedGaming schedule data comes in via an **ETL/sync process** into SGLMan's own tables — *not* SahasrahBot's approach of live-querying the SG API per interaction |
| 2026-07-13 | `AsyncQualifier` is a **standalone peer aggregate of `Tournament`**: created/administered the same way (many can run concurrently per tenant), but a **distinct state machine** entirely outside the `Match`/schedule system — no structural FK between the two |
| 2026-07-13 | **SG sync is strictly one-way** (SG → SGLMan, never back). For a `Match` created by the ETL, **the ETL-owned fields are read-only in SGLMan** — enforced at the service layer, not just convention. See [Feature 4](#4-speedgaming-schedule-etl). |
| 2026-07-13 | **Async Qualifier execution is web-first, decided (not open).** SahasrahBot's Discord-thread-driven run execution (slash command → private thread → buttons) is **dropped**, not ported, not offered as a config toggle. Drawing a permalink, timing a run, submitting time/VoD, and review all happen on SGLMan web pages; Discord is notification-only via the existing DM queue. Live races (Phase 6) still need a racetime.gg bot connection for synchronous group races, but that's separate from the core async execution loop. |

## Context

SGLMan runs **SpeedGaming Live**: an *on-site* event where players are physically
present, staff schedule matches onto stream stages, crew sign up per match, and a
seed is rolled per match from the admin schedule. Online tournaments differ:
players race remotely, seeds are distributed automatically, results are captured
rather than entered, and qualifiers are often **async** — play once within a
window, submit a time, ranked against par.

**SGLMan is the designated successor to SahasrahBot.** The end state is that
SahasrahBot's tournament/racing mission retires and SGLMan is the single platform
for both SGL's on-site events and the online community's tournaments. The
maintainer has fixed the succession scope to the five features below — SahasrahBot
functionality outside that list retires with it (or survives on a thin community
bot), rather than being reimplemented.

Two structural facts make the port natural:

- **SahasrahBot was refactored to SGLMan's exact architecture**
  (`alttprbot/{models,repositories,services,presentation}`), so ports are
  translations into existing layers, not rewrites.
- **SGLMan already has the supporting substrate**: multitenancy (each SahasrahBot
  community becomes a tenant; one Discord bot, many guilds), verified identity
  linking on the global `User` (Challonge, Twitch — racetime.gg becomes the third),
  seed generation for five randomizers, the event bus, and audit logging.

## Design principle: user-definable tournament logic

**The load-bearing difference from SahasrahBot.** There, each tournament is a
bespoke Python handler class — standing up a new tournament means a developer
writes and ships code. In SGLMan, **a community defines tournament behavior as
data, through the admin UI, with no code change and no deploy**.

The buildable shape of this is **declarative configuration selecting among
built-in strategy primitives, plus safe templated text** — *not* a scripting
engine or per-tenant plugin code (which would relocate the code-per-tournament
problem and add a security surface). Concretely:

- **Presets are DB rows a tenant admin authors in the UI** (randomizer + settings
  payload), not files in the repo. The existing `presets/` files become importable
  built-in defaults.
- **Behavior facets are strategy choices + parameters** stored in schema-validated
  config: seed source, scoring, scheduling windows, reattempt rules, messaging
  templates with `{placeholders}` (safe substitution, never `eval`).
- The engine implements a **finite, named set of strategies**; config picks and
  parameterizes them. A new *primitive* is a reviewed code change available to all
  tenants; a new *tournament or qualifier* is pure config.

Everything below is designed under this constraint.

---

## Scope: the five forward-ported features

**These are additive — they sit on top of SGLMan's existing Tournament/Match
capability, which remains the backbone for online tournaments.** Everything the
app already does — tournaments, enrollment, match scheduling and lifecycle, crew
signup/approval, stream rooms, notifications, Challonge mirroring, availability —
serves online events directly; nothing here replaces those workflows. The five
ported features fill the online-specific gaps and plug into that machinery: the
SG ETL materializes into existing `Match` rows, Discord Events sync reads the
existing schedule, presets extend the existing seed-rolling flow, the racetime
race-room lifecycle auto-creates and drives a room per scheduled `Match`, and Async
Qualifiers arrive as a **peer aggregate alongside `Tournament`** — created and
administered the same way, running a distinct machine.

| # | Feature | SahasrahBot source | SGLMan disposition |
|---|---|---|---|
| 1 | **[Async Qualifiers](#1-async-qualifiers)** (renamed from *Async Tournament*) | `models/async_tournament.py`, `services/async_tournament_*` | New tenant-scoped `AsyncQualifier*` subsystem; **web-first execution, decided** — Discord-thread run flow dropped |
| 2 | **[Seed rolling](#2-seed-rolling)** — eventually every SahasrahBot-supported randomizer | `services/seedgen/`, `models/presets.py` | Extend `SeedGenerationService`; add user-managed `Preset` model; incremental randomizer coverage |
| 3 | **[Discord Events sync](#3-discord-events-sync)** | `ScheduledEvents` model (`episode_id` ↔ `scheduled_event_id`) | Generalized auto-sync of Discord Scheduled Events from SGLMan schedule data, per tenant guild |
| 4 | **[SpeedGaming schedule ETL](#4-speedgaming-schedule-etl)** | direct SG API queries keyed on `episode_id` throughout | **New approach**: periodic ETL into SGLMan tables; SG becomes an upstream data source, not a per-interaction dependency |
| 5 | **[Racetime race-room lifecycle](#5-racetime-race-room-lifecycle)** | `services/race_room_service`, the `racetime-bot` handler framework | New `racetimebot/` subsystem (peer of `discordbot/`); **auto-creates rooms on schedule** and owns the full room lifecycle through finish/cancel, incl. seed attach + result capture |

### Explicitly not ported

- **Per-tournament handler classes** — replaced by the user-definable config
  (design principle above), not translated.
- **Spoiler races, community dailies, ranked-choice voting** — retire with
  SahasrahBot (previously misclassified here as pre-cutover parity items).
- **General Discord-community features** (reaction/voice roles, holy images,
  inquiries, `konot`) — outside the tournament/racing mission.
- **SahasrahBot's dormant `Schedule*` models** (`ScheduleEvent`,
  `ScheduleEpisode`, …) — an unfinished in-house scheduling attempt with live
  tables but no runtime usage. The SG ETL supersedes the idea; do not port the
  models.

---

## Feature 1: Async Qualifiers

**Rename:** SahasrahBot calls this *Async Tournament*. In SGLMan it is
**Async Qualifier** (`AsyncQualifier*` models, `AsyncQualifierService`) — the
workflow (self-paced runs against a permalink pool inside a window) is nothing
like a `Tournament`'s, and the old name would collide with SGLMan's existing
`Tournament` aggregate.

### A peer aggregate to `Tournament`: same creation, distinct machine

`AsyncQualifier` is a **standalone, first-class aggregate** — a sibling of
`Tournament`, not a child or a mode of one:

- **Created and administered like a tournament.** The admin surface mirrors the
  Tournaments pattern staff already know: a create/edit dialog and admin tab,
  per-qualifier admins (M2M, like `Tournament.admins`), player enrollment,
  `is_active`, and the same service/audit/event conventions. Standing one up
  feels exactly like standing up a tournament — and **any number of qualifiers
  can exist and run concurrently** per tenant, just as tournaments do.
- **Fully outside the schedule system.** Qualifier runs are self-paced within the
  window — they are never `Match` rows, never appear on the Schedule/On Air tabs,
  and don't touch stream rooms or station assignment. The qualifier gets its own
  admin tab and player-facing pages (start a run, submit, leaderboard).
- **But a distinct state machine.** It shares none of `Tournament`'s runtime
  machinery — no `Match`, no scheduled → seated → started → finished lifecycle,
  no stream-room/crew flow. Its lifecycle is its own: **window opens → players
  draw permalinks from pools → runs (in-progress → finished/forfeit) → review
  (pending → approved/rejected) → scored leaderboard → window closes.** Keeping
  the machines separate is the point of the rename: neither model grows
  conditional behavior to accommodate the other.
- **At most an informational association.** A qualifier may *name* the event it
  feeds for display purposes, but nothing structural hangs off that — no FK
  dependencies between the two machines' workflows.

### Workflow (ported semantics)

1. Staff create a qualifier: window, **permalink pools** (each pool optionally
   tied to a preset), runs-per-pool, allowed reattempts, and access rules.
2. An eligible player starts a run: the system assigns a permalink from a pool
   (spoiler-safe — revealed only at start), timestamps the start, and the player
   races self-timed.
3. The player submits finish time + VoD URL; the run enters **review**
   (pending → approved/rejected) by authorized reviewers, with review notes.
4. Scoring is **par-based** per permalink (`par_time` maintained from approved
   runs); a leaderboard ranks qualifiers.
5. **Live races**: a pool can be flagged for synchronous group runs on
   racetime.gg (SahasrahBot's `AsyncTournamentLiveRace` — `racetime_slug`,
   status). These reuse the [Feature 5](#5-racetime-race-room-lifecycle) racetime
   subsystem rather than a separate integration.

### Model mapping (SahasrahBot → SGLMan)

All new models are tenant-scoped (`tenant` FK NOT NULL, CASCADE, scoped repos,
leak test) per [multitenancy.md](features/multitenancy.md).

| SahasrahBot | SGLMan | Adaptation |
|---|---|---|
| `AsyncTournament` (guild/channel ids, owner, `allowed_reattempts`, `runs_per_pool`, `customization`) | `AsyncQualifier` | Discord channel wiring → tenant + web UI; `customization` → schema-validated config per the design principle; standalone peer of `Tournament` (no structural FK — at most an informational label for the event it feeds) |
| `AsyncTournamentPermalinkPool` (name, preset) | `AsyncQualifierPool` | `preset` becomes FK → the new `Preset` model |
| `AsyncTournamentPermalink` (url, notes, `live_race`, `par_time`) | `AsyncQualifierPermalink` | as-is |
| `AsyncTournamentRace` (status, review_status, start/end, `thread_id`, `runner_vod_url`, score) | `AsyncQualifierRun` | **`thread_id` dropped** (no Discord thread — execution is the web run page); Discord DM notifies on state changes instead; statuses kept: `pending/in_progress/finished/forfeit/disqualified`, review `pending/approved/rejected` |
| `AsyncTournamentLiveRace` (`racetime_slug`, `episode_id`, status) | `AsyncQualifierLiveRace` | `episode_id` → FK to the SG-imported episode/match where applicable |
| `AsyncTournamentReviewNotes` | `AsyncQualifierReviewNote` | as-is |
| `AsyncTournamentWhitelist` / `AsyncTournamentPermissions` | eligibility + reviewer config on `AsyncQualifier` | map onto SGLMan roles (`AuthService`) + tournament enrollment instead of parallel permission tables |
| `AsyncTournamentAuditLog` | **not ported** | SGLMan's `AuditService` + new `AuditActions`/`EventType` members (`async_qualifier.run_submitted`, `.run_reviewed`, …) |

**Workflow surface: web-first, decided.** SahasrahBot's async flow is
Discord-thread-driven (slash command → private thread → buttons). SGLMan drops
that entirely: players start runs, submit times/VoDs, and view leaderboards on
tenant web pages; Discord is notification-only (existing DM queue — "window
open," "run reviewed," etc.), not an execution surface. This isn't just a port
shortcut — a web run page can show live elapsed time, inline VoD upload/embed,
richer pool/leaderboard browsing, and a proper reviewer queue UI, none of which
Discord's thread+button model does well. `thread_id` is dropped from
`AsyncQualifierRun` (no replacement field — there is no thread). If a
lightweight Discord entry point (e.g. "start my run" deep-linking into the web
page) proves worth adding later, it goes through `discordbot/` calling the same
`AsyncQualifierService` — but it is not part of this plan.

## Feature 2: Seed rolling

SGLMan already rolls `alttpr`, `ootr`, `smmap`, `ff1r`, `z1r`
([seed-generation.md](reference/seed-generation.md)). The target: **every
randomizer SahasrahBot supports is eventually supported in SGLMan.**

- **User-managed presets first.** A tenant-scoped `Preset` model (`name`,
  `randomizer`, `settings` JSON, `description`) with CRUD on an admin tab;
  `SeedGenerationService.generate_seed` takes a preset instead of opening
  hard-coded paths. Existing `presets/` files ship as importable defaults. This is
  the foundation both Async Qualifier pools and expanded rolling sit on.
- **Incremental randomizer coverage.** Confirmed SahasrahBot randomizer families
  to bring over include ALTTPR (+ door rando + **mystery weightsets**), SM, SMZ3,
  SM VARIA/DASH, CT: Jets of Time, and the OoTR/Zelda/FF families SGLMan already
  partially covers. First implementation task of that phase: enumerate the
  authoritative list from `alttprbot/services/seedgen/` and track coverage as a
  checklist in this doc. Each backend follows the existing pattern (async HTTP,
  env-var credentials, `ValueError` on missing config).
- **Mystery support** (weighted random settings) is part of seed rolling, not a
  separate feature: a weightset is just a `Preset` variant whose payload the
  generator samples — same user-managed authoring story.

## Feature 3: Discord Events sync

SahasrahBot maps SG episodes to Discord **Scheduled Events** 1:1
(`ScheduledEvents`: `scheduled_event_id` PK, unique `episode_id`, `event_slug`).
SGLMan generalizes this into automatic sync of the tenant guild's scheduled
events from SGLMan schedule data:

- **Source of truth is SGLMan's schedule** — native `Match` rows (including
  SG-imported ones, Feature 4) and Async Qualifier windows/live races.
- A `DiscordScheduledEvent` link model (tenant-scoped): `guild_id`,
  `discord_event_id`, source type + id, `synced_at`, content hash — so sync is
  **idempotent reconciliation** (create/update/cancel to match the schedule),
  not fire-and-forget creation.
- Runs as a background worker under `tenant_scope`, through the existing
  one-bot-many-guilds Discord singleton; per-tenant opt-in and templated event
  titles/descriptions via the user-definable config.

## Feature 4: SpeedGaming schedule ETL

SahasrahBot treats speedgaming.org as a live dependency — every relevant
interaction queries the SG API and joins on `episode_id` (`TournamentGames`,
`TournamentResults`, `ScheduledEvents` all key on it; there is no local episode
store). **SGLMan inverts this: an ETL process synchronizes SG data into SGLMan's
own tables**, making SG an upstream feed rather than a runtime dependency.

- **Extract** — poll the SG schedule API per configured event slug on a cadence
  (background worker, `tenant_scope`, honoring SG rate limits).
- **Transform** — normalize episodes to SGLMan's shape: UTC datetimes, players
  matched to `User` (via Discord id where SG provides it; unmatched players kept
  as raw names for staff reconciliation — same graceful-degradation pattern as
  unlinked racetime identities), crew/channel metadata mapped to SGLMan concepts.
- **Load** — upsert into a tenant-scoped staging model `SpeedGamingEpisode`
  (unique `(tenant, sg_episode_id)`, payload snapshot + content hash, `synced_at`,
  nullable FK → `Match`), then materialize/refresh linked `Match` rows.
- **Reconciliation contract — decided, not just directional.** Sync is strictly
  **one-way, SG → SGLMan**; nothing SGLMan does ever writes back to SpeedGaming.
  For a `Match` created by the ETL, **the fields the ETL populates are read-only
  in SGLMan** — staff cannot hand-edit them; the next sync is the only thing that
  can change them. Everything SGLMan adds on top stays fully staff-editable and
  is never touched by sync:

  | ETL-owned (read-only in SGLMan) | SGLMan-owned (editable, sync never touches) |
  |---|---|
  | `scheduled_at`, enrolled players (`MatchPlayers` rows sourced from SG), `title`, tournament linkage | `generated_seed`, `stream_room`, `Commentator`/`Tracker` crew, `MatchAcknowledgment`, `MatchWatcher`, station assignments, `seated_at`/`started_at`/`finished_at`/`confirmed_at`, `comment`, Discord event links |

  **Enforcement, not just convention:** `Match` carries a source marker (its FK to
  `SpeedGamingEpisode`, non-null = SG-sourced). `MatchService.update_match` rejects
  writes to ETL-owned fields on a sourced match — an attempt raises `ValueError`
  ("this field is synced from SpeedGaming and cannot be edited"), same pattern as
  every other service-layer validation. The presentation layer disables those
  form fields for SG-sourced matches (with a "Synced from SpeedGaming" badge and
  a link to the source episode) rather than letting the click reach the service
  and bounce. A cancelled upstream episode **soft-detaches** — the `Match` row and
  everything SGLMan added survive; only the ETL-owned fields freeze at their last
  synced value and no further sync updates them.
- A `SpeedGamingEventLink` (tournament ↔ SG event slug + sync settings) configures
  which SG events feed which tenant tournaments.

Benefits over the direct-query approach: SG outages don't break race-day
operations, data is queryable/joinable locally (reports, Discord events, crew
flows all just work on `Match`), and the sync is observable (last-synced, diffs,
errors surfaced in the admin UI + audit log). The read-only boundary also means
staff can never "fix" a Match locally in a way the next sync silently reverts —
today's biggest source of ETL confusion in systems like this.

## Feature 5: Racetime race-room lifecycle

**SGLMan owns the full lifecycle of a racetime.gg race room** for a scheduled
match — from creation through the race finishing or being cancelled — rather than
delegating any of it to SahasrahBot or to staff clicking through racetime.gg by
hand. This is the piece that makes an online scheduled bracket actually run, and
it is the backbone of the decided-first focus (scheduled restreamed brackets,
ALTTPR-first).

### The `racetimebot/` subsystem (peer of `discordbot/`)

A new top-level package, structurally the sibling of `discordbot/`, following the
established "bot handlers are a presentation layer" rule (they call services, never
import repositories):

- **One persistent connection** to racetime.gg per process, started from
  `main.py`'s lifespan (`init_racetime_bot()`), gated by `RACETIME_*` env vars and
  a **`MOCK_RACETIME`** flag mirroring `MOCK_DISCORD` — so the whole app stays
  developable with no racetime credentials, and the lifecycle can be exercised end
  to end against a stub. Unset credentials log a warning and skip the bot, exactly
  like the Discord token today.
- **A handler per active room**, spawned via the `racetime-bot` framework
  (websocket per category, `RaceHandler` per room). Each handler is a long-lived
  task that reacts to room state transitions and calls `RaceRoomService`.
- **Tenant routing.** A room belongs to the tenant whose match created it; its
  handler runs inside `tenant_scope(tenant_id)` so every service call is scoped —
  the same discipline the Discord bot uses for guild routing, and the same
  websocket-trap caveat ([multitenancy.md](features/multitenancy.md)): handlers run
  outside any HTTP request, so the tenant must be resolved from the room→tenant
  mapping on every inbound event, never assumed.

### Scheduled auto-creation (decided)

Rooms are **created on schedule, not on demand.** A background worker (under
`tenant_scope`, same pattern as the SG sync and Discord-events workers) opens a
racetime room for each eligible upcoming `Match` a configurable lead time before
`Match.scheduled_at` (e.g. "open the room 30 minutes before start"). Lead time,
eligibility (which tournaments/matches auto-open), room visibility, and the goal
are per-tournament config via the [user-definable](#design-principle-user-definable-tournament-logic)
surface — no per-tournament code. Staff can also trigger creation manually for a
one-off, but the default path is automatic.

### Lifecycle state machine

`RaceRoomService` (in `application/services/`) is the business layer the handlers
and the auto-open worker both call. The room's lifecycle, mapped onto the `Match`:

| Room event | SGLMan action |
|---|---|
| **Create** (worker, on schedule) | open the racetime room from tournament config; store its slug + state on the `Match`; invite/announce to enrolled players |
| **Open → entrants join** | track readiness; surface room status on the match's web/admin views |
| **Attach seed** | roll (or use the already-rolled) seed via `SeedGenerationService` + the tournament's `Preset`, and post the permalink into the room at the configured moment (e.g. at `.setup`/countdown) |
| **In-progress** (race starts) | stamp `Match.started_at`; templated race-room messages via config |
| **Finish** | capture each entrant's finish time/place, map racetime users → `User` (via the racetime identity link below; unlinked → raw handle for staff reconcile), record results, stamp `Match.finished_at`, hand off to result reporting (Challonge) |
| **Cancel / abort / timeout** | mark the room closed, leave the `Match` re-openable, audit the reason |

Every transition writes an `AuditLog` and publishes an `EventType`
(`race_room.created`, `.opened`, `.started`, `.finished`, `.cancelled`) so
webhooks, telemetry, and UI refresh react through the existing bus.

### racetime identity linking (prerequisite)

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
don't block a finish — the raw racetime handle is stored on the result for staff
to reconcile later (same graceful-degradation rule as SG player matching).

---

## Data-model additions (summary)

| Model / change | Feature |
|---|---|
| `User.racetime_user_id` / `_username` / `_linked_at` (global, unique, OAuth identity-only) | 5 (result attribution), 1 (live races) |
| `Preset` (tenant-scoped) + `Tournament`/pool preset FKs | 2 |
| `AsyncQualifier`, `AsyncQualifierPool`, `AsyncQualifierPermalink`, `AsyncQualifierRun`, `AsyncQualifierLiveRace`, `AsyncQualifierReviewNote` | 1 |
| `DiscordScheduledEvent` (tenant-scoped link/reconciliation table) | 3 |
| `SpeedGamingEpisode`, `SpeedGamingEventLink` (tenant-scoped); `Match` gains its FK to `SpeedGamingEpisode` (source marker driving read-only enforcement) | 4 |
| `Match` gains racetime room fields (`racetime_room_slug`, room state, `room_opened_at`) + per-entrant finish time/place on `MatchPlayers` for captured results | 5 |
| New `AuditActions` + `EventType` members per subsystem (`async_qualifier.*`, `preset.*`, `discord_event.*`, `sg_sync.*`, `race_room.*`) — EventType is an external contract: add, never rename | all |

New enums: run status + review status (Feature 1), sync status (Feature 4).

## Phased roadmap

Ordering follows dependencies, not feature numbering. The **decided first focus —
scheduled restreamed brackets, ALTTPR-first — is delivered by Phases 1–4**
(presets → identity → racetime bot → room lifecycle); the SG ETL, Discord events,
and Async Qualifiers build out from there. SG ETL and Discord Events are
independent of the racetime track and can run in parallel.

1. **Phase 1 — user-managed presets + seedgen preset selection** (Feature 2
   foundation). `Preset` model, admin tab, `SeedGenerationService` preset arg,
   built-in preset import. ALTTPR-first; immediately useful on-site too.
2. **Phase 2 — racetime identity linking** (Feature 5 prerequisite). `User.racetime_*`
   + OAuth page (mirrors Twitch/Challonge linking). Small; also unblocks Async
   Qualifier live races.
3. **Phase 3 — racetime bot skeleton + `MOCK_RACETIME`** (Feature 5). Stand up
   `racetimebot/` as a lifespan-managed connection with a mockable boundary and a
   handler that connects and tracks room state — proving the single-worker /
   long-lived-websocket architecture before wiring business logic.
4. **Phase 4 — racetime room lifecycle for scheduled matches** (Feature 5, the
   core online loop). `RaceRoomService`, the scheduled auto-open worker, seed
   attach from `Preset`, full lifecycle → result capture → Challonge reporting.
   **This completes scheduled online brackets** and reuses the existing crew /
   stream-room / notification stack.
5. **Phase 5 — SpeedGaming ETL** (Feature 4). Staging model, sync worker,
   read-only reconciliation contract, admin visibility. Independent of the
   racetime track; parallelizable with Phases 1–4.
6. **Phase 6 — Discord Events sync** (Feature 3). Consumes native + SG-imported
   schedule data; reconciliation worker + config.
7. **Phase 7 — Async Qualifiers core** (Feature 1). Models, web run-execution
   pages (draw permalink, timer, submit time/VoD), reviewer queue, par scoring,
   leaderboard. Discord DM notifications only — no thread-based execution.
8. **Phase 8 — Async Qualifier live races** (Feature 1 + 5). Reuses the Phase 3–4
   racetime subsystem: a room per live race, result capture into runs.
9. **Phase 9+ — randomizer coverage expansion** (Feature 2 completion).
   Incremental backends toward full SahasrahBot parity; mystery weightsets.

## Risks & sharp edges

- **Background-worker load + a second persistent websocket in one process.** The
  single-uvicorn-worker constraint ([architecture.md](architecture.md)) now hosts
  the SG sync worker, the Discord events reconciler, the room auto-open worker, and
  the **racetime connection with a task per live room** — alongside the web UI and
  Discord bot. This is the sharpest architectural cost of Feature 5: a busy race
  day could have many concurrent room handlers in the same event loop that serves
  the UI. Disciplines: non-blocking I/O only, bounded concurrency, **per-room
  error isolation** (a crashing handler must not drop the bot or other rooms),
  reconnect/resume so a dropped websocket doesn't orphan live rooms, and
  `tenant_scope` everywhere (`require_tenant_id()` raising is the safety net). If
  load ever outgrows one process, the racetime bot is the natural first thing to
  split into a sidecar against the same DB — explicitly not now.
- **Tenant routing for inbound race events.** racetime handlers run entirely
  outside any HTTP request (the websocket trap), so a room's tenant must be
  resolved from the stored room→tenant mapping on **every** inbound event and
  wrapped in `tenant_scope` — never inferred. A forgotten scope surfaces loudly via
  `require_tenant_id()` raising; keep that safety net rather than defaulting a
  tenant.
- **Scheduled room creation reliability.** The auto-open worker must be idempotent
  (exactly one room per match even across restarts/retries — guard on the stored
  `racetime_room_slug`), tolerate racetime API failures without wedging the match
  (retry with backoff, surface a staff-visible error, allow manual creation as
  fallback), and handle reschedules (a `Match.scheduled_at` that moves after a room
  opened). Getting "open 30 min before" wrong in either direction — no room, or a
  duplicate room — is a race-day incident.
- **ETL field-level read-only enforcement.** The one-way, per-field read-only
  contract (above) has to be enforced at the service layer, not just documented —
  a `MatchService.update_match` gap that lets an ETL-owned field slip through
  would get silently reverted on the next sync and look like a bug. New
  ETL-owned fields introduced later must be added to the guard, not just the
  transform. Identity matching (SG player → `User`) needs the reconcile-later
  path (raw name kept, staff link later), not hard failure.
- **Async run integrity.** Permalinks revealed only at run start; one
  attempt enforced server-side (reattempts only per config); VoD + review flow is
  the anti-cheat backstop. Port these semantics faithfully — they are the feature.
- **The config/code boundary.** User-definable must not drift into
  user-breakable: finite strategy registry, schema-validated config, safe
  template substitution, no `eval`. A need config can't express becomes a new
  named strategy for everyone.
- **Succession scope discipline.** The five features are the succession scope.
  Resist re-expanding toward "reimplement all of SahasrahBot" — anything outside
  the list retires or lives on a thin community bot.

## Succession & cutover

- **Each SahasrahBot community becomes a tenant**; provisioning via the existing
  `/platform` surface. SGL is the first tenant.
- **The cutover gate is the five features**, evaluated per community: a community
  cuts over when the features *it uses* (from this list) are live in SGLMan.
- **Data migration** (SahasrahBot is also Tortoise/Aerich — DB-to-DB backfill is
  feasible): verified racer links → `User.racetime_*`; presets/weightsets →
  `Preset` rows; async tournament history → `AsyncQualifier*` (drain or migrate
  in-flight qualifiers — never cut mid-window); historical results archived.
- **Parallel run during transition**, each community's racing owned by exactly one
  bot at a time (never two bots in one racetime room); SahasrahBot's racetime
  category/bot identity transfers to SGLMan at the end, since Feature 5 makes
  SGLMan the room owner.

## Open questions (for the maintainer)

1. **Non-racing SahasrahBot features** (reaction roles, etc.): retire, or keep on
   a thin community bot? (Nothing in this plan depends on the answer.)
2. **Room-open lead time & auto-open eligibility** — sensible per-tournament
   defaults (e.g. 30 min before start, all matches with two linked players), or
   staff-triggered only until a tournament opts in?

## Related docs

- [architecture.md](architecture.md) — process model, single-worker constraint, bot-as-peer pattern
- [reference/data-model.md](reference/data-model.md) — `User` identity links, `Match`, `Tournament`
- [reference/seed-generation.md](reference/seed-generation.md) — current seedgen + preset gap
- [features/multitenancy.md](features/multitenancy.md) — tenant context, `tenant_scope`, one-bot-many-guilds
- [reference/discord-integration.md](reference/discord-integration.md) — bot/queue patterns the new workers follow
