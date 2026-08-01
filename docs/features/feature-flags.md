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

Gating is the two obligations CLAUDE.md states — hide it at the entry surfaces,
*and* enforce it in the owning service. Both halves are authorization-style gates
at a boundary, never a business rule inside a transaction: the service guard sits
on the public entry method and reads a per-request cache (`_flag_cache`, a
contextvar keyed by tenant), so N guards in one request cost one resolution rather
than 3N queries. Concretely:

| Surface | How |
|---|---|
| Whole pages | `@protected_page('/path', feature=FeatureFlag.X)` → 404 when off (hidden, role-independent). Used by `/qualifiers`, `/equipment`, `/volunteer`. |
| Bare `@ui.page` routes | An OAuth leg that cannot use `@protected_page` (it serves a cross-host callback) checks the flag in the handler and redirects back — `pages/challonge_oauth.py`'s `_challonge_live`. Hiding the entry button is not enough; the URL stays reachable. |
| Nav links to a gated page | The nav must not offer a link the gate will reject, or it dead-ends on a 404/403. The Volunteer entry resolves through `AuthService.can_view_volunteer` (flag **and** role), which `BaseLayout` calls when `show_volunteer` is left at its `None` default — one helper shared with the page's own gate so the two cannot drift. |
| Admin tabs | `pages/admin.py` loads `FeatureFlagService().enabled_flags()` once and `and`-s the flag into each subsystem tab's condition. |
| Home tabs | `pages/home.py` gates the Brackets, Triforce Texts and Equipment tabs (My Availability stays ungated — it feeds crew signup too). Brackets is resolved before the signed-in branch, since it is anonymous-readable. |
| REST API | `api/__init__.py` attaches `require_feature(FeatureFlag.X)` to each gated router's `include_router`; a disabled feature 404s. |
| Auto workers | The racetime auto-open and SpeedGaming sync workers skip a tenant whose flag is off (a clean `is_enabled` check inside `tenant_scope`). Skipping, not raising: a loop over tenants must not die on the first one that lacks the feature. |
| **The owning service** | `@requires_feature(FeatureFlag.X)` (from `application.feature_flags`) on its public entry methods — every mutation, plus the top-level reads that return the feature's data. Not internal helpers or per-row getters. Raises `FeatureDisabledError`. Each flag names its owning module(s) in `FeatureFlagSpec.service_modules`, and `check_feature_flag_gating.py` fails the edit if one of them does not enforce the flag. |

The admin **Features** tab itself is only role-gated (STAFF), never flag-gated —
it is the control panel.

