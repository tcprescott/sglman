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

Gating a subsystem is **two obligations**, and doing only the first is the
failure mode to watch for:

1. **Hide it at the entry surfaces** so it is not visible where it is not live.
2. **Enforce it in the owning service** so it is not *reachable* where it is not
   live — by a caller that has no gate, or by one whose gate someone forgot.

**UI-only gating is not gating.** Hiding a tab does nothing about a Discord
interaction handler, a background worker, a REST router nobody mounted behind
`require_feature`, or the next page someone adds. The service that owns the
feature is the one place every caller passes through, so that is where the
refusal belongs.

Both halves stay **authorization-style gates at a boundary** (like
`@protected_page` and the API auth deps), never a business rule buried inside a
transaction. The service guard sits on the public entry method and reads a
per-request cache (`_flag_cache`, a contextvar keyed by tenant), so N guards in
one request cost one resolution rather than 3N queries.

| Surface | How |
|---|---|
| Whole pages | `@protected_page('/path', feature=FeatureFlag.X)` → 404 when off (hidden, role-independent). Used by `/qualifiers`, `/equipment`, `/volunteer`. |
| Nav links to a gated page | The nav must not offer a link the gate will reject, or it dead-ends on a 404/403. The Volunteer entry resolves through `AuthService.can_view_volunteer` (flag **and** role), which `BaseLayout` calls when `show_volunteer` is left at its `None` default — one helper shared with the page's own gate so the two cannot drift. |
| Admin tabs | `pages/admin.py` loads `FeatureFlagService().enabled_flags()` once and `and`-s the flag into each subsystem tab's condition. |
| Home tabs | `pages/home.py` gates the Triforce Texts and Equipment tabs (My Availability stays ungated — it feeds crew signup too). |
| REST API | `api/__init__.py` attaches `require_feature(FeatureFlag.X)` to each gated router's `include_router`; a disabled feature 404s. |
| Auto workers | The racetime auto-open and SpeedGaming sync workers skip a tenant whose flag is off (a clean `is_enabled` check inside `tenant_scope`). Skipping, not raising: a loop over tenants must not die on the first one that lacks the feature. |
| **The owning service** | `@requires_feature(FeatureFlag.X)` (from `application.feature_flags`) on its public entry methods — every mutation, plus the top-level reads that return the feature's data. Not internal helpers or per-row getters. Raises `FeatureDisabledError`. Each flag names its owning module(s) in `FeatureFlagSpec.service_modules`, and `check_feature_flag_gating.py` fails the edit if one of them does not enforce the flag. |

The admin **Features** tab itself is only role-gated (STAFF), never flag-gated —
it is the control panel.

**A super-admin does not bypass a flag.** The platform role is staff-equivalent
inside every tenant (see
[role-based-auth.md](role-based-auth.md#super-admin-authority-inside-a-tenant)),
but that is authority over what a community has turned *on*: `is_enabled` takes no
user, so a tenant with `VOLUNTEERS` off 404s `/volunteer` for a super-admin too.
Gating a feature is not an authorization question, so the fix for "I can't see it"
is to grant the tenant the flag on `/platform`, not to widen a role.

### API-key randomizers are not flag-gated

A flag is the wrong tool for a keyed randomizer, and this used to be done the
wrong way: `dk64_randomizer` existed only to record that a community was
authorized to use the deployment's shared DK64 API key. Randomizer credentials
are now **per tenant** — a community supplies the key it was issued and is bound
by — so the credential itself is the gate: the randomizer is hidden from every
selector until the key is set, and rolling without one raises. There is nothing
left for a flag to decide. See
[seed-generation.md](../reference/seed-generation.md#per-tenant-credentials).

## The current flags

| Flag | Category | Established? | Hidden at | Enforced in |
|---|---|---|---|---|
| `async_qualifiers` | Online tournaments | no (ships dark) | `/qualifiers`, admin Qualifiers tab, `/async-qualifiers*` API | `async_qualifier/` (`AsyncQualifierService`, `AsyncQualifierLiveRaceService`) |
| `racetime_rooms` | Online tournaments | no | admin Racetime tab, race-room + profile API, auto-open worker | `race_room_service.py` (the worker delegates to it) |
| `speedgaming_etl` | Online tournaments | no | admin SpeedGaming tab, `/speedgaming` API, sync worker | `speedgaming_sync_service.py`, `speedgaming_sync_worker.py` |
| `brackets` | Online tournaments | no (ships dark) | admin Brackets tab, public bracket pages (`/tournament/{id}/brackets`, `/brackets/{id}`), `/brackets` API | `bracket_service.py` |
| `challonge` | Community | **yes** | admin Challonge tab (no REST router exists) | `challonge_service.py`; `push_result_if_linked` soft-skips |
| `equipment` | Community | **yes** | `/equipment`, home + admin Equipment tabs (no REST router exists) | `equipment_service.py` |
| `volunteers` | Community | **yes** | `/volunteer` + its nav link, admin Vol. Roster/Schedule, `/volunteers` API | `volunteer/` (reminder worker skips) |
| `triforce_texts` | Community | **yes** | home + admin Triforce tabs, `/triforce-texts` API | `triforce_text_service.py`; the seed-roll text embed soft-returns `None` |

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
2. **Hide it at the entry surfaces:** `feature=` on the page's `@protected_page`; `and FeatureFlag.X in live` on its admin/home tab; `require_feature(FeatureFlag.X)` on its REST router; an `is_enabled` skip in any background worker that acts on it; and resolve any nav link *to* the page through an access helper so it is never offered where the gate would reject it.
3. **Enforce it in the owning service:** name the module(s) in the spec's `service_modules`, then put `@requires_feature(FeatureFlag.X)` on their public entry methods — every mutation plus the top-level reads that return the feature's data. Leave soft integration points (something an unrelated flow calls for *every* record) returning a neutral value instead, and let workers skip rather than raise.
4. Seed it in [`scripts/seed_dev.py`](../../scripts/seed_dev.py) so the dev tenants exercise it. If the fixture goes through a service that now enforces the flag, seed it only for a tenant whose tier grants it.
5. Add coverage to [`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) and a service-refusal case to [`tests/test_feature_flag_enforcement.py`](../../tests/test_feature_flag_enforcement.py); if a test spins up a second tenant that should behave normally, give it the flags (`enable_all_flags` in `tests/conftest.py`, `enable_all_features` in `tests/api_helpers.py`).

`check_feature_flag_gating.py` (PostToolUse hook) fails the edit if either half is
missing, so a flag cannot ship UI-only gated.

## Testing

The `db` fixture provisions the default tenant (id 1) with every flag fully on
(explicit `available+enabled` override rows), so the legacy suite exercises
features as before regardless of groups. New tenants start off (the production
default); a test that spins up a second tenant to hit a gated router must call
`enable_all_features(tenant_id)`. See
[`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) for the
effective-state resolution, override precedence, live group derivation, default
fallback, single-default, deletion-reassign, and isolation coverage.
