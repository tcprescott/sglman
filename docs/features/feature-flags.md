# Feature Flags

Per-tenant feature flags let a community turn whole subsystems on or off. A flag
exists **only** for a deliberately-gated feature — this is not a switch for every
feature in the app. Availability is driven by a **live group (tier)** with a
per-tenant override on top, and the community controls enablement.

- **Registry (code):** [`application/feature_flags.py`](../../application/feature_flags.py) — one `FeatureFlagSpec` per flag (label, description, category, `established`). Enum keys live in [`models.enums.FeatureFlag`](../../models/enums.py).
- **Group (tier):** [`FeatureFlagGroup`](../../models/feature_flag.py) — a global, super-admin-defined bundle of flags (`name`, `flags`, `is_default`). A tenant points at one via `Tenant.feature_group`.
- **Override:** [`TenantFeatureFlag`](../../models/feature_flag.py) — one row per `(tenant, flag)`; `available`/`enabled` are **tri-state** (NULL = inherit, True/False = explicit).
- **Service / repos:** [`FeatureFlagService`](../../application/services/feature_flag_service.py), [`TenantFeatureFlagRepository`](../../application/repositories/feature_flag_repository.py), [`FeatureFlagGroupRepository`](../../application/repositories/feature_flag_group_repository.py).

## Resolving `available` and `enabled`

Availability is resolved live, override → group → default group:

1. **Group (tier).** A super-admin defines named `FeatureFlagGroup` bundles on `/platform` and assigns each tenant to one; a tenant's available flags derive from its group **live** — editing the group updates every tenant on it. A tenant with **no** group falls back to the single `is_default` group.
2. **Per-tenant override.** A super-admin may force one flag on/off for one tenant (the tri-state `available` column); the explicit override wins over the group.
3. **Enable tier.** Whenever a flag is available it is **ON by default**; the community's STAFF may switch it off — a sticky per-tenant choice (the tri-state `enabled` column).

```
effective_available = override.available if set, else (flag ∈ tenant-group ∪ default-group)
effective_enabled   = override.enabled if set, else True when available
is_enabled          = effective_available AND effective_enabled   ← what every gate reads
```

`is_enabled` returns `False` when there is no tenant in scope (the platform
surface) rather than raising. A `TenantFeatureFlag` row left with both columns
NULL carries no information and is deleted, so an override never lingers as a
no-op. Deleting a group reassigns its tenants to ungrouped (→ default fallback);
`is_default` is single (setting one clears the rest).

| Tier | Who | Controls | Where |
|---|---|---|---|
| Group / tier | Super-admin | which features a tenant's group offers (live) | `/platform` → **Feature Groups** + a tenant's **Features** button |
| Availability override | Super-admin | force one flag on/off for one tenant | `/platform` → tenant **Features** → Inherit / Force-on / Force-off |
| Enablement | Tenant STAFF | whether each available feature is on | Admin → **Features** tab |

## Where gating is enforced

Feature availability is an **authorization-style gate at the entry surfaces**
(like `@protected_page` and the API auth deps), not a business rule buried in a
service transaction — so a service method never does a feature-flag DB read.

