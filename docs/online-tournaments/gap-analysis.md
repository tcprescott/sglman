# Online Tournaments Plan — Gap Analysis

> Companion to the [Online Tournaments plan](README.md). Findings from an
> adversarial review (six lenses — SahasrahBot parity, SGLMan integration reality,
> data model, internal consistency, operations, product/UX/authz — grounded in the
> actual SahasrahBot source and the SGLMan codebase). This is input for tightening
> the plan, not a verdict that it is broken.

## Executive summary

The plan is **sound as a design doc**: the five-feature scope, the succession
framing, and the user-definable principle hold up, and most "gaps" a mechanical
review surfaces are ordinary implementation details correctly deferred to the phase
that builds them. What follows filters those out and keeps the findings that carry
**real risk if left unrecorded** — split into (A) genuine cross-cutting decisions
the plan has *not actually made*, (B) SahasrahBot integrity behaviors the web-first
pivot could silently regress, (C) result-capture edge cases the clean lifecycle
table hides, and (D) specific schema/ops decisions worth pinning before code.

The three most important: **(1)** every new worker/bot drives service methods gated
on a *human* `User` — there is no system-actor concept, and the plan never decides
one; **(2)** the anti-cheat "hide the pool/par/leaderboard while a qualifier is open"
rule is a hard SahasrahBot invariant that the plan's "richer web browsing" framing
could regress; **(3)** the racetime Finish row models only a clean two-player finish,
but real races end in forfeit / no-show / DQ / N-way, results are frequently wrong
and disputed, and the Challonge sink is strictly 1v1.

## Resolution status (2026-07-14)

