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
| 2026-07-13 | **Forward-port scope fixed at four features** (see [Scope](#scope-the-four-forward-ported-features)): Async Qualifiers, seed rolling, Discord Events sync, SpeedGaming ETL. Supersedes the earlier broad port map and the "parity items before cutover" framing |
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
maintainer has fixed the succession scope to the four features below — SahasrahBot
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

## Scope: the four forward-ported features

**These are additive — they sit on top of SGLMan's existing Tournament/Match
capability, which remains the backbone for online tournaments.** Everything the
app already does — tournaments, enrollment, match scheduling and lifecycle, crew
signup/approval, stream rooms, notifications, Challonge mirroring, availability —
serves online events directly; nothing here replaces those workflows. The four
ported features fill the online-specific gaps and plug into that machinery: the
SG ETL materializes into existing `Match` rows, Discord Events sync reads the
existing schedule, presets extend the existing seed-rolling flow, and Async
Qualifiers arrive as a **peer aggregate alongside `Tournament`** — created and
administered the same way, running a distinct machine.

| # | Feature | SahasrahBot source | SGLMan disposition |
|---|---|---|---|
| 1 | **[Async Qualifiers](#1-async-qualifiers)** (renamed from *Async Tournament*) | `models/async_tournament.py`, `services/async_tournament_*` | New tenant-scoped `AsyncQualifier*` subsystem; **web-first execution, decided** — Discord-thread run flow dropped |
| 2 | **[Seed rolling](#2-seed-rolling)** — eventually every SahasrahBot-supported randomizer | `services/seedgen/`, `models/presets.py` | Extend `SeedGenerationService`; add user-managed `Preset` model; incremental randomizer coverage |
| 3 | **[Discord Events sync](#3-discord-events-sync)** | `ScheduledEvents` model (`episode_id` ↔ `scheduled_event_id`) | Generalized auto-sync of Discord Scheduled Events from SGLMan schedule data, per tenant guild |
| 4 | **[SpeedGaming schedule ETL](#4-speedgaming-schedule-etl)** | direct SG API queries keyed on `episode_id` throughout | **New approach**: periodic ETL into SGLMan tables; SG becomes an upstream data source, not a per-interaction dependency |

### Explicitly not ported

- **Per-tournament handler classes** — replaced by the user-definable config
  (design principle above), not translated.
- **Racetime race-room automation for scheduled matches** (`race_room_service`,
  tournament room handlers) — not in the succession scope. The only racetime
  surface retained is what Async Qualifier **live races** require, plus
  racetime **identity linking** on `User`. Room automation for scheduled brackets
  can be revisited later; nothing in this plan forecloses it.
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
   status) — the one racetime-bot dependency this plan keeps.

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

---

## Data-model additions (summary)

| Model / change | Feature |
|---|---|
| `User.racetime_user_id` / `_username` / `_linked_at` (global, unique, OAuth identity-only) | 1 (live races, attribution) |
| `Preset` (tenant-scoped) + `Tournament`/pool preset FKs | 2 |
| `AsyncQualifier`, `AsyncQualifierPool`, `AsyncQualifierPermalink`, `AsyncQualifierRun`, `AsyncQualifierLiveRace`, `AsyncQualifierReviewNote` | 1 |
| `DiscordScheduledEvent` (tenant-scoped link/reconciliation table) | 3 |
| `SpeedGamingEpisode`, `SpeedGamingEventLink` (tenant-scoped); `Match` gains its FK to `SpeedGamingEpisode` (source marker driving read-only enforcement) | 4 |
| New `AuditActions` + `EventType` members per subsystem (`async_qualifier.*`, `preset.*`, `discord_event.*`, `sg_sync.*`) — EventType is an external contract: add, never rename | all |

New enums: run status + review status (Feature 1), sync status (Feature 4).

## Phased roadmap

Ordering follows dependencies, not feature numbering — presets underpin
qualifiers; the ETL feeds Discord events.

1. **Phase 1 — user-managed presets + seedgen preset selection** (Feature 2
   foundation). `Preset` model, admin tab, `SeedGenerationService` preset arg,
   built-in preset import. ALTTPR-first; immediately useful on-site too.
2. **Phase 2 — SpeedGaming ETL** (Feature 4). Staging model, sync worker,
   reconciliation contract, admin visibility. Independent of Phase 1;
   parallelizable.
3. **Phase 3 — Discord Events sync** (Feature 3). Consumes native + SG-imported
   schedule data; reconciliation worker + config.
4. **Phase 4 — racetime identity linking.** `User.racetime_*` + OAuth page
   (mirrors Twitch/Challonge linking). Small; prerequisite for Phase 6.
5. **Phase 5 — Async Qualifiers core** (Feature 1). Models, web run-execution
   pages (draw permalink, timer, submit time/VoD), reviewer queue, par scoring,
   leaderboard. Discord DM notifications only — no thread-based execution.
6. **Phase 6 — Async Qualifier live races.** The racetime-bot slice (mockable
   `MOCK_RACETIME` boundary, room per live race, result capture).
7. **Phase 7+ — randomizer coverage expansion** (Feature 2 completion).
   Incremental backends toward full SahasrahBot parity; mystery weightsets.

## Risks & sharp edges

- **Background-worker load in one process.** The single-uvicorn-worker constraint
  ([architecture.md](architecture.md)) now hosts the SG sync worker, the Discord
  events reconciler, and (Phase 6) racetime connections alongside the web UI and
  Discord bot. Same disciplines as today: non-blocking I/O only, bounded
  concurrency, per-worker error isolation, `tenant_scope` everywhere
  (`require_tenant_id()` raising is the safety net).
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
- **Succession scope discipline.** The four features are the succession scope.
  Resist re-expanding toward "reimplement all of SahasrahBot" — anything outside
  the list retires or lives on a thin community bot.

## Succession & cutover

- **Each SahasrahBot community becomes a tenant**; provisioning via the existing
  `/platform` surface. SGL is the first tenant.
- **The cutover gate is the four features**, evaluated per community: a community
  cuts over when the features *it uses* (from this list) are live in SGLMan.
- **Data migration** (SahasrahBot is also Tortoise/Aerich — DB-to-DB backfill is
  feasible): verified racer links → `User.racetime_*`; presets/weightsets →
  `Preset` rows; async tournament history → `AsyncQualifier*` (drain or migrate
  in-flight qualifiers — never cut mid-window); historical results archived.
- **Parallel run during transition**, each community's racing owned by exactly
  one bot at a time; SahasrahBot's racetime identity transfers at the end if the
  live-race slice needs it.

## Open questions (for the maintainer)

1. **Racetime rooms for scheduled matches** are now out of the port scope —
   confirm that's intended long-term, or parked until after the four features.
2. **Non-racing SahasrahBot features** (reaction roles, etc.): retire, or keep on
   a thin community bot? (Nothing in this plan depends on the answer.)

## Related docs

- [architecture.md](architecture.md) — process model, single-worker constraint, bot-as-peer pattern
- [reference/data-model.md](reference/data-model.md) — `User` identity links, `Match`, `Tournament`
- [reference/seed-generation.md](reference/seed-generation.md) — current seedgen + preset gap
- [features/multitenancy.md](features/multitenancy.md) — tenant context, `tenant_scope`, one-bot-many-guilds
- [reference/discord-integration.md](reference/discord-integration.md) — bot/queue patterns the new workers follow
