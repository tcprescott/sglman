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

> **SGLMan is the designated successor to SahasrahBot** (decided 2026-07-12). The
> end state is that SahasrahBot is **retired** and SGLMan is the single platform
> for both SpeedGaming Live's on-site events *and* the broader community's online
> racing/tournaments. That reframes this effort: it is not "add an online feature
> to SGLMan" but "**absorb SahasrahBot's tournament-running mission into SGLMan and
> switch over.**" The consequences — hosting the whole community via multitenancy,
> inheriting SahasrahBot's racetime identity, a feature-parity bar before cutover,
> and a data-migration story — are collected under
> [Succession & cutover](#succession--cutover).

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

## Design principle: user-definable tournament logic

**This is the load-bearing difference from SahasrahBot and it shapes every design
choice below.** In SahasrahBot, each tournament is a **bespoke Python handler
class** — its racetime category/goal, seed roll, room messages, scheduling rules,
scoring, and result reporting are all hardcoded, so standing up a new tournament
(or letting a new community run one) means a developer writes and ships code.

SGLMan's goal is the inverse: **a community defines a tournament's behavior as
data, through the admin UI, with no code change and no deploy.** A tenant admin
creates a tournament format the same way they already create tournaments, stream
rooms, and volunteer positions today.

The realistic, buildable shape of "user-definable" is **declarative configuration
that selects among built-in strategy primitives, plus templated text** — *not* a
scripting engine or per-tenant plugin code (which would reintroduce the
code-per-tournament problem, just relocated). Concretely, a tournament config lets
an admin choose and parameterize:

| Configurable facet | Chosen from / authored as | Replaces (SahasrahBot) |
|---|---|---|
| Seed source | a randomizer + a **preset** (DB row, UI-authored) | hardcoded roll per handler |
| Race-room behavior | a room template: auto-start, streaming rule, **seed-attach timing**, message templates with `{placeholders}` | hardcoded room setup |
| Match format | a **strategy** enum + params (`single`, `best_of_N`, tiebreak) | per-handler game logic |
| Scoring | a **strategy** enum + params (`fastest_time`, `par_based`, `points`) | `*_scoring_service` per tournament |
| Scheduling | a mode (`staff`, `self_service`) + window rules | per-handler scheduling |
| Result reporting | a target (`challonge`, `none`) | per-handler reporting |
| Eligibility | linked-identity + role/enrollment gates | `*_verification_service` |

The engine implements a **finite, named set of strategies**; the config picks and
parameterizes them. New *primitives* (a new scoring strategy, a new randomizer
backend) are still code — but a new *tournament* is pure config. That line is what
keeps the system both flexible and maintainable.

**Implications carried through the rest of this plan:** presets are **DB-backed and
UI-authored** (not files in the repo); per-tournament behavior lives in a
**declarative tournament config** (see
[Declarative tournament configuration](#declarative-tournament-configuration)); and
SahasrahBot's per-tournament handler classes are **generalized into that config**,
not ported.

---

## Scope decisions (proposed — confirm before building)

0. **Tournament logic is user-definable, not code-per-tournament** (see the
   [design principle](#design-principle-user-definable-tournament-logic) above) —
   the constraint that governs decisions 1–6.
1. **racetime.gg is the online race substrate.** We integrate against it rather
   than building a race timer. A category-scoped racetime **bot** account rolls
   and monitors rooms; individual **players link their racetime identity** by
   OAuth (mirrors Twitch linking). Because SGLMan **succeeds** SahasrahBot, the
   long-term target is for SGLMan's bot to **take over SahasrahBot's existing
   racetime category and bot identity** at cutover, not to run a parallel one.
2. **One racetime bot connection per process**, started in the FastAPI lifespan
   alongside the Discord bot, subject to the same **single-uvicorn-worker**
   constraint ([architecture.md](architecture.md)). See
   [The single-worker constraint](#risk-the-single-worker-constraint) — this is
   the sharpest architectural risk.
3. **Extend the existing `Match` model for scheduled online races; add a new
   `AsyncTournament` subsystem for async qualifiers.** Scheduled head-to-head
   online matches are the current `Match` plus a race room; async qualifiers are a
   genuinely new paradigm (no `Match`, no schedule) and get their own models.
4. **Multitenant from day one — and this is how the whole community is hosted.**
   Everything new is tenant-scoped exactly like the rest of the app
   ([multitenancy.md](features/multitenancy.md)): a `tenant` FK, scoped
   repositories, per-tenant racetime config. A racetime room is routed back to its
   tenant the same way a Discord guild is. Succession makes this concrete:
   SahasrahBot serves **many communities/guilds**, so each becomes a **tenant** in
   SGLMan — multitenancy is not just for SGL, it is the mechanism that lets one
   SGLMan deployment absorb SahasrahBot's entire installed base.
5. **Reuse, don't fork, the crew/restream layer.** Online restreams reuse
   `StreamRoom`, `Commentator`, `Tracker`, and the crew signup/ack flow. "Station"
   assignment is simply unused for non-restreamed races.
6. **Presets become first-class *and user-managed*.** A preset is a **DB row a
   tenant admin authors/edits in the UI** (randomizer + settings payload), not a
   file in the repo; the tournament/match/async pool references it. The existing
   `presets/` files become importable built-in defaults, replacing the current
   hard-coded-path-per-randomizer scheme.

---

## SahasrahBot inventory → port mapping

From `alttprbot/services/` (the authoritative subsystem list). Each row is
classified **Port** (bring it in), **Have** (already in SGLMan), **Adapt** (port
but reshape to SGLMan's models), **Generalize** (replace bespoke code with
user-facing config), or **Skip** (out of scope for tournament running).

**Succession raises the bar.** Because SGLMan *replaces* SahasrahBot rather than
sitting beside it, the deferred racing features (spoiler races, settings voting,
dailies) are no longer optional "nice-to-haves" — they become **parity items that
must exist before cutover**, just still later phases (marked _parity_ below). Only
the pure Discord-community features (reaction/voice roles, holy images, inquiries)
remain genuine **Skip** candidates — see the [succession boundary](#succession--cutover)
for where that line falls.

| SahasrahBot service | Disposition | SGLMan home |
|---|---|---|
| `tournament/` handler classes (per-tournament logic) | **Generalize** | **not ported** — replaced by the [declarative tournament config](#declarative-tournament-configuration) + strategy engine |
| `race_room_service` | **Port** | new `racetimebot/` + `RaceRoomService` — create/monitor racetime rooms |
| `async_tournament_service` and friends (`_live_race`, `_permissions`, `_scoring`) | **Adapt** | new `AsyncTournament*` models + `AsyncTournamentService` |
| `tournament_scheduling_service` | **Adapt** | fold into `MatchScheduleService`; add self-service scheduling |
| `tournament_results_service` | **Adapt** | new `RaceResultService`; report to Challonge |
| `tournament_games_service` | **Adapt** | multi-game matches (best-of-N) on `Match` |
| `preset_service` | **Port** | new `PresetService` over `presets/` (see [Presets](#presets)) |
| `seedgen/` | **Have** (partial) | `SeedGenerationService` — extend with preset selection |
| `racer_verification_service`, `verified_racer_service`, `nick_verification_service` | **Adapt** | racetime identity linking on `User` (OAuth, like Twitch) |
| `spoiler_race_service` | **Port** (_parity_, later) | spoiler-log races — a race-room variant |
| `daily_service` | **Port** (_parity_, later) | recurring community dailies — needed to retire SahasrahBot's racing role |
| `ranked_choice_service` | **Port** (_parity_, later) | settings voting for finals |
| `triforce_text_service` | **Have** | already ported ([triforce-texts.md](features/triforce-texts.md)) |
| `audit_service`, `audit_messages_service` | **Have** | `AuditService` |
| `user_service`, `authorization/`, `guild_config_service` | **Have** | `UserService`, `AuthService`, multitenancy `config` |
| `discord_server_service`, `reaction_role_service`, `voice_role_service`, `holy_image_service`, `konot_service`, `inquiry_message_config_service`, `_notify` | **Skip?** | general Discord-community features, not tournament/racing — the one **succession boundary** still to confirm (retire, keep in a separate lightweight bot, or absorb) |

**Takeaway:** the *tournament-running* core reduces to five new things —
**racetime bot + room service**, the **declarative tournament config + strategy
engine** (the piece that replaces SahasrahBot's per-tournament handlers),
**async tournaments**, **user-managed presets**, and **racetime identity linking**
— plus adapting scheduling/results to close the loop. The parity features
(spoiler/voting/dailies) follow later; only the general-community bot features are
candidates to leave behind.

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

### Presets (user-managed)

SGLMan today hard-codes one preset path per randomizer and has **no
preset-selection mechanism** ([seed-generation.md](reference/seed-generation.md)).
Online tournaments need to choose settings per tournament/pool (SGL settings vs.
open vs. a finals ruleset) — and per the [design principle](#design-principle-user-definable-tournament-logic),
**a tenant admin authors those in the UI**, not a developer in the repo:

- A `Preset` model (tenant-scoped): `name`, `randomizer`, `settings` (JSON payload
  passed to the seed backend), `description`. CRUD on an admin **Presets** tab.
- A `PresetService` over the model; `SeedGenerationService.generate_seed` takes a
  preset (resolved settings) instead of opening a hard-coded path.
- The existing `presets/` files ship as **importable built-in defaults** — a new
  tenant can clone "SGL 2025 ALTTPR" as a starting point, then edit it. Keeps the
  current behavior working while making presets data, not code.

### Declarative tournament configuration

This is the subsystem that **replaces SahasrahBot's per-tournament handler
classes** and realizes the [design principle](#design-principle-user-definable-tournament-logic).
A tournament (and, later, an async pool) carries a structured config an admin
edits through the UI; the runtime reads it — it never branches on "which
tournament is this."

- **Storage.** A structured JSON config on `Tournament` (validated by a Pydantic
  schema), or a dedicated `TournamentConfig` model if it grows relationships. It
  references a `Preset` by id and names a strategy + params for each facet (seed,
  room, format, scoring, scheduling, reporting, eligibility — the table in the
  design principle).
- **Strategy engine.** Each facet resolves to one of a **finite, registered set of
  strategy implementations** (`application/services/tournament_strategies/` or
  similar). Adding a strategy is a code change; *choosing and parameterizing* one
  is config. `RaceRoomService`, `RaceResultService`, and the scheduler ask the
  config for the active strategy rather than hardcoding behavior.
- **Templated text.** Room names and racetime chat messages are **templates with
  `{placeholders}`** (player names, seed URL, round label) rendered at runtime —
  so a community customizes announcements without touching code. Rendering is a
  safe substitution, **not** `eval` / arbitrary expressions.
- **Validation & safety.** The config is schema-validated on save (unknown
  strategy → `ValueError` surfaced in the UI); a template referencing an unknown
  placeholder fails at save, not at race time. This is the guardrail that keeps
  "user-definable" from becoming "user-breakable."

The explicit **non-goal** is a scripting/plugin system: no per-tenant Python, no
expression language. Anything a config can't express is a request for a **new
named strategy**, added once and then available to every tenant as a menu choice.

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
| new `Preset` model (tenant-scoped) | user-authored randomizer settings, referenced by tournaments/pools |
| `Tournament.config` JSON (or `TournamentConfig` model) | declarative, UI-authored per-tournament behavior (strategies + templates + preset ref) |
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

**Phase 2 — user-managed presets + declarative tournament config.** The `Preset`
model + admin **Presets** tab; the `Tournament.config` schema and the strategy
engine (seed/room/format/scoring/scheduling/reporting selected + parameterized in
the UI); templated room text. This is the piece that **replaces SahasrahBot's
per-tournament handlers** and the foundation Phase 3 reads from. For ALTTPR-first,
only the strategies the scheduled loop needs must ship (`single`/`best_of_N`
format, `fastest_time` scoring, `challonge` reporting); the rest are added as
menu choices later. Presets are useful on their own (on-site staff can pick them too).

**Phase 3 — scheduled online races (the core loop).** From a scheduled `Match`,
create a racetime room **driven entirely by the tournament config** (no
per-tournament code); the handler seeds it at the countdown, records start/finish,
and `RaceResultService` writes results and reports to Challonge via the configured
strategy. This is the first end-to-end online match and reuses the entire existing
crew / restream / notification stack.

**Phase 4 — self-service scheduling.** Let players (not just staff) propose/confirm
match times using the existing `PlayerAvailability` + Challonge matchup data. Turns
the on-site "staff schedules everyone" model into player-driven scheduling.

**Phase 5 — async tournaments.** The `AsyncTournament*` models, permalink pools,
one-attempt enforcement, par scoring, leaderboard page, and live-race review.

**Phase 6+ — parity features.** Spoiler races, settings ranked-choice voting for
finals, and community dailies. Under succession these are **required for cutover**
(not optional extras) but come after the scheduled-bracket core is stable — see
[Succession & cutover](#succession--cutover).

---

## Succession & cutover

SGLMan replacing SahasrahBot is a **migration project, not just a feature build**.
The phased roadmap above delivers the *capabilities*; this section covers what it
takes to actually **switch the community over and turn SahasrahBot off**. It is an
orthogonal track that runs alongside the feature phases and gates the final cutover.

### Each SahasrahBot community becomes a tenant

SahasrahBot serves many Discord guilds. Succession maps each onto a **tenant**
([multitenancy.md](features/multitenancy.md)): its guild id, racetime config,
presets, roles, and members live under one `Tenant`. Onboarding a community is
"provision a tenant," which the `/platform` super-admin surface already does. SGL
itself is simply the first, already-existing tenant.

### Feature-parity checklist (the cutover gate)

SahasrahBot cannot be retired for a given community until SGLMan covers what that
community actually relies on. The bar is **per-community**, not global — a bracket
-only community can cut over long before an async-heavy one. The checklist:

- [ ] Scheduled race rooms + auto-seed + result capture (Phase 3)
- [ ] racetime identity linking for that community's racers (Phase 0)
- [ ] The presets/settings that community races on, imported (Phase 2)
- [ ] Result reporting to their bracket (Phase 3, Challonge today)
- [ ] Async qualifiers, **if** the community runs them (Phase 5)
- [ ] Spoiler races / settings voting / dailies, **if** used (Phase 6)
- [ ] The [succession boundary](#the-succession-boundary) resolved for their
      general-community bot features

### Data migration

A retirement is only clean if history and in-flight state survive. Inventory of
SahasrahBot data that needs a migration path (SahasrahBot uses the same Tortoise +
Aerich stack, so a direct DB-to-DB backfill is feasible):

| SahasrahBot data | SGLMan target | Notes |
|---|---|---|
| Verified/linked racers (racetime ↔ discord) | `User.racetime_*` | so results attribute post-cutover; the whole point of Phase 0 |
| Presets | `Preset` rows | per-tenant import |
| Guild config | `Tenant.config` | racetime category, defaults |
| Historical race/tournament results | results tables | preserve records, or archive read-only |
| **In-flight async tournaments** | `AsyncTournament*` | the sharp edge — a live event cannot be cut mid-flight; migrate or drain first |

### The succession boundary

The one genuinely open scope question (see [Open questions](#open-questions-for-the-maintainer)):
SahasrahBot also does **general Discord-community management** (reaction roles,
voice roles, holy images, inquiries) that has nothing to do with racing. Three
options, to confirm:

1. **Retire them** — communities drop the feature or move it to an off-the-shelf bot.
2. **Keep a thin SahasrahBot** — retire only its tournament/racing role; a
   stripped-down bot keeps the community-management bits.
3. **Absorb them** — SGLMan grows a community-management surface (largest scope,
   dilutes SGLMan's tournament-manager focus).

The plan's default is **(1)/(2)** — SGLMan succeeds the *tournament/racing*
mission and stays a tournament manager, not a general community bot. Confirm before
this constrains any design.

### Cutover strategy

**Per-community, incremental — not big-bang.** Because each community is a tenant
and the parity bar is per-community, communities move over one at a time as their
checklist fills. Run SGLMan and SahasrahBot **in parallel during the transition**,
with each community's racetime handling owned by exactly one of them at a time
(avoid two bots in one room). SahasrahBot's racetime category/bot identity transfers
to SGLMan only once the last dependent community has cut over.

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

### Risk: the config/code boundary (user-definable without user-breakable)

The [user-definable principle](#design-principle-user-definable-tournament-logic)
lives or dies on drawing the line correctly. Too rigid and communities can't
express their format without a code change (the problem we're solving); too open
(a scripting/expression engine) and we get untestable, unsafe, unsupportable
per-tenant logic plus a security surface. The design answer is a **finite,
registered strategy set + schema-validated config + safe template substitution**:
every config is validated on save, every template placeholder is checked against a
known set, and there is **no `eval`**. When a real need can't be expressed, the fix
is to add one **named strategy** for everyone — a deliberate, reviewed code change —
not to widen the config into a language. Guarding this line is an ongoing design
discipline, not a one-time decision.

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

### Risk: succession pulls in scope creep

Succession is the biggest scope risk in the plan: "replace SahasrahBot" can quietly
expand to "reimplement all of SahasrahBot." Two disciplines hold the line. First,
SGLMan succeeds the **tournament/racing** mission only; general community-management
features (reaction/voice roles, holy images, inquiries) are the
[succession boundary](#the-succession-boundary), defaulting to *not absorbed*.
Second, the parity checklist is **per-community** — build what a community actually
uses before cutting *it* over, rather than pre-building every SahasrahBot feature for
a hypothetical user. Cut over the communities you can serve; don't gate everything on
the union of all features.

---

## Open questions (for the maintainer)

_Resolved 2026-07-12:_ **Games** — start **ALTTPR-only**. **Priority** —
**scheduled restreamed brackets** first (Phase 3); async qualifiers deferred.
**SahasrahBot relationship** — SGLMan **succeeds** it (full replacement, not
coexistence); see [Succession & cutover](#succession--cutover).

Still open:

1. **The succession boundary.** What happens to SahasrahBot's non-racing
   community-management features — retire, keep in a thin bot, or absorb? Default
   is *not absorbed* ([the succession boundary](#the-succession-boundary)).
2. **racetime bot account/category.** SGLMan inherits SahasrahBot's category at
   cutover, but during the parallel-run transition: one shared category with
   `guild_id`-style routing, or per-tenant categories? (Shared is simpler; per-tenant
   is cleaner isolation but more operational overhead.)

---

## Related docs

- [architecture.md](architecture.md) — process model, single-worker constraint, bot-as-peer pattern
- [reference/data-model.md](reference/data-model.md) — `User` identity links, `Match`, `Tournament`, Challonge models
- [reference/seed-generation.md](reference/seed-generation.md) — current seedgen + the preset gap
- [features/multitenancy.md](features/multitenancy.md) — tenant context, `tenant_scope`, one-bot-many-guilds routing
- [reference/discord-integration.md](reference/discord-integration.md) — the bot/handler pattern the racetime bot mirrors
- [multitenancy-plan.md](multitenancy-plan.md) — the house style this plan follows
