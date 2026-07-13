# Feature 3: Discord Events sync

> Part of the [Online Tournaments plan](README.md) (proposed, not implemented).
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).

SahasrahBot maps SG episodes to Discord **Scheduled Events** 1:1
(`ScheduledEvents`: `scheduled_event_id` PK, unique `episode_id`, `event_slug`).
SGLMan generalizes this into automatic sync of the tenant guild's scheduled events
from SGLMan schedule data.

Source: `ScheduledEvents` model (`episode_id` ↔ `scheduled_event_id`).

## Approach

- **Source of truth is SGLMan's schedule** — native `Match` rows (including
  SG-imported ones, [Feature 4](speedgaming-etl.md)) and
  [Async Qualifier](async-qualifiers.md) windows/live races.
- A `DiscordScheduledEvent` link model (tenant-scoped): `guild_id`,
  `discord_event_id`, source type + id, `synced_at`, content hash — so sync is
  **idempotent reconciliation** (create/update/cancel to match the schedule), not
  fire-and-forget creation.
- Runs as a background worker under `tenant_scope`, through the existing
  one-bot-many-guilds Discord singleton; per-tenant opt-in and templated event
  titles/descriptions via the
  [user-definable config](README.md#design-principle-user-definable-tournament-logic).

## Data model

`DiscordScheduledEvent` (tenant-scoped link/reconciliation table). `discord_event.*`
audit/event members. No new enums.

## Roadmap

- **Phase 6** — consumes native + SG-imported schedule data; reconciliation worker
  + config. Depends on the schedule existing (native matches always; SG-imported
  matches once [Feature 4](speedgaming-etl.md) lands).

(Full ordering across all features: [roadmap](README.md#phased-roadmap).)

## Feature-specific risks

- **Reconciliation drift.** The content hash must capture everything that appears
  in the Discord event (title, time, description) so an upstream schedule change
  reliably updates or cancels the mirrored event rather than leaving a stale one.
  Deleted/rescheduled source rows must cancel or move their event, not orphan it.
- **Discord rate limits.** Batch reconciliation and respect the shared Discord
  singleton's limits; a large schedule shift shouldn't hammer the API.

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks
(this worker contributes to the single-process background-worker load).
