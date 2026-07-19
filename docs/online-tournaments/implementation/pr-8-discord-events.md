# PR 8 — Discord Events sync

> Feature 3. Roadmap phase 6. Reconciles Wizzrobe schedule data into Discord Scheduled
> Events. **Shared-guild safety is the sharp edge** (post PR #85/#86 on `main`).

**Goal:** each tenant's schedule is mirrored to Discord Scheduled Events in its
linked guild, idempotently, without ever touching another tenant's events.

**Depends on:** PR 7 (soft — for SG-imported matches; native matches work without
it). **Unblocks:** nothing.

## Deliverables

- **`DiscordScheduledEvent`** link model (tenant-scoped): `guild_id`,
  `discord_event_id`, source type + id (polymorphic — needs a source-type enum),
  `synced_at`, content hash. **Uniqueness**: `unique (discord_event_id)` + a
  composite on `(tenant, source_type, source_id)` for idempotency
  ([gap discord-scheduled-event-polymorphic](../gap-analysis.md)). Migration + leak
  test.
- **Reconciler worker** under `tenant_scope`, through the one-bot-many-guilds
  singleton: create/update/cancel Discord events to match the schedule (native
  `Match` + SG-imported + qualifier windows/live races once those exist). Content
  hash drives update-vs-noop. Per-tenant opt-in; templated titles/descriptions via
  config.
- **Shared-guild safety** ([reconciliation](../discord-events-sync.md#shared-guilds-reconciled-with-main)):
  the working set is **this tenant's own `DiscordScheduledEvent` rows only** — never
  "all events in the guild." A `discord_event_id` in the guild but absent from this
  tenant's link table belongs to a sibling tenant; **do not cancel it.** The target
  guild is the verified `Tenant.discord_guild_id`.
- Rate-limit-aware batching. `discord_event.*` audit/events.

## Decisions that apply

Idempotent reconciliation keyed on the tenant's own link rows; shared-guild
never-cancel-siblings; verified `Tenant.discord_guild_id`.

## Reference implementations

- **sahabot2**: `Tournament.create_scheduled_events` / `scheduled_events_enabled` /
  `discord_event_filter` (`DiscordEventFilter` enum) / `event_duration_minutes` +
  `discord_event_guilds` M2M in `models/match_schedule.py`; its scheduled-events
  service.
- **wizzrobe**: `application/services/discord_link_service.py` +
  [multitenancy.md](../../features/multitenancy.md) "Discord: one bot, many guilds"
  (fan-out + `DiscordRoleMapping.tenant` isolation — mirror that isolation here),
  `discordbot/` handlers, the volunteer-reminder loop as a worker precedent.

## Acceptance criteria

- With two tenants sharing one guild, each syncs its own matches to Discord events;
  cancelling a match in tenant A removes only A's event and leaves B's intact
  (regression test this explicitly). Verify via `ui-validation` + a shared-guild test.

## Out of scope

Any change to the Discord role-sync / linking flow (owned by `main`).
