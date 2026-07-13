# PR 7 — SpeedGaming schedule ETL + placeholder users

> Feature 4. Roadmap phase 5. Independent of the racetime track — parallelizable.
> sahabot2 has a **working implementation of this**; port it faithfully.

**Goal:** synchronize SG episodes into SGLMan `Match` rows one-way, resolving players
via placeholder users, with the hybrid read-only contract.

**Depends on:** PR 0. **Unblocks:** PR 8 (Discord events consume SG-imported matches).

## Deliverables

- **Placeholder-user migration** ([decision](../README.md#decisions-log)):
  `User.discord_id` → nullable+unique with `CHECK (discord_id IS NOT NULL OR
  is_placeholder)`; add `is_placeholder` + `speedgaming_id`. **This changes a core
  model** — audit every `user.discord_id` / non-null assumption.
- **Models**: `SpeedGamingEpisode` (tenant-scoped: unique `(tenant, sg_episode_id)`,
  payload snapshot + content hash, `synced_at`, sync-status enum, FK → `Match`);
  `SpeedGamingEventLink` (tournament ↔ SG event slug + sync settings + observability
  fields: `last_synced_at`, `last_status`, `last_error`, cadence, `active`);
  `Match → SpeedGamingEpisode` source-marker FK (`SET_NULL`). Migrations + leak tests.
- **ETL service** (port from sahabot2): extract (windowed poll per event slug),
  transform (UTC, **placeholder-user resolution**: `discord_id` → `discord_username`
  → placeholder-by-`speedgaming_id` → create placeholder; **upgrade in place** when a
  `discord_id` appears), load (upsert episode → materialize/refresh `Match` +
  `MatchPlayers` + crew + stream channel).
- **Hybrid read-only contract** ([decision](../README.md#decisions-log)): (1)
  per-field lock — `MatchService.update_match` rejects edits to ETL-owned fields on a
  sourced match ([gap readonly-guard](../gap-analysis.md) — the guard belongs on the
  one edit path); UI disables them with a "Synced from SpeedGaming" badge. (2)
  lifecycle guards — re-sync **skips** finished / manually-progressed /
  racetime-room-linked matches; **auto-finish >4h** past. Soft-detach on upstream
  cancel.
- **Sync worker** under `tenant_scope`, acting as the **system user**; honor SG rate
  limits. Gated per tenant by `SYNC_ADMIN`. `sg_sync.*` audit/events.
- **Docs**: [speedgaming-etl.md](../speedgaming-etl.md).

## Decisions that apply

One-way sync; placeholder users; hybrid read-only; system-user actor; `SYNC_ADMIN`.

## Reference implementations

- **sahabot2** (port directly): `application/services/speedgaming/speedgaming_etl_service.py`
  (`_find_or_create_user`, `_sync_match_players`, `_sync_match_crew`,
  `import_episode`, `_detect_deleted_episodes` with auto-finish + racetime-room
  skip), `speedgaming_service.py` (SG API client, windowed fetch, `content_type`
  override), `models/user.py` (placeholder pattern + CHECK constraint),
  `models/match_schedule.py` (`Match.speedgaming_episode_id`).
- **sglman**: `application/services/match_service.py` (update_match guard point),
  `application/repositories/_tenant.py`.

## Acceptance criteria

- A configured SG event imports episodes into `Match` rows with players resolved
  (placeholder where unmatched); a re-sync updates a changed time but **skips** a
  finished match and one with a linked room; a staff edit to an ETL-owned field is
  rejected; an unmatched player becomes a real user when their `discord_id` appears.
  Verify against SG fixtures (mock the API).

## Out of scope

Discord scheduled events (PR 8); writing anything back to SG (never).