Interactive decisions closed the Tier-1 items and several others; details in the
[decisions log](README.md#decisions-log). Four were settled against
[sahabot2](https://github.com/tcprescott/sahabot2), the maintainer's prior working
port.

| Finding | Resolution |
|---|---|
| 1.1 system actor | Reserved system `User` (sentinel `discord_id`); tenant from `tenant_scope` |
| 1.2 config home | Hybrid — typed columns for queried knobs (incl. qualifier `opens_at`/`closes_at`) + validated JSON blob |
| 1.3 racetime topology | Shared, DB-managed `RacetimeBot` rows selected per tournament; tenant-routed |
| 1.4 unresolved identities | **Placeholder `User`** rows (sahabot2): nullable+CHECK `discord_id`, `is_placeholder`, `speedgaming_id`; upgrade in place |
| 1.5 roles | Add `PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN` + per-qualifier `admins` M2M |
| 1.6 reschedule w/ open room | Keep the room, update time + Discord event only; staff handle the room |
| 2.2 reattempt fields | Carry `reattempted` + `reattempt_reason` on `AsyncQualifierRun` |
| 4.2 room slug uniqueness | Its own `RacetimeRoom` model (unique `slug`, `OneToOne→Match`) — from sahabot2 |
| 4.5 reviewer set | Qualifier `admins` M2M; self-review blocked |
| SG read-only contract | Hybrid — per-field lock **and** sahabot2's lifecycle guards (skip finished/manual/room-linked; auto-finish >4h) |
| §5 observability (stuck rooms / dead workers / failed syncs) | Platform external-service health page + first-class racetime bot health (status, heartbeat, alerting) |
| 5.4 MOCK_RACETIME | Scripted event-emitting fake; production-refused like other mock flags |

Still open as build-time detail (Tiers 2–4 not listed above): draw-fairness/par/leaderboard
acceptance criteria (§2.3), run atomicity/one-active-run (§2.4), terminal states &
result dispute (§3.1, §3.3), non-Challonge closure (§3.4), and the remaining Tier-4
schema/index specifics — all to be pinned in their build phase.

## How to read this

Each finding is tagged:

- **DECIDE** — a real decision the plan hasn't made; resolve and record it in a plan doc now.
- **RECORD** — a must-preserve SahasrahBot behavior or acceptance criterion; add it so the building phase can't lose it.
- **FIX** — an internal inconsistency or wording that will mislead a reader.

Severity is my re-adjudication (the automated verify pass over-refuted — see
[Methodology](#methodology)). "Deferred to Phase N" is *not* a reason to omit a
load-bearing behavior from a design doc.

---

## Tier 1 — Genuine unmade decisions (DECIDE)

### 1.1 No system/non-human actor for autonomous flows · high
Every autonomous subsystem the plan adds — the racetime handlers, the auto-open
worker, the SG materializer, Async Qualifier scoring — must drive service methods
that are gated on a human `User` with roles. `MatchScheduleService._transition`
(seat/start/finish/confirm) calls `AuthService.ensure(can_transition_match(actor,…))`,
which returns `False` for a `None` actor; `MatchService.record_match_result` types
`actor: User` (required); `ChallongeService.push_result_if_linked` returns `False`
for `None`. The one existing worker (`volunteer_reminder`) sidesteps this by writing
through the repository and never calling a gated service. The plan routes autonomous
flows through *new* services (`RaceRoomService`, etc.), so it can choose — but it
never does. This is a cross-cutting decision that shapes audit/event attribution and
the data model. **Decide once:** a seeded per-tenant system `User` (cleanest for
audit/event `actor` attribution) vs. an explicit non-human-actor path in the new
services. Record it in README cross-cutting risks + the data-model summary.

### 1.2 The user-definable config has no column to live in · high
The plan's load-bearing differentiator — declarative, schema-validated config
selecting among strategy primitives — has nowhere to persist. `Tournament` has no
JSON/config field; `AsyncQualifier` has no window (`opens_at`/`closes_at`) columns
despite "play within a window" being its whole semantic; the F5 auto-open toggle /
lead time / goal / visibility, F3 event templates, and F1 scoring/reattempt/messaging
config all need a home. This is greenfield (only `Tenant.config` and
`SystemConfiguration` exist, both unvalidated). **Decide** the shape (a validated
`Tournament.config` JSON + `AsyncQualifier` config JSON, or typed columns per knob)
and name it in the data-model summary; at minimum add the `AsyncQualifier` window
columns, which are not optional.

### 1.3 Racetime: one global bot vs. per-tenant, and per-category reality · high
Two conflations. **(a)** racetime bots are one **per game category** (each with its
own client-id/secret, websocket, and racetime-side registration/approval), not "one
connection per process" — the env surface and `MOCK_RACETIME` must model a
category→credentials map. **(b)** Multitenancy: is there one shared SGLMan bot
identity for all tenants (routing rooms→tenant like "one bot, many guilds"), or
per-tenant categories/credentials? The succession story says SahasrahBot's category
"transfers to SGLMan" (singular), implying global — but communities historically own
their own categories. **Decide** and record; it drives the env design, the
room→tenant routing, and the cutover identity transfer.

### 1.4 No storage for unmatched/unlinked identities · high
Both F4 ("unmatched SG players kept as raw names for staff reconciliation") and F5
("raw racetime handle stored on the result for staff to reconcile later") depend on a
place to put an identity that doesn't resolve to a `User`. But `MatchPlayers.user` is
a **required** FK with no `raw_name`/`raw_handle` column — an unmatched SG participant
can't even get a `MatchPlayers` row. The stated graceful-degradation path is
unbuildable as modeled. **Decide** where raw identities live (nullable handle column
on `MatchPlayers`; participant rows on `SpeedGamingEpisode`) and record it.

### 1.5 Roles for the new admin surfaces · high
Every feature adds an admin surface (presets, qualifiers, SG links, racetime
auto-open config), but the `Role` enum is fixed and has no preset-manager /
qualifier-admin / sync-admin, and `AuthService` has no check for them. The plan says
qualifier permissions "map onto SGLMan roles" but never picks the mapping. **Decide**
the authz for each surface (reuse `STAFF` + per-entity admin M2M is the cheapest) and
record it — especially the **Async Qualifier reviewer set** (§2.1), which is central
to integrity and doesn't inherit cleanly because a qualifier is a `Tournament` peer,
not a `Tournament`.

### 1.6 Reschedule / upstream-cancel after a room has opened · high
F5 lists "handle reschedules (`scheduled_at` moves after a room opened)" as a *risk*
with no behavior, and it compounds across features: `scheduled_at` is ETL-owned and
read-only for SG-sourced matches (F4), so an SG reschedule pushes a new time onto a
match that may already have a live room and a synced Discord event (F3). **Decide**
the behavior (cancel/re-open the room? defer start? leave as-is?) across F3/F4/F5 and
record it — this is a cross-feature interaction, not a single-phase detail.

---

## Tier 2 — Integrity behaviors to preserve (RECORD)

These are hard SahasrahBot invariants. The web-first pivot is the right call, but it
removes the Discord-thread machinery that enforced several of them, so they must be
written down as acceptance criteria or they will be lost.

### 2.1 Active-window information lockdown · high
In SahasrahBot, while a qualifier is **active**, only admin/mod may view the
leaderboard, pools, permalinks, and other players' runs; these go public only once
it closes. This is core anti-cheat. The plan actively markets the web surface's
"richer pool/leaderboard browsing" as an advantage — a direct regression risk if
built literally. **Record** in `async-qualifiers.md`: pool, par times, and other
entrants' runs are staff-only until the qualifier is inactive; tie it to the "access
rules" config facet.

### 2.2 Reattempt, forfeit, and one-attempt semantics — and carry the fields · high
The plan says "port faithfully" but the model-mapping table **drops the fields that
are the mechanism**: `AsyncTournamentRace.reattempted` + `reattempt_reason` are how
"one attempt, reattempts only per config" is enforced (a reattempt voids the prior
run, frees the pool slot, excludes it from par/scoring/played-count, requires a
reason, and is limited). Forfeit is irreversible, scores zero, and blocks replay
unless a reattempt is spent. **Record** these rules and **carry `reattempted` /
`reattempt_reason` onto `AsyncQualifierRun`** explicitly.

### 2.3 Draw fairness, par formula, leaderboard aggregation · medium
Three "the feature" behaviors stated only in summary: **(a) draw** is not plain
random — exclude permalinks the user already played, and when pool play-count
imbalance exceeds a threshold, force the least-played permalink. **(b) par** = mean of
the N fastest *finished* runs on a permalink; **score** = clamp(0..105,
(2 − elapsed/par)·100). **(c) leaderboard** = per-pool `runs_per_pool` slots, missing
slot scores 0, with a separate "estimate" over finished runs only, and (today) no
tie-break. **Record** as Phase 7 acceptance criteria so the port preserves even
sampling and stable pars, and **decide** whether "no tie-break / insertion order" is
kept.

### 2.4 Run start atomicity, one-active-run, eligibility, abandonment · medium
Web-first introduces flows the thread model handled implicitly: the permalink draw
("revealed only at start") must be a single locked transaction (no double-draw under
concurrent clicks); only one active run per player at a time; who is *eligible* to
start a run (any tenant user? enrolled only? role-gated?) is unbound; and abandoned
in-progress runs need a disposition (SahasrahBot auto-forfeits after a cap).
**Record** these as Phase 7 criteria; the `pending` run status also needs a defined
meaning now that reveal and start are collapsed.

---

## Tier 3 — Result capture is too clean (RECORD/DECIDE)

### 3.1 Terminal states beyond a clean finish · high
The lifecycle table handles only "Finish" (everyone finishes) and "Cancel." Real
races end in: one finisher + one forfeit (valid win by forfeit), both forfeit,
no-show (nobody joins), or DQ. **Record** how racetime terminal states
(finished/forfeit/dnf/dq) map to `finish_rank`, winner, and match completion.

### 3.2 N-entrant races vs. a 1v1 Challonge sink · high
F5 captures "each entrant's finish time/place," and ALTTPR racetime rooms can be
3-way/FFA — but `ChallongeService.push_match_result` is strictly 1v1 (one winner,
`losers[0]`, raises otherwise). **Decide/record**: scheduled *bracket* matches are
1v1 (fine), but if N-way scheduled races are ever in scope they need a non-Challonge
result path; state the boundary explicitly.

### 3.3 Result correction / dispute flow · high
Racetime results are frequently wrong or contested (forgot `.done`, errant
`.forfeit`, `.undone`, wrong-account finish). The plan captures once at Finish with no
correction path. **Record** that captured results flow through the existing
`record_match_result` / confirm path (so staff override, authz, and audit already
apply) rather than being terminal.

### 3.4 Non-Challonge / non-bracket closure · medium
Finish "hands off to result reporting (Challonge)," but Challonge is optional and many
tournaments are round-robin/swiss/off-Challonge. **Record** that racetime capture
feeds the Match result-record/confirm flow with the Challonge push as an optional
downstream step (which is already how `push_result_if_linked` behaves).

---

## Tier 4 — Data-model specifics (DECIDE, mostly at build time)

| # | Finding | Sev | Action |
|---|---|---|---|
| 4.1 | `Match`↔`SpeedGamingEpisode` is described as **two opposite FKs** (circular) with no authoritative direction | med | Make `Match → SpeedGamingEpisode` the single canonical FK; the reverse is a relation, not a second column. Fix wording in `speedgaming-etl.md`. |
| 4.2 | `Match.racetime_room_slug` needs **global uniqueness + index**, and the room→tenant lookup must use an **explicitly-unscoped** query (inbound events carry no tenant) | med-high | Record: `unique=True, index=True`; route the reverse lookup through an unscoped repo method (mirrors the `ApiToken`→tenant pattern). This is the mechanism behind the stated tenant-routing risk. |
| 4.3 | SG-owned (read-only) `MatchPlayers` rows vs. F5 writing **finish time/place onto the same rows** | med | Add the racetime finish columns to the *SGLMan-owned* side of the F4 ownership table explicitly, or the read-only guard blocks result capture on SG-sourced matches. |
| 4.4 | `MatchPlayers.finish_rank` already exists (it is "place"); only a finish **time** is new, and its type is unspecified | low-med | Record: reuse `finish_rank`, add one finish-elapsed-time column (decide type — interval vs. seconds vs. the `HH:MM:SS` racetime returns) + nullable raw handle. |
| 4.5 | Async Qualifier **reviewer designation** has no model/field after collapsing `AsyncTournamentPermissions` onto global roles | med | Decide: reviewers = the qualifier's admins M2M, or a sibling reviewer M2M. |
| 4.6 | `AsyncQualifierRun` mapping omits **structural FKs** (→qualifier, →user, →permalink, nullable →live_race) and metric fields (`run_igt`, review attribution) | med | Enumerate the FKs; the nullable `live_race` FK is what ties Phase 8 back to runs. |
| 4.7 | `Preset` has **no uniqueness and no owner** (SahasrahBot namespaces per user); mystery weightsets need a **discriminator** vs. fixed-settings presets | med | Record: composite `unique (tenant, randomizer, name)`; register mystery as its own randomizer key rather than overloading one payload. |
| 4.8 | `Tournament.seed_generator` (string) **coexists** with the new `Preset` FK — deprecation/backfill/`on_delete` unstated | med | Record the nullable FK + `SET_NULL` + legacy-string backfill plan in Phase 1. |
| 4.9 | Enum inventories omit the **race-room state** enum (F5) and **DiscordScheduledEvent source-type** enum (F3); `sync status` values (F4) unlisted | low-med | List them; decide whether room-state is a real enum or a cached racetime string. |
| 4.10 | No **indexes** named for the reviewer-queue (`qualifier, review_status`), par recompute (`permalink`), "my runs" (`user`), or Discord-event source lookup | low | Follow the per-model `Meta.indexes` convention when each model lands. |
| 4.11 | `DiscordScheduledEvent` polymorphic source (type+id) has **no uniqueness** for idempotent reconciliation and no cleanup for deleted sources | med | Record `unique (discord_event_id)` + composite source key; define cascade/cancel on source deletion. |
| 4.12 | `SpeedGamingEventLink` / `SpeedGamingEpisode` lack the **observability fields** the "observable sync" promise needs (last_error, last status, cadence, active) and stated cardinality | med | Name them in the F4 data model. |

---

## Tier 5 — Operations & migration (DECIDE)

| # | Finding | Sev | Action |
|---|---|---|---|
| 5.1 | The **SahasrahBot→SGLMan migration** is asserted "feasible" with zero mechanics: PK/FK remapping (SahasrahBot `User` PKs → SGLMan global `discord_id`), `guild_id`→tenant derivation, preset-namespace flattening, in-flight handling, downtime | med-high | The succession story's biggest hand-wave. Commit to a migration-runbook doc before the first cutover (schema-map + PK/FK translation via `discord_id` joins + dry-run). |
| 5.2 | **Restart orphans live rooms**: every push to `main` recreates the container and kills all handler tasks; "reconnect/resume" is named but has no mechanism | med-high | Record a boot-time reconciliation step: query Matches with open/in-progress room state and re-spawn handlers under `tenant_scope`. |
| 5.3 | **No test strategy** for the new worker/websocket/ETL surface — exactly the category the SQLite suite already can't reach (per `development.md`) | med | Plan a Postgres CI job (ETL upserts, read-only guard) + stub-driven `RaceRoomService` transition tests independent of a live websocket. |
| 5.4 | **`MOCK_RACETIME` depth**: it is a *result-capture bypass* that can fabricate finishes → must refuse under `ENVIRONMENT=production` like the other mock flags; and "exercise the full lifecycle end to end" needs a *scripted event-emitting fake*, not a no-op skip like `MOCK_DISCORD` | med | Record both: production-refusal parity, and that the mock is an active fake driving inbound room transitions. |
| 5.5 | New **env vars/credentials never enumerated** (`RACETIME_*` bot + OAuth are two distinct credential sets with distinct mocks; SG API auth; per-randomizer keys) | med | Each phase PR extends the `deployment.md` env table; note the bot-vs-OAuth split now. |
| 5.6 | Boot-time forward-only migrations + new stateful workers make **rollback worse**, with no per-worker kill switch | low-med | Add a `*_ENABLED` flag per subsystem (like `TELEMETRY_ENABLED`) so a bad worker can be disabled without a rollback. |
| 5.7 | **Rate-limit/backoff** for SG poll, racetime, and Discord bulk event ops is gestured at but unspecified | low-med | Name the poll cadence and reuse the existing `webhook_service` backoff pattern when each worker lands. |

---

## Tier 6 — Consistency & wording (FIX)

| # | Finding | Action |
|---|---|---|
| 6.1 | `discord-events-sync.md` names "Async Qualifier windows/live races" as a source, but Async Qualifiers ship in **Phase 7–8, after** Discord Events (Phase 6) | Add a half-clause that qualifier sources are mirrored once that subsystem lands; the roadmap already scopes P6 to native+SG only, so this is a doc-internal contradiction to smooth. |
| 6.2 | The decisions log says the qualifier is "**entirely outside the Match/schedule system — no structural FK**," but `AsyncQualifierLiveRace.episode_id` becomes an FK to the SG episode/match | Tighten to "no *workflow* FK; live races may reference a SG episode where applicable." |
| 6.3 | Flat "rooms auto-created on schedule … not on demand" statements omit the **opt-in gate** stated elsewhere | Append "(opt-in per tournament)" to the two overview mentions so they don't drift from the decision. |

---

## Deliberately out of scope (not gaps)

So these aren't re-raised: the **Discord-thread execution model** and its
reveal→ready grace/extend-timeout mechanics (dropped with the web-first decision);
**spoiler races, dailies, ranked-choice voting** (retire with SahasrahBot);
**general community-bot features** (thin-bot); **per-match settings-submission**
(`TournamentGames`) and SahasrahBot's dormant `Schedule*` models (superseded by the
SG ETL). The create-time write paths (`create_match`/`submit_match_request`) are
*not* a read-only-enforcement leak — they mint fresh, non-sourced, fully-editable
matches, which is exactly the SGLMan-owned side of the contract.

## Methodology

Six independent finder lenses produced 91 candidate gaps, each grounded in the
SahasrahBot source and the SGLMan codebase; each was then adversarially verified.
**The verify stage was miscalibrated** — it was instructed to default to "not a gap"
and to treat anything deferred to a build phase as covered, so it refuted all 80
verified candidates. That bar is wrong for a gap analysis (a design doc that omits a
load-bearing invariant *has* a gap even if a later phase would build it), so this
report is a **re-adjudication** of the candidate set by the plan author, keeping the
findings with genuine risk and dropping the true false-positives (noted above). The
synthesis run itself was cut off by a session usage limit; this document was
assembled from the workflow's per-agent journal. Net: ~30 findings kept of 91
candidates, re-severitised by whether they require an unmade decision, protect an
integrity invariant, or are ordinary deferrable detail.
