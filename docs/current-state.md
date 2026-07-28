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
| **Match operations** | scheduling and lifecycle, stream-room assignment, player dashboard, acknowledgment, watching, crew signup + approval, player availability, match suggestions | [match-participation](features/match-participation.md) |
| **Tournaments** | tournaments, enrollment, per-tournament admins and crew coordinators, triforce texts, notification preferences | [triforce-texts](features/triforce-texts.md) |
| **Brackets** | single/double elimination, Swiss, round robin, multi-stage chains, best-of-N series, public bracket views. **Behind `FeatureFlag.BRACKETS` — ships dark** | [brackets](features/brackets.md) |
| **Online tournaments** | user-managed seed presets, racetime.gg room lifecycle + bot runtime, async qualifiers (incl. live races), SpeedGaming schedule ETL, Discord Events sync, per-tenant randomizer credentials | [online-tournaments](features/online-tournaments.md), [seed-generation](reference/seed-generation.md) |
| **Volunteering** | opt-in, positions, shifts, assignments, availability, auto-scheduler, reminders, coordinator data export | [services](reference/services.md) |
| **Equipment** | assets, checkout/check-in, loan history, QR codes | [services](reference/services.md) |
| **Platform** | multitenancy (`/t/<slug>` + custom domains), per-tenant feature flags, `/platform` super-admin surface, service-health board | [multitenancy](features/multitenancy.md), [feature-flags](features/feature-flags.md) |
| **Identity & access** | Discord OAuth, eleven roles, guild-role sync, Challonge/Twitch/racetime identity linking | [roles](reference/authentication.md#roles), [authentication](reference/authentication.md) |
| **Integrations** | REST API + personal access tokens, MCP server at `/mcp`, event bus, signed outbound webhooks, web push, Challonge | [rest-api](reference/rest-api.md), [mcp-server](features/mcp-server.md), [webhooks](features/webhooks.md) |
| **Observability** | audit logging, engagement telemetry, analytics/insights reports, in-app feedback, Sentry | [audit-logging](features/audit-logging.md), [telemetry](features/telemetry.md), [admin-reports](features/admin-reports.md) |

## Known issues

- **~22 hand-rolled `write_log` + `event_bus.publish` pairs** remain unconverted to `AuditService.write_and_publish`. Left deliberately: 17 test files stub `write_log` and assert on its call args, so converting churns assertions across all 17 for a pure-DRY win on correct code. `check_dry_regressions.py` blocks *new* pairs, so the backlog can be worked file-by-file.
- **All mobile and dark-mode verification is emulated** (Playwright at 390×844 / 360×800 via `/ui-validation`); no physical-device pass has run. Specifically unverified on real hardware: the NiceGUI WebSocket lifecycle across screen lock / backgrounding / resume, and the native `type=date` / `type=time` pickers.
- **Report filter changes trigger a full page reload** — `navigate_with_params` (`pages/admin_tabs/reports/shared.py`) calls `ui.navigate.to`, and all eight report pages route their filter handlers through it. Deferred: the fix means wrapping six report bodies in `@ui.refreshable` and swapping to `history.replace`, and the reward is modest against the regression risk on an admin-only surface that works.

## Deliberately deferred

Recorded so they read as decisions rather than gaps:

- **Bracket automation stops at Challonge parity.** Humans schedule open matchups into `Match` rows. Auto-created matches, full round auto-scheduling, and bracket-driven crew/restream assignment were all left out of v1.
- **No persisted `MatchState` column.** State stays derived from the five nullable timestamps via `match/match_status.py`. Worth revisiting only when the schedule needs to *filter* by state at scale — a stored column becomes a second source of truth needing reconciliation.
- **Bracket fullscreen / venue mode** — a toggle expanding the bracket at larger scale for projectors and stream layouts. Groundwork exists (the toolbar reserves space; the renderer themes through `--bracket-*` variables); no model or data change needed.
- **Team entrants and ladder formats.** The nullable-user `BracketEntrant` indirection is the prepared hook for teams; `openskill` is the noted candidate for rating-based formats.
- **Challonge retirement is an open decision**, not inertia — the integration stays until native brackets are proven in production.
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

All datetimes stored UTC, displayed US/Eastern ([timezone-handling](timezone-handling.md)).
Full process model and directory map: [architecture](architecture.md).
Capacity and the single-worker constraint: [scaling-roadmap](scaling-roadmap.md).

## Testing

`poetry run pytest` — the whole suite, parallel, no PostgreSQL or Discord needed.
Line coverage sits around 92% across `application/`, `api/` and `middleware/`.
Deliberately uncovered (each needs live infra): the Discord bot handlers, NiceGUI
rendering, the OAuth flow, and the network-backed clients. See
[development](development.md).