**A super-admin does not bypass a flag.** The platform role is staff-equivalent
inside every tenant (see
[authentication.md](../reference/authentication.md#roles)),
but that is authority over what a community has turned *on*: `is_enabled` takes no
user, so a tenant with `VOLUNTEERS` off 404s `/volunteer` for a super-admin too.
The fix for "I can't see it" is to grant the tenant the flag on `/platform`, not
to widen a role.

**A keyed randomizer is not flag-gated.** Randomizer credentials are per tenant,
so the credential is the gate: the randomizer is hidden from every selector until
the key is set, and rolling without one raises. See
[seed-generation.md](../reference/seed-generation.md#per-tenant-credentials).

## The current flags

| Flag | Category | Established? | Hidden at | Enforced in |
|---|---|---|---|---|
| `async_qualifiers` | Online tournaments | no (ships dark) | `/qualifiers`, admin Qualifiers tab, `/async-qualifiers*` API | `async_qualifier/` (`AsyncQualifierService`, `AsyncQualifierLiveRaceService`) |
| `racetime_rooms` | Online tournaments | no | admin Racetime tab, race-room + profile API, auto-open worker | `race_room_service.py` (the worker delegates to it) |
| `speedgaming_etl` | Online tournaments | no | admin SpeedGaming tab, `/speedgaming` API, sync worker | `speedgaming_sync_service.py`, `speedgaming_sync_worker.py` |
| `brackets` | Online tournaments | no (ships dark) | admin Brackets tab, public bracket pages (`/tournament/{id}/brackets`, `/brackets/{id}`), `/brackets` API | `bracket_service.py` |
| `challonge` | Community | **yes** | admin Challonge tab (no REST router exists) | `challonge_service.py`; `push_result_if_linked` soft-skips |
| `equipment` | Community | **yes** | `/equipment`, home + admin Equipment tabs, `api/routers/equipment.py` | `equipment_service.py` |
| `volunteers` | Community | **yes** | `/volunteer` + its nav link, admin Vol. Roster/Schedule, `/volunteers` API | `volunteer/` (reminder worker skips) |
| `triforce_texts` | Community | **yes** | home + admin Triforce tabs, `/triforce-texts` API | `triforce_text_service.py`; the seed-roll text embed soft-returns `None` |
| `feedback` | Community | **yes** | the drawer's Feedback item (`theme/base.py`), admin Feedback tab, the profile's "Your feedback" card, `api/routers/feedback.py` | `feedback_service.py` |
| `event_info` | Community | no (ships dark) | `/event-info*`, the drawer's Event Information item (`theme/base.py`); `help_icon` resolves the flag itself before reading a handbook snippet (no REST router exists) | `event_info_service.py` |

`established=True` marks a feature that was **already in live use** when its flag
was added. [Migration 30](../../migrations/models/30_20260715000000_feature_flags.py)
pinned the first four `available+enabled` for every existing tenant so gating
them didn't make them vanish, and
[migration 51](../../migrations/models/51_20260731190000_gate_feedback.py) does
the same for `feedback`, gated later; new/unreleased features (the four online
ones) ship dark. Gating something already live always needs that backfill —
without it the flag defaults off and the feature disappears from under the
communities using it.

## Groups (tiers)

[Migration 31](../../migrations/models/31_20260715120000_feature_flag_groups.py)
adds the group layer: `FeatureFlagGroup` + `Tenant.feature_group`, tri-state
`TenantFeatureFlag.available/enabled`, and an **empty** `Default` group plus an
`Online Tournaments` group. It is non-destructive — the migration-30 pins survive
as per-tenant overrides, so a community keeps its features until you move it onto
a group via `/platform`.

Super-admins manage groups on `/platform` → **Feature Groups** (create/edit/
delete, mark one default, pick its flags) and assign a tenant to a group from its
**Features** button. Because availability derives from the group **live**, editing
a group re-tiers every tenant on it. `FeatureFlagService` owns the group CRUD, the
`assign_tenant_group` write, and the effective-state resolution.

## Adding a feature flag

Only gate a feature behind a flag when it warrants one — **always ask the user
first** (see CLAUDE.md). When you do:

1. Add a member to [`FeatureFlag`](../../models/enums.py) and a `FeatureFlagSpec`
   to [`application/feature_flags.py`](../../application/feature_flags.py). Set
   `established=True` **only** if the feature is already in live use (then add its
   key to the migration backfill so existing tenants keep it).
2. Wire **both halves of the gate** per the surface table above, and name the
   owning module(s) in the spec's `service_modules` so the hook can check the
   service half.
3. Seed it in [`scripts/seed_dev.py`](../../scripts/seed_dev.py) so the dev tenants exercise it. If the fixture goes through a service that now enforces the flag, seed it only for a tenant whose tier grants it.
4. Add coverage to [`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) and a service-refusal case to [`tests/test_feature_flag_enforcement.py`](../../tests/test_feature_flag_enforcement.py); if a test spins up a second tenant that should behave normally, give it the flags (`enable_all_flags` in `tests/conftest.py`, `enable_all_features` in `tests/api_helpers.py`).

`check_feature_flag_gating.py` (PostToolUse hook) fails the edit if either half is
missing, so a flag cannot ship UI-only gated.

## Testing

### The flags-off browser sweep

The gap the Python suite cannot cover: a surface that is **not** flag-gated but
calls a gated service anyway. It renders fine for a community that has the
feature and raises `FeatureDisabledError` for one that doesn't — and since
`pages/` has no automated coverage, the first report is a dead section in
production (the Profile tab calling `ChallongeService.participant_tournament_ids`
was exactly this). Drive it in a browser instead:

```bash
scripts/ui_flag_sweep.sh
```

It snapshots the dev tenant's flags, forces every flag off, walks the ungated
home/admin surfaces listed in `scripts/ui_flag_targets.json`, repeats against the
mixed-tier `second` tenant, restores the flags, and fails on any tab that renders
`This section failed to load…` or logs a `FeatureDisabledError`. Details and the
one-off knob (`scripts/set_feature_flags.py`) are in the
[`ui-validation`](../../.claude/skills/ui-validation/SKILL.md) skill.

Rule of thumb for the fix: a surface everyone gets resolves the flag itself —
`FeatureFlag.X in await FeatureFlagService().enabled_flags()` — and skips both
the service call and the UI it feeds. Don't drop the service guard to make the
page work; that is the half that makes gating real.

### Unit tests

The `db` fixture provisions the default tenant (id 1) with every flag fully on
(explicit `available+enabled` override rows), so the legacy suite exercises
features as before regardless of groups. New tenants start off (the production
default); a test that spins up a second tenant to hit a gated router must call
`enable_all_features(tenant_id)`. See
[`tests/test_feature_flags.py`](../../tests/test_feature_flags.py) for the
effective-state resolution, override precedence, live group derivation, default
fallback, single-default, deletion-reassign, and isolation coverage.
