# Feature 3: Discord Events sync

> Part of the [Online Tournaments design record](README.md) — **implemented**.
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).
>
> **Status: implemented (PR 8).** Tenant-scoped `DiscordScheduledEvent` link
> (polymorphic `source_type`/`source_id` via the `DiscordEventSource` enum,
> `discord_event_id` unique, content-hash reconciliation), per-tournament opt-in +
> templating columns on `Tournament`, `DiscordEventReconcilerService` (create /
> update / cancel scoped to the tenant's own rows — shared-guild sibling-safe), the
> `DiscordService` scheduled-event methods (`MOCK_DISCORD` fake), the
> `DISCORD_EVENTS_SYNC_ENABLED` worker, and the admin **Discord Events** tab.
> Migration 27. See [current-state.md](../current-state.md) and the data-model
> reference for the as-built shape.

SahasrahBot maps SG episodes to Discord **Scheduled Events** 1:1
(`ScheduledEvents`: `scheduled_event_id` PK, unique `episode_id`, `event_slug`).
Wizzrobe generalizes this into automatic sync of the tenant guild's scheduled events
from Wizzrobe schedule data.

Source: `ScheduledEvents` model (`episode_id` ↔ `scheduled_event_id`).

## Approach

- **Source of truth is Wizzrobe's schedule** — native `Match` rows (including
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
- The target guild is `Tenant.discord_guild_id`, established by the **verified**
  `DiscordLinkService` connect flow (`main`, PR #85/#86) — not a claimed id.

### Shared guilds (reconciled with `main`)

As of PR #85/#86, **`discord_guild_id` is no longer unique — several tenants may
share one Discord server.** That guild's Scheduled Events list can therefore hold
events owned by *sibling* tenants. So the reconciler's working set is **"the events
this tenant created," tracked via its own `DiscordScheduledEvent` rows** — never
"every scheduled event in the guild." Concretely: create/update/cancel only against
rows this tenant owns; a `discord_event_id` present in the guild but absent from
this tenant's link table belongs to someone else and is left untouched. This mirrors
how role-sync already isolates a shared guild by `DiscordRoleMapping.tenant`.

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
- **Never cancel a sibling tenant's event (shared guilds).** Since a guild can
  back several tenants, the reconciler must scope every create/update/**cancel** to
  its own `DiscordScheduledEvent` rows. A "cancel everything in the guild not in my
  schedule" implementation would delete another community's events — the sharpest
  edge this feature has post-PR #85/#86.
- **Discord rate limits.** Batch reconciliation and respect the shared Discord
  singleton's limits; a large schedule shift shouldn't hammer the API.

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks
(this worker contributes to the single-process background-worker load).