| Surface | How |
|---|---|
| Whole pages | `@protected_page('/path', feature=FeatureFlag.X)` → 404 when off (hidden, role-independent). Used by `/qualifiers`, `/equipment`, `/volunteer`. |
| Admin tabs | `pages/admin.py` loads `FeatureFlagService().enabled_flags()` once and `and`-s the flag into each subsystem tab's condition. |
| Home tabs | `pages/home.py` gates the Triforce Texts and Equipment tabs (My Availability stays ungated — it feeds crew signup too). |
| REST API | `api/__init__.py` attaches `require_feature(FeatureFlag.X)` to each gated router's `include_router`; a disabled feature 404s. |
| Auto workers | The racetime auto-open and SpeedGaming sync workers skip a tenant whose flag is off (a clean `is_enabled` check inside `tenant_scope`). |
| A value within a shared control | When the gated thing is one *option* in a shared select rather than a whole page/router (e.g. the `dk64r` seed generator), the gate is a **per-value filter at each selection surface** plus an **explicit flag check at each action boundary**. `dk64r` filters via `SeedGenerationService.available_randomizers(live_flags)` and re-checks at every roll (see [seed-generation.md](../reference/seed-generation.md#flag-gated-randomizers)). The roll check is the sanctioned service-layer flag read — it sits at the roll's authorization boundary, not inside a low-level transaction. |

The admin **Features** tab itself is only role-gated (STAFF), never flag-gated —
it is the control panel.

### API-key randomizers are always flag-gated

A convention worth stating explicitly: **any seed randomizer whose upstream
requires an API key to generate is gated behind a per-tenant feature flag.** The
key's owner attaches usage restrictions the community must agree to, and a
super-admin's availability grant is how the platform records that a given tenant
is authorized (and has agreed) to use it — an authorization gate, not a beta
toggle. `dk64_randomizer` (api.dk64rando.com, `DK64R_API_KEY`) is the first; new
keyed backends follow the same rule rather than each being decided ad hoc.

## The current flags

| Flag | Category | Established? | Gated surfaces |
|---|---|---|---|
| `async_qualifiers` | Online tournaments | no (ships dark) | `/qualifiers`, admin Qualifiers tab, `/async-qualifiers*` API |
| `racetime_rooms` | Online tournaments | no | admin Racetime tab, race-room + profile API, auto-open worker |
| `speedgaming_etl` | Online tournaments | no | admin SpeedGaming tab, `/speedgaming` API, sync worker |
| `dk64_randomizer` | Online tournaments | no | the `dk64r` seed generator: selector filter (tournament dialog, Presets tab, `/seeds/randomizers`) + every roll boundary (match roll, `POST /seeds`, qualifier pool roll) |
| `brackets` | Online tournaments | no (ships dark) | admin Brackets tab, public bracket pages (`/tournament/{id}/brackets`, `/brackets/{id}`), `/brackets` API |
| `challonge` | Community | **yes** | admin Challonge tab |
| `equipment` | Community | **yes** | `/equipment`, home + admin Equipment tabs |
| `volunteers` | Community | **yes** | `/volunteer`, admin Vol. Roster/Schedule, `/volunteers` API |
| `triforce_texts` | Community | **yes** | home + admin Triforce tabs, `/triforce-texts` API |

`established=True` marks a feature that was **already in live use** when its flag
was added. [Migration 30](../../migrations/models/30_20260715000000_feature_flags.py)
pinned those flags `available+enabled` for every existing tenant so gating them
didn't make them vanish; new/unreleased features (the four online ones) ship
dark.

## Groups (tiers)

[Migration 31](../../migrations/models/31_20260715120000_feature_flag_groups.py)
adds the group layer on top: `FeatureFlagGroup` + `Tenant.feature_group`, makes
`TenantFeatureFlag.available/enabled` nullable (tri-state), and seeds an **empty**
`Default` group plus an `Online Tournaments` group. The migration is
non-destructive — the migration-30 pins stay in place as per-tenant overrides, so
existing communities keep their features; you migrate them onto groups at your
pace via `/platform`.

Super-admins manage groups on `/platform` → **Feature Groups** (create/edit/
delete, mark one default, pick its flags) and assign a tenant to a group from its
**Features** button. Because availability derives from the group **live**, editing
a group re-tiers every tenant on it in one edit. `FeatureFlagService` owns the
group CRUD, the `assign_tenant_group` write, and the effective-state resolution.

## Adding a feature flag

Only gate a feature behind a flag when it warrants one — **always ask the user
first** (see CLAUDE.md). When you do:

1. Add a member to [`FeatureFlag`](../../models/enums.py) and a `FeatureFlagSpec`
   to [`application/feature_flags.py`](../../application/feature_flags.py). Set
   `established=True` **only** if the feature is already in live use (then add its
   key to the migration backfill so existing tenants keep it).
2. Gate the surfaces: `feature=` on the page's `@protected_page`; `and FeatureFlag.X in live` on its admin/home tab; `require_feature(FeatureFlag.X)` on its REST router; an `is_enabled` skip in any background worker that acts on it.
3. Seed it in [`scripts/seed_dev.py`](../../scripts/seed_dev.py) so the dev tenants exercise it.
4. Add coverage to [`tests/test_feature_flags.py`](../../tests/test_feature_flags.py); if the feature has a gated REST router, provision the flag for any second tenant an isolation test creates (`enable_all_features` in `tests/api_helpers.py`).

## Testing

The `db` fixture provisions the default tenant (id 1) with every flag fully on
(explicit `available+enabled` override rows), so the legacy suite exercises
features as before regardless of groups. New tenants start off (the production
default); a test that spins up a second tenant to hit a gated router must call
`enable_all_features(tenant_id)`. See
[`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) for the
effective-state resolution, override precedence, live group derivation, default
fallback, single-default, deletion-reassign, and isolation coverage.
