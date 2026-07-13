# Feature 4: SpeedGaming schedule ETL

> Part of the [Online Tournaments plan](README.md) (proposed, not implemented).
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).

SahasrahBot treats speedgaming.org as a live dependency — every relevant
interaction queries the SG API and joins on `episode_id` (`TournamentGames`,
`TournamentResults`, `ScheduledEvents` all key on it; there is no local episode
store). **SGLMan inverts this: an ETL process synchronizes SG data into SGLMan's
own tables**, making SG an upstream feed rather than a runtime dependency.

Source: SahasrahBot's direct SG API queries keyed on `episode_id` throughout.

## Extract / Transform / Load

- **Extract** — poll the SG schedule API per configured event slug on a cadence
  (background worker, `tenant_scope`, honoring SG rate limits).
- **Transform** — normalize episodes to SGLMan's shape: UTC datetimes,
  crew/channel metadata mapped to SGLMan concepts, and players resolved to `User`
  by the **placeholder-user pattern (decided, from sahabot2)**:
  - Resolution order: existing `User` by `discord_id` → by `discord_username`
    (from SG `discord_tag`) → existing placeholder by `speedgaming_id` → **create a
    placeholder `User`** (`discord_id=NULL`, `discord_username="sg_{sgid}"`,
    `is_placeholder=True`, `speedgaming_id` set).
  - This keeps `MatchPlayers.user` **NOT NULL** — an unresolved SG player is still a
    first-class `User` (enrollable, assignable crew, shows on the roster), just
    flagged placeholder. It requires `User.discord_id` become nullable+unique with
    `CHECK (discord_id IS NOT NULL OR is_placeholder)`, plus `is_placeholder` and
    `speedgaming_id` columns.
  - **Upgrade in place**: when a later sync (or a real login) supplies a
    `discord_id`, the placeholder is promoted to a full `User` (or deferred to an
    existing real `User` with that `discord_id`).
- **Load** — upsert into a tenant-scoped staging model `SpeedGamingEpisode` (unique
  `(tenant, sg_episode_id)`, payload snapshot + content hash, `synced_at`, nullable
  FK → `Match`), then materialize/refresh linked `Match` rows.

## Reconciliation contract — decided, not just directional

Sync is strictly **one-way, SG → SGLMan**; nothing SGLMan does ever writes back to
SpeedGaming. For a `Match` created by the ETL, **the fields the ETL populates are
read-only in SGLMan** — staff cannot hand-edit them; the next sync is the only
thing that can change them. Everything SGLMan adds on top stays fully staff-editable
and is never touched by sync:

| ETL-owned (read-only in SGLMan) | SGLMan-owned (editable, sync never touches) |
|---|---|
| `scheduled_at`, enrolled players (`MatchPlayers` rows sourced from SG), `title`, tournament linkage | `generated_seed`, `stream_room`, `Commentator`/`Tracker` crew, `MatchAcknowledgment`, `MatchWatcher`, station assignments, `seated_at`/`started_at`/`finished_at`/`confirmed_at`, `comment`, Discord event links |

**Enforcement = hybrid, two guards (decided).** The plan combines strict per-field
locking with sahabot2's proven lifecycle guards:

1. **Per-field read-only (UI + service).** `Match` carries a source marker (its FK
   to `SpeedGamingEpisode`, non-null = SG-sourced). `MatchService.update_match`
   rejects writes to ETL-owned fields on a sourced match (`ValueError`, same pattern
   as every other service-layer validation); the presentation layer disables those
   form fields with a "Synced from SpeedGaming" badge.
2. **Lifecycle guards on the sync side (from sahabot2, which ran this in production).**
   Re-sync **skips** a match that is finished, has any manual status set
   (`checked_in`/`started`/`finished`/`confirmed`), or has a linked `RacetimeRoom`;
   and **auto-finishes** matches more than ~4h past their scheduled time (unless a
   room is linked). This protects race-day work even on fields the ETL nominally owns.

A cancelled upstream episode **soft-detaches** — the `Match` row and everything
SGLMan added survive; the ETL-owned fields freeze at their last synced value.

A `SpeedGamingEventLink` (tournament ↔ SG event slug + sync settings) configures
which SG events feed which tenant tournaments.

## Why ETL over direct queries

SG outages don't break race-day operations, data is queryable/joinable locally
(reports, [Discord events](discord-events-sync.md), crew flows all just work on
`Match`), and the sync is observable (last-synced, diffs, errors surfaced in the
admin UI + audit log). The read-only boundary also means staff can never "fix" a
Match locally in a way the next sync silently reverts — today's biggest source of
ETL confusion in systems like this.

## Data model

Tenant-scoped: `SpeedGamingEpisode`, `SpeedGamingEventLink` (add observability
fields — `last_synced_at`, `last_status`, `last_error`, cadence, `active`). `Match`
gains its FK to `SpeedGamingEpisode` (the source marker; `on_delete=SET_NULL`) and
already carries `speedgaming_episode_id`-style linkage. Global `User` gains
`is_placeholder` + `speedgaming_id` and its `discord_id` becomes nullable+unique
with a `CHECK (discord_id IS NOT NULL OR is_placeholder)` constraint (the
placeholder pattern above). New `sync status` enum; `sg_sync.*` audit/event
members. The SG materializer runs as the reserved **system `User`**.

## Roadmap

- **Phase 5** — staging model, sync worker, read-only reconciliation contract,
  admin visibility. Independent of the racetime track; parallelizable with
  Phases 1–4.

(Full ordering across all features: [roadmap](README.md#phased-roadmap).)

## Feature-specific risks

- **Field-level read-only enforcement.** The one-way, per-field read-only contract
  above has to be enforced at the service layer, not just documented — a
  `MatchService.update_match` gap that lets an ETL-owned field slip through would
  get silently reverted on the next sync and look like a bug. New ETL-owned fields
  introduced later must be added to the guard, not just the transform.
- **Identity matching.** SG player → `User` needs the reconcile-later path (raw
  name kept, staff link later), not hard failure.

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks
(this worker contributes to the single-process background-worker load).
