# Feature 1: Async Qualifiers

> Part of the [Online Tournaments plan](README.md) (proposed, not implemented).
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).

**Rename:** SahasrahBot calls this *Async Tournament*. In Wizzrobe it is
**Async Qualifier** (`AsyncQualifier*` models, `AsyncQualifierService`) — the
workflow (self-paced runs against a permalink pool inside a window) is nothing
like a `Tournament`'s, and the old name would collide with Wizzrobe's existing
`Tournament` aggregate.

Source: `alttprbot/models/async_tournament.py`, `services/async_tournament_*`.

## A peer aggregate to `Tournament`: same creation, distinct machine

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

## Workflow (ported semantics)

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
   status). These reuse the [Feature 5](racetime-room-lifecycle.md) racetime
   subsystem rather than a separate integration.

## Workflow surface: web-first, decided

SahasrahBot's async flow is Discord-thread-driven (slash command → private thread
→ buttons). Wizzrobe drops that entirely: players start runs, submit times/VoDs, and
view leaderboards on tenant web pages; Discord is notification-only (existing DM
queue — "window open," "run reviewed," etc.), not an execution surface. This isn't
just a port shortcut — a web run page can show live elapsed time, inline VoD
upload/embed, richer pool/leaderboard browsing, and a proper reviewer queue UI,
none of which Discord's thread+button model does well. `thread_id` is dropped from
`AsyncQualifierRun` (no replacement field — there is no thread). If a lightweight
Discord entry point (e.g. "start my run" deep-linking into the web page) proves
worth adding later, it goes through `discordbot/` calling the same
`AsyncQualifierService` — but it is not part of this plan.

## Model mapping (SahasrahBot → Wizzrobe)

All new models are tenant-scoped (`tenant` FK NOT NULL, CASCADE, scoped repos,
leak test) per [multitenancy.md](../features/multitenancy.md).

| SahasrahBot | Wizzrobe | Adaptation |
|---|---|---|
| `AsyncTournament` (guild/channel ids, owner, `allowed_reattempts`, `runs_per_pool`, `customization`) | `AsyncQualifier` | Discord channel wiring → tenant + web UI; `customization` → schema-validated config per the [design principle](README.md#design-principle-user-definable-tournament-logic); standalone peer of `Tournament` (no structural FK — at most an informational label for the event it feeds) |
| `AsyncTournamentPermalinkPool` (name, preset) | `AsyncQualifierPool` | `preset` becomes FK → the new `Preset` model ([Feature 2](seed-rolling.md)) |
| `AsyncTournamentPermalink` (url, notes, `live_race`, `par_time`) | `AsyncQualifierPermalink` | as-is |
| `AsyncTournamentRace` (status, review_status, start/end, `thread_id`, `runner_vod_url`, score) | `AsyncQualifierRun` | **`thread_id` dropped** (no Discord thread — execution is the web run page); Discord DM notifies on state changes instead; statuses kept: `pending/in_progress/finished/forfeit/disqualified`, review `pending/approved/rejected` |
| `AsyncTournamentLiveRace` (`racetime_slug`, `episode_id`, status) | `AsyncQualifierLiveRace` | `episode_id` → FK to the SG-imported episode/match ([Feature 4](speedgaming-etl.md)) where applicable |
| `AsyncTournamentReviewNotes` | `AsyncQualifierReviewNote` | as-is |
| `AsyncTournamentWhitelist` / `AsyncTournamentPermissions` | eligibility + reviewer config on `AsyncQualifier` | **decided:** management gated by the new `QUALIFIER_ADMIN` role (or STAFF) + a per-qualifier `admins` M2M (like `Tournament.admins`); **reviewers = that `admins` M2M, with self-review blocked** (a reviewer cannot approve/reject their own run) |
| `AsyncTournamentAuditLog` | **not ported** | Wizzrobe's `AuditService` + new `AuditActions`/`EventType` members (`async_qualifier.run_submitted`, `.run_reviewed`, …) |

## Data model

Tenant-scoped: `AsyncQualifier`, `AsyncQualifierPool`, `AsyncQualifierPermalink`,
`AsyncQualifierRun`, `AsyncQualifierLiveRace`, `AsyncQualifierReviewNote`, plus a
per-qualifier `admins` M2M. `AsyncQualifier` carries typed **window columns**
(`opens_at`/`closes_at`) + `runs_per_pool` + `allowed_reattempts` and a
validated-JSON `config` blob for scoring/reattempt/messaging (the hybrid config
decision); `AsyncQualifierRun` carries `reattempted` + `reattempt_reason` (the
one-attempt integrity backstop). New enums: run status
(`pending/in_progress/finished/forfeit/disqualified`) and review status
(`pending/approved/rejected`). Depends on `Preset`
([Feature 2](seed-rolling.md)) for pool presets and, for live races, on
`User.racetime_*` + the racetime subsystem ([Feature 5](racetime-room-lifecycle.md)).

## Roadmap

- **Phase 7** — core: models, web run-execution pages (draw permalink, timer,
  submit time/VoD), reviewer queue, par scoring, leaderboard. Discord DM
  notifications only.
- **Phase 8** — live races: reuse the [Feature 5](racetime-room-lifecycle.md)
  racetime subsystem for a room per live race, capturing results into runs.

(Full ordering across all features: [roadmap](README.md#phased-roadmap).)

## Feature-specific risks

- **Async run integrity.** Permalinks revealed only at run start; one attempt
  enforced server-side (reattempts only per config); VoD + review flow is the
  anti-cheat backstop. Port these semantics faithfully — they are the feature.

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks
(single-worker load, config/code boundary, succession discipline).
