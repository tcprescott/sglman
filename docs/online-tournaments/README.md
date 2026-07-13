# Online Tournaments Plan (proposal)

> Status: **proposed, not implemented.** This is the design/implementation plan for
> adapting SGLMan — today an *on-site* tournament manager — to also support **online
> tournaments**, forward-porting a defined set of functionality from
> [SahasrahBot](https://github.com/tcprescott/sahasrahbot). No code in this plan has
> shipped. When work begins, track progress in
> [current-state.md](../current-state.md) and split each phase into its own PR.

This is the **overview / index**. Each of the five features has its own document;
this hub holds the cross-cutting material — decisions, scope, roadmap, shared
risks, and the succession story. A [gap analysis](gap-analysis.md) reviews the plan
for unmade decisions and must-preserve behaviors before implementation.

## The five feature documents

| # | Feature | Doc | One-line |
|---|---|---|---|
| 1 | Async Qualifiers | [async-qualifiers.md](async-qualifiers.md) | Self-paced permalink-pool qualifiers; a standalone peer aggregate of `Tournament`, web-first |
| 2 | Seed rolling | [seed-rolling.md](seed-rolling.md) | User-managed presets + incremental coverage toward every SahasrahBot randomizer |
| 3 | Discord Events sync | [discord-events-sync.md](discord-events-sync.md) | Idempotent auto-sync of Discord Scheduled Events from SGLMan schedule data |
| 4 | SpeedGaming schedule ETL | [speedgaming-etl.md](speedgaming-etl.md) | One-way ETL of SG episodes into SGLMan `Match` rows; hybrid read-only (per-field + lifecycle guards); placeholder users for unresolved players |
| 5 | Racetime race-room lifecycle | [racetime-room-lifecycle.md](racetime-room-lifecycle.md) | Full racetime.gg room lifecycle, auto-created on schedule, through finish/cancel |

## Decisions log

| Date | Decision |
|---|---|
| 2026-07-12 | First online focus: **scheduled restreamed brackets**; **ALTTPR-first** game scope |
| 2026-07-12 | Tournament logic is **user-definable** (declarative config, not code-per-tournament) — see [design principle](#design-principle-user-definable-tournament-logic) |
| 2026-07-12 | **SGLMan succeeds SahasrahBot** (full replacement of its tournament/racing mission, not coexistence) |
| 2026-07-13 | **Forward-port scope fixed at five features** (see [Scope](#scope-the-five-forward-ported-features)): Async Qualifiers, seed rolling, Discord Events sync, SpeedGaming ETL, racetime race-room lifecycle. Supersedes the earlier broad port map and the "parity items before cutover" framing |
| 2026-07-13 | **SGLMan owns the full racetime race-room lifecycle** ([Feature 5](racetime-room-lifecycle.md), added after the initial four): create → open → in-progress → finished/cancelled, for scheduled matches. **Rooms are auto-created on schedule** (opened ahead of `Match.scheduled_at`), not on demand. Reverses the earlier "race-room automation out of scope" decision and resolves the corresponding open question. |
| 2026-07-13 | SahasrahBot's **Async Tournament** is renamed **Async Qualifier** in SGLMan — its workflow is completely different from a tournament's and the name collision with `Tournament` would mislead |
| 2026-07-13 | SpeedGaming schedule data comes in via an **ETL/sync process** into SGLMan's own tables — *not* SahasrahBot's approach of live-querying the SG API per interaction |
| 2026-07-13 | `AsyncQualifier` is a **standalone peer aggregate of `Tournament`**: created/administered the same way (many can run concurrently per tenant), but a **distinct state machine** entirely outside the `Match`/schedule system — no structural FK between the two |
| 2026-07-13 | **SG sync is strictly one-way** (SG → SGLMan, never back). For a `Match` created by the ETL, **the ETL-owned fields are read-only in SGLMan** — enforced at the service layer, not just convention. See [Feature 4](speedgaming-etl.md). |
| 2026-07-13 | **Async Qualifier execution is web-first, decided (not open).** SahasrahBot's Discord-thread-driven run execution (slash command → private thread → buttons) is **dropped**, not ported, not offered as a config toggle. Drawing a permalink, timing a run, submitting time/VoD, and review all happen on SGLMan web pages; Discord is notification-only via the existing DM queue. Live races still need a racetime.gg bot connection for synchronous group races, but that's separate from the core async execution loop. |
| 2026-07-13 | **SahasrahBot's non-racing community features survive on a thin bot.** Only SahasrahBot's tournament/racing role is retired into SGLMan; a stripped-down SahasrahBot keeps the community-management bits (reaction/voice roles, holy images, inquiries, `konot`). SGLMan does **not** absorb them — it stays a tournament manager. |
| 2026-07-13 | **Racetime auto-open is opt-in per tournament.** No room is auto-created until a tournament explicitly enables auto-open and sets its lead time — nothing opens unexpectedly. |
| 2026-07-13 | **Auto-open eligibility: all entrants have a linked racetime identity.** A room auto-opens only when every player in the match has linked racetime (clean result attribution); matches with an unlinked entrant are left to manual creation. |
| 2026-07-14 | **Gap-analysis decisions.** The following resolve findings in the [gap analysis](gap-analysis.md); several are informed by [sahabot2](https://github.com/tcprescott/sahabot2), the maintainer's prior working port (now a reference in this session). |
| 2026-07-14 | **Autonomous actor = a reserved system `User`.** Workers/bots (racetime handlers, auto-open worker, SG materializer, qualifier scoring) act as one seeded system `User` (sentinel `discord_id`), with tenant from `tenant_scope`. Fits the "pass `actor: User` explicitly" audit convention. (sahabot2 used a `SYSTEM_USER_ID = -1` sentinel + null-actor audit; a real row suits sglman's actor-snapshotting audit better.) |
| 2026-07-14 | **Config storage = hybrid (typed columns + validated JSON).** Worker-queried knobs (qualifier `opens_at`/`closes_at`, `auto_open` bool, lead time, `require_racetime_link`, goal) are typed columns; templates, scoring params, and strategy choices live in a Pydantic-validated JSON config on `Tournament`/`AsyncQualifier`. Directly mirrors sahabot2's `Tournament` (typed racetime/SG columns + `settings_form_schema`/`preset_selection_rules` JSON). |
| 2026-07-14 | **Racetime topology = shared bots, tenant-routed, DB-managed.** Refined from sahabot2: racetime bots/categories are first-class `RacetimeBot` rows (creds per category), shared across tenants, and a `Tournament` selects one via FK; rooms route back to their tenant. Not per-tenant credentials, not one hard-coded connection. |
| 2026-07-14 | **Unresolved SG/unlinked identities = placeholder `User` rows** (sahabot2 pattern). `User.discord_id` becomes nullable+unique with `CHECK (discord_id IS NOT NULL OR is_placeholder)`, plus `is_placeholder` and `speedgaming_id`. An unresolved SG player gets a placeholder `User` (so `MatchPlayers.user` stays NOT NULL), upgraded in place when a `discord_id` later appears. Resolution order: `discord_id` → `discord_username` → placeholder-by-`speedgaming_id` → create placeholder. |
| 2026-07-14 | **SG read-only contract = hybrid (both guards).** Keep per-field read-only in the UI (staff can't edit ETL-owned fields on SG-sourced matches) AND adopt sahabot2's lifecycle guards: re-sync skips matches that are finished, have any manual status, or have a linked racetime room; auto-finish matches >4h past scheduled. Defense in depth. |
| 2026-07-14 | **New admin surfaces get dedicated roles.** Add `PRESET_MANAGER`, `SYNC_ADMIN` (SG links + Discord events + racetime config), and `QUALIFIER_ADMIN` to the `Role` enum, plus a per-qualifier `admins` M2M (like `Tournament.admins`) for scoping a single qualifier. |
| 2026-07-14 | **Qualifier reviewers = the qualifier's `admins` M2M; self-review blocked.** A reviewer cannot approve/reject their own run. |
| 2026-07-14 | **Reschedule with an open room = keep the room, update time only.** On an upstream reschedule after a room opened, update `scheduled_at` + the Discord event; leave the open room as-is (staff manually cancel/recreate if warranted). Never auto-disrupt a room. |
| 2026-07-14 | **Racetime room = its own `RacetimeRoom` model** (sahabot2), not a slug column on `Match`: unique `slug`, `category`, `status`, `OneToOne→Match` (SET_NULL), `FK→RacetimeBot`. Decouples room lifecycle from `Match` and prevents orphaned slugs. |

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
maintainer has fixed the succession scope to the five features above — SahasrahBot
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

Every feature is designed under this constraint.

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
| 1 | **[Async Qualifiers](async-qualifiers.md)** (renamed from *Async Tournament*) | `models/async_tournament.py`, `services/async_tournament_*` | New tenant-scoped `AsyncQualifier*` subsystem; **web-first execution, decided** — Discord-thread run flow dropped |
| 2 | **[Seed rolling](seed-rolling.md)** — eventually every SahasrahBot-supported randomizer | `services/seedgen/`, `models/presets.py` | Extend `SeedGenerationService`; add user-managed `Preset` model; incremental randomizer coverage |
| 3 | **[Discord Events sync](discord-events-sync.md)** | `ScheduledEvents` model (`episode_id` ↔ `scheduled_event_id`) | Generalized auto-sync of Discord Scheduled Events from SGLMan schedule data, per tenant guild |
| 4 | **[SpeedGaming schedule ETL](speedgaming-etl.md)** | direct SG API queries keyed on `episode_id` throughout | **New approach**: periodic ETL into SGLMan tables; SG becomes an upstream data source, not a per-interaction dependency |
| 5 | **[Racetime race-room lifecycle](racetime-room-lifecycle.md)** | `services/race_room_service`, the `racetime-bot` handler framework | New `racetimebot/` subsystem (peer of `discordbot/`); **auto-creates rooms on schedule** and owns the full room lifecycle through finish/cancel, incl. seed attach + result capture |

### Explicitly not ported

- **Per-tournament handler classes** — replaced by the user-definable config
  (design principle above), not translated.
- **Spoiler races, community dailies, ranked-choice voting** — retire with
  SahasrahBot (previously misclassified as pre-cutover parity items).
- **General Discord-community features** (reaction/voice roles, holy images,
  inquiries, `konot`) — outside the tournament/racing mission. **Decided:** these
  survive on a **thin SahasrahBot** (only its tournament/racing role retires into
  SGLMan); SGLMan does not absorb them.
- **SahasrahBot's dormant `Schedule*` models** (`ScheduleEvent`,
  `ScheduleEpisode`, …) — an unfinished in-house scheduling attempt with live
  tables but no runtime usage. The SG ETL supersedes the idea; do not port the
  models.

## Data-model additions (summary)

Canonical list; each feature doc details its own slice.

| Model / change | Feature |
|---|---|
| `User.racetime_user_id` / `_username` / `_linked_at` (global, unique, OAuth identity-only) | 5 (result attribution), 1 (live races) |
| `Preset` (tenant-scoped) + `Tournament`/pool preset FKs | 2 |
| `AsyncQualifier`, `AsyncQualifierPool`, `AsyncQualifierPermalink`, `AsyncQualifierRun`, `AsyncQualifierLiveRace`, `AsyncQualifierReviewNote` | 1 |
| `DiscordScheduledEvent` (tenant-scoped link/reconciliation table) | 3 |
| `SpeedGamingEpisode`, `SpeedGamingEventLink` (tenant-scoped); `Match` gains its FK to `SpeedGamingEpisode` (source marker driving read-only enforcement) | 4 |
| `RacetimeRoom` model (unique `slug`, `category`, `status`, `OneToOne→Match` SET_NULL, `FK→RacetimeBot`) + `RacetimeBot` rows; `MatchPlayers` reuses `finish_rank` and gains a finish-time column; per-tournament racetime config columns | 5 |
| `User` gains `is_placeholder` + `speedgaming_id`; `discord_id` → nullable+unique with `CHECK (discord_id IS NOT NULL OR is_placeholder)` (placeholder pattern) | 4 |
| New `Role` members: `PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN`; `AsyncQualifier.admins` M2M | 1,2,3,4 |
| New `AuditActions` + `EventType` members per subsystem (`async_qualifier.*`, `preset.*`, `discord_event.*`, `sg_sync.*`, `race_room.*`) — EventType is an external contract: add, never rename | all |

New enums: run status + review status (Feature 1), sync status (Feature 4).

## Phased roadmap

Ordering follows dependencies, not feature numbering. The **decided first focus —
scheduled restreamed brackets, ALTTPR-first — is delivered by Phases 1–4**
(presets → identity → racetime bot → room lifecycle); the SG ETL, Discord events,
and Async Qualifiers build out from there. SG ETL and Discord Events are
independent of the racetime track and can run in parallel.

1. **Phase 1 — user-managed presets + seedgen preset selection**
   ([Feature 2](seed-rolling.md)). `Preset` model, admin tab,
   `SeedGenerationService` preset arg, built-in preset import. ALTTPR-first;
   immediately useful on-site too.
2. **Phase 2 — racetime identity linking** ([Feature 5](racetime-room-lifecycle.md)
   prerequisite). `User.racetime_*` + OAuth page (mirrors Twitch/Challonge
   linking). Small; also unblocks Async Qualifier live races.
3. **Phase 3 — racetime bot skeleton + `MOCK_RACETIME`**
   ([Feature 5](racetime-room-lifecycle.md)). Stand up `racetimebot/` as a
   lifespan-managed connection with a mockable boundary and a handler that connects
   and tracks room state — proving the single-worker / long-lived-websocket
   architecture before wiring business logic.
4. **Phase 4 — racetime room lifecycle for scheduled matches**
   ([Feature 5](racetime-room-lifecycle.md), the core online loop).
   `RaceRoomService`, the scheduled auto-open worker, seed attach from `Preset`,
   full lifecycle → result capture → Challonge reporting. **This completes
   scheduled online brackets** and reuses the existing crew / stream-room /
   notification stack.
5. **Phase 5 — SpeedGaming ETL** ([Feature 4](speedgaming-etl.md)). Staging model,
   sync worker, read-only reconciliation contract, admin visibility. Independent of
   the racetime track; parallelizable with Phases 1–4.
6. **Phase 6 — Discord Events sync** ([Feature 3](discord-events-sync.md)).
   Consumes native + SG-imported schedule data; reconciliation worker + config.
7. **Phase 7 — Async Qualifiers core** ([Feature 1](async-qualifiers.md)). Models,
   web run-execution pages (draw permalink, timer, submit time/VoD), reviewer
   queue, par scoring, leaderboard. Discord DM notifications only — no thread-based
   execution.
8. **Phase 8 — Async Qualifier live races** ([Feature 1](async-qualifiers.md) +
   [5](racetime-room-lifecycle.md)). Reuses the Phase 3–4 racetime subsystem: a
   room per live race, result capture into runs.
9. **Phase 9+ — randomizer coverage expansion**
   ([Feature 2](seed-rolling.md) completion). Incremental backends toward full
   SahasrahBot parity; mystery weightsets.

## Cross-cutting risks

Feature-specific risks live in each feature doc. These span multiple features:

- **Background-worker load + a second persistent websocket in one process.** The
  single-uvicorn-worker constraint ([architecture.md](../architecture.md)) now
  hosts the SG sync worker (F4), the Discord events reconciler (F3), the room
  auto-open worker (F5), and the **racetime connection with a task per live room**
  (F5) — alongside the web UI and Discord bot. This is the sharpest architectural
  cost, driven mostly by Feature 5: a busy race day could have many concurrent room
  handlers in the same event loop that serves the UI. Disciplines: non-blocking
  I/O only, bounded concurrency, **per-room error isolation** (a crashing handler
  must not drop the bot or other rooms), reconnect/resume so a dropped websocket
  doesn't orphan live rooms, and `tenant_scope` everywhere (`require_tenant_id()`
  raising is the safety net). If load ever outgrows one process, the racetime bot
  is the natural first thing to split into a sidecar against the same DB —
  explicitly not now.
- **The config/code boundary.** User-definable must not drift into user-breakable:
  finite strategy registry, schema-validated config, safe template substitution,
  no `eval`. A need config can't express becomes a new named strategy for everyone.
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
  category/bot identity transfers to SGLMan at the end, since
  [Feature 5](racetime-room-lifecycle.md) makes SGLMan the room owner.

## Open questions (for the maintainer)

**None currently open** — the scope, succession, and behavior questions raised
during planning are all resolved in the [decisions log](#decisions-log). New
questions that surface as implementation begins go here.

## Related docs

- [architecture.md](../architecture.md) — process model, single-worker constraint, bot-as-peer pattern
- [reference/data-model.md](../reference/data-model.md) — `User` identity links, `Match`, `Tournament`
- [reference/seed-generation.md](../reference/seed-generation.md) — current seedgen + preset gap
- [features/multitenancy.md](../features/multitenancy.md) — tenant context, `tenant_scope`, one-bot-many-guilds
- [reference/discord-integration.md](../reference/discord-integration.md) — bot/queue patterns the new workers follow
- [sahabot2](https://github.com/tcprescott/sahabot2) — the maintainer's prior working port (NiceGUI + FastAPI + Tortoise). Reference implementation for the SG ETL (placeholder users), `RacetimeRoom`/`RacetimeBot`/`RaceRoomProfile` models, and per-tournament config columns. Added to this session's scope.
