# Feature Flags

Per-tenant feature flags let a community turn whole subsystems on or off. A flag
exists **only** for a deliberately-gated feature — this is not a switch for every
feature in the app. Flags are **disabled by default** and governed **two-tier**.

- **Registry (code):** [`application/feature_flags.py`](../../application/feature_flags.py) — one `FeatureFlagSpec` per flag (label, description, category, `established`). Enum keys live in [`models.enums.FeatureFlag`](../../models/enums.py).
- **State (per tenant):** [`TenantFeatureFlag`](../../models/feature_flag.py) — one row per `(tenant, flag)` with two booleans: `available` and `enabled`.
- **Service:** [`FeatureFlagService`](../../application/services/feature_flag_service.py).
- **Repository:** [`TenantFeatureFlagRepository`](../../application/repositories/feature_flag_repository.py).

## The two tiers

| Tier | Who | Controls | Where |
|---|---|---|---|
| Availability | Super-admin | `available` — is the feature *offered* to this tenant | `/platform` → a tenant's **Features** button |
| Enablement | Tenant STAFF | `enabled` — has the community *turned it on* | Admin → **Features** tab |

**A feature is live only when `available AND enabled`.** A missing row means both
are false — the disabled-by-default posture, so a new flag needs no per-tenant
backfill to be off everywhere. `is_enabled` is the single read every gate calls;
it returns `False` when there is no tenant in scope (e.g. the platform surface)
rather than raising. Revoking availability makes a feature go dark while
preserving the tenant's `enabled` choice, so re-granting restores it.

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

The admin **Features** tab itself is only role-gated (STAFF), never flag-gated —
it is the control panel.

## The current flags

| Flag | Category | Established? | Gated surfaces |
|---|---|---|---|
| `async_qualifiers` | Online tournaments | no (ships dark) | `/qualifiers`, admin Qualifiers tab, `/async-qualifiers*` API |
| `racetime_rooms` | Online tournaments | no | admin Racetime tab, race-room + profile API, auto-open worker |
| `speedgaming_etl` | Online tournaments | no | admin SpeedGaming tab, `/speedgaming` API, sync worker |
| `challonge` | Community | **yes** | admin Challonge tab |
| `equipment` | Community | **yes** | `/equipment`, home + admin Equipment tabs |
| `volunteers` | Community | **yes** | `/volunteer`, admin Vol. Roster/Schedule, `/volunteers` API |
| `triforce_texts` | Community | **yes** | home + admin Triforce tabs, `/triforce-texts` API |

`established=True` marks a feature that was **already in live use** when its flag
was added. The [migration](../../migrations/models/30_20260715000000_feature_flags.py)
backfills those flags as `available+enabled` for every existing tenant so gating
them doesn't make them vanish; new/unreleased features (the three online ones)
ship dark.

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

The `db` fixture provisions the default tenant (id 1) with every flag fully on,
so the legacy suite exercises features as before. New tenants start off (the
production default); a test that spins up a second tenant to hit a gated router
must call `enable_all_features(tenant_id)`. See
[`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) for the
two-tier semantics and isolation coverage.
