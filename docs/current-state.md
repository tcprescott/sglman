# Current State

Living status snapshot. Feature *behaviour* is documented in
[docs/features/](README.md#feature-reference-docsfeatures); this page is only what
works, what is deliberately unfinished, and what is known-broken. Start at the
[documentation index](README.md).

The application is in active use. The three-layer refactor is complete, and every
feature below is merged to `main`.

## Feature status

Everything listed is **stable in production** unless marked otherwise.

| Area | Features | Docs |
|---|---|---|
| **Match operations** | scheduling and lifecycle, capability-shaped boards (`MatchBoardAccess`), stage assignment with its own DMs and a pre-match reminder worker, player dashboard, acknowledgment, watching, crew signup + approval + coverage, the volunteer's own My Crew, per-tournament crew requirement, player availability, match suggestions, player reschedule/cancellation requests | [match-participation](features/match-participation.md) |
| **Tournaments** | tournaments, player self-service signup (own Home tab, per-tournament signup window, confirmation DM), staff-side enrollment, per-tournament admins and crew coordinators, triforce texts, notification preferences | [triforce-texts](features/triforce-texts.md) |
| **Prize payouts** | prize pool + bonus per tournament, placement splits with joint placings, amounts computed from the pool at read time, Matcherino handles on the profile, a copy-ready payout block, REST + an MCP read tool. **Behind `FeatureFlag.PAYOUTS` — ships dark** | [payouts](features/payouts.md) |
| **Brackets** | single/double elimination, Swiss, round robin, multi-stage chains, best-of-N series, draw preview before start, standings + staff tie-breaks, stage cancellation, public bracket views + static cached spectator views (`/live/…`, no websocket). **Behind `FeatureFlag.BRACKETS` — ships dark** | [brackets](features/brackets.md) |
| **Online tournaments** | user-managed seed presets, racetime.gg room lifecycle + bot runtime, async qualifiers (incl. live races), SpeedGaming schedule ETL, Discord Events sync, per-tenant randomizer credentials | [online-tournaments](features/online-tournaments.md), [seed-generation](reference/seed-generation.md) |
| **Volunteering** | opt-in, positions, shifts, assignments, availability, auto-scheduler, reminders, coordinator data export, hours served against per-tenant comp tiers | [services](reference/services.md) |
| **Equipment** | assets, checkout/check-in, loan history, QR codes | [services](reference/services.md) |
| **Platform** | multitenancy (`/t/<slug>` + custom domains), the membership gate + self-serve join requests, per-tenant feature flags, `/platform` super-admin surface (incl. the first-admin grant and a setup-readiness column), the derived new-community setup checklist, service-health board | [multitenancy](features/multitenancy.md), [feature-flags](features/feature-flags.md) |
| **Identity & access** | Discord OAuth, eleven roles, guild-role sync, Challonge/Twitch/racetime identity linking | [roles](reference/authentication.md#roles), [authentication](reference/authentication.md) |
| **Integrations** | REST API + personal access tokens, MCP server at `/mcp` (reads for every connection, match writes for one whose consent screen approved them), event bus, signed outbound webhooks, web push, Challonge | [rest-api](reference/rest-api.md), [mcp-server](features/mcp-server.md), [webhooks](features/webhooks.md) |
| **Help** | public `/help` section (ten articles, search, anchored nav) for players, crew, volunteers and proctors, plus tappable help icons on the surfaces they explain; **app mechanics only** since the room procedure moved to Event Information; content is in-repo Markdown parsed to a closed block model, never `ui.markdown` | [help](features/help.md) |
| **Event Information** | public `/event-info` — one community's own event handbook (what's on, attending the day, who to ask, plus role-gated floor procedure for the people running a room). Behind `FeatureFlag.EVENT_INFO`, **ships dark**; content is per-tenant in-repo Markdown through the same closed block model, and is intended to become database-backed and staff-editable | [event-information](features/event-information.md) |
| **Observability** | audit logging, engagement telemetry, analytics/insights reports, in-app feedback (reversible review + the submitter's own status list; behind `FeatureFlag.FEEDBACK`), Sentry | [audit-logging](features/audit-logging.md), [telemetry](features/telemetry.md), [admin-reports](features/admin-reports.md) |

## Known issues

- **Three hand-rolled `write_log` + `event_bus.publish` pairs remain**, each for a
  reason converting would break (see [event-system](features/event-system.md#the-three-remaining-hand-rolled-pairs)):
  `CrewService.set_approval` and `CrewService.acknowledge` audit *inside* an
  `in_transaction()` block while publishing outside it, and
  `VolunteerScheduleService.assign` audits unconditionally but publishes only for
  a non-draft assignment. The other 20 were converted; the test-shape problem that
  had blocked them is fixed by `tests.factories.make_audit_double`, whose
  `write_and_publish` runs its real body against a mocked `write_log`, so a
  converted service still publishes under test.
- **All mobile and dark-mode verification is emulated** (Playwright at 390×844 / 360×800 via `/ui-validation`); no physical-device pass has run. Specifically unverified on real hardware: the NiceGUI WebSocket lifecycle across screen lock / backgrounding / resume, and the native `type=date` / `type=time` pickers.
- **Report filter changes trigger a full page reload** — `navigate_with_params` (`pages/admin_tabs/reports/shared.py`) calls `ui.navigate.to`, and all eight report pages route their filter handlers through it. Deferred: the fix means wrapping six report bodies in `@ui.refreshable` and swapping to `history.replace`, and the reward is modest against the regression risk on an admin-only surface that works. Measured (dev box, seeded `default`, one date-filter change instrumented from the change event to the row set rendering): **~1.2 s on crew and ~1.4 s on telemetry, one frame navigation, 29 HTTP requests.** It no longer costs the operator their place: `static/js/report-nav.js` records the scroll position per report and restores it on the next render of the same one (before: `scrollY 600 → 0` on both).

## Deliberately deferred

Recorded so they read as decisions rather than gaps:

- **In-app help covers the non-staff surfaces only.** The nine `/help` articles
  are written for players, crew, volunteers and proctors; staff actions appear
  only from the outside ("staff approve your signup"). Admin → Schedule and every
  admin tab have no article and no help icons — a deliberate scope call, not an
  oversight. One visible edge: the result dialog's *Flag for admin review* help
  icon hangs off the `VOLUNTEERS`-gated proctor article, so a staff member
  recording a result in a community with volunteers off sees the checkbox with no
  help beside it. Adding a staff track fixes that and means new articles plus a
  second set of icons; the parser, the page and the gating all already carry it.
- **The event handbook encodes room procedure, and nothing checks it.** Who runs
  the countdown, escalating a no-show, not touching a mid-match hardware failure
  before an admin rules on it — none of that is in the code, so no test can catch
  it drifting from how events actually run. It needs a human re-read when
  procedure changes. Moving it out of `/help` and into `/event-info` at least
  puts it where it is one community's to own and revise.
- **The SGL handbook ships with `TODO:` callouts, and one of them matters.** The
  articles are written from sglive.speedgaming.org (read 2026-08-01) — dates,
  venue, room block, ticket tiers, both tournament lists, the volunteer form and
  its badge-comp tiers, the lanyard convention, Discord and Twitch. What is left
  is genuinely unpublished: the daily agenda, per-tournament formats, badge
  collection, room locations, a **board game room for attendees**, and **a code
  of conduct — neither the event site nor speedgaming.org publishes one**. Prize-pool figures are a community-funded
  snapshot and will drift. The `event_info` flag is dark, so nothing reaches a
  reader until the gaps and the grant are done.
- **Event Information is file-backed, and meant not to stay that way.** Content is
  per-tenant Markdown in the repo, so a change needs a PR and a deploy. Everything
  above `application/event_info/catalog.py` — the flag, routes, page, nav, tests —
  already goes through `EventInfoService` and knows nothing about files, so making
  it database-backed and staff-editable is that one module plus an editor.
- **The `System` service account is still offered as a person** wherever a picker is not membership-scoped. `UserRepository.get_community_people` excludes it, which covers every per-community picker; the platform-level `get_all_users` does not, because a super-admin's first-admin picker is choosing from every account (the checkout dialog, its other caller, re-applies the exclusion in Python). A general "service account" concept was out of scope.
- **A brand-new community still shows the full admin drawer.** The setup checklist supplies the ordering the audit found missing, and nothing hides the other tabs — hiding tabs from a staff member who knows what they want is a worse failure than showing too many.

- **`Tournament.staff_administered` is a removal candidate, and now has no reader at all.** It was only ever a cosmetic split of the profile page's tournament lists; that card and the `UserService` helper behind it are gone with the Tournaments tab, and the new tab groups by signup state instead. Real tournaments are operated the same way whether or not it is set, and in practice it is not set. The column and the edit-dialog toggle can go together — no dev fixture is built on it, deliberately (see [dev-seed](reference/dev-seed.md)).
- **Team events are not modelled.** `Tournament.team_size` is stored and editable, but nothing reads it: there is no team membership, no team-aware pairing, and no team result. Communities that run team events track them outside Wizzrobe. The nullable-user `BracketEntrant` indirection is the prepared hook if that changes; until then the seed deliberately leaves `team_size` at its default rather than implying semantics that do not exist.
- **Bracket automation stops at Challonge parity.** Humans schedule open matchups into `Match` rows. Auto-created matches, full round auto-scheduling, and bracket-driven crew/restream assignment were all left out of v1.
- **No persisted `MatchState` column.** State stays derived from the five nullable timestamps via `match/match_status.py`. Worth revisiting only when the schedule needs to *filter* by state at scale — a stored column becomes a second source of truth needing reconciliation.
- **Bracket fullscreen / venue mode** — a toggle expanding the bracket at larger scale for projectors and stream layouts. Groundwork exists (the toolbar reserves space; the renderer themes through `--bracket-*` variables); no model or data change needed.
- **Team entrants and ladder formats.** The nullable-user `BracketEntrant` indirection is the prepared hook for teams; `openskill` is the noted candidate for rating-based formats.
- **Challonge retirement is an open decision**, not inertia — the integration stays until native brackets are proven in production. The migration path exists either way: `ChallongeService.unlink_tournament` (**Unlink** on the Challonge tab) detaches a tournament and drops its mirror, which is what makes it eligible for a native bracket.
- **Notification centralization, phase 2.** The event bus is additive: services publish domain events for webhooks, but Discord DM fan-out still runs directly through `discord_queue`. Migrating it would let one `publish` drive all channels, but the fan-out is deeply audience-specific (players/crew/watchers/subscribers, different button variants). See [event-system](features/event-system.md).

## Architecture at a glance

```
pages/ + theme/           ← NiceGUI UI (Quasar)
  ↓
application/services/     ← business rules, validation, audit, notifications
  ↓
application/repositories/ ← ORM queries (Tortoise), tenant scoping
  ↓
models/                   ← Tortoise models + enums, per-domain submodules
```

All datetimes stored UTC, displayed on a per-request local clock — a community either pins one zone or follows each viewer ([timezone-handling](timezone-handling.md)).
Full process model and directory map: [architecture](architecture.md).
Capacity and the single-worker constraint: [scaling-roadmap](scaling-roadmap.md).

## Testing

`poetry run pytest` — the whole suite, parallel, no PostgreSQL or Discord needed.
Line coverage sits around 92% across `application/`, `api/` and `middleware/`.
Deliberately uncovered (each needs live infra): the Discord bot handlers, NiceGUI
rendering, the OAuth flow, and the network-backed clients. See
[development](development.md).

Four checks run alongside it in CI, each covering something the suite cannot:

| Check | What it catches |
|---|---|
| `scripts/guardrails.py` | the `.claude/scripts/` invariants — layer boundaries, tenant scoping, async/datetime safety, feature-flag gating — on **every** commit, not only ones a Claude session wrote |
| `scripts/mypy_ratchet.py` | a file *gaining* type errors, against a per-file baseline (blocking; the ~1420 existing ones are mostly ORM shapes mypy cannot resolve) |
| `tests/test_query_budget.py` | queries-per-render growing with row count (an N+1) or past a ceiling (a duplicate load) |
| the `postgres` job | what SQLite silently no-ops — row locks above all — over `tests/postgres/` and `tests/tenancy/` |
