# PR 0 — Foundations: system user, roles, config substrate

> Cross-cutting. Roadmap: prerequisite for everything. **Keep it small** — it exists
> so feature PRs don't each reinvent these.
>
> **Status: implemented.** System `User` (`models.SYSTEM_USER_DISCORD_ID` + `User.is_system`,
> resolved via `UserService.get_system_user`); `Role.PRESET_MANAGER`/`SYNC_ADMIN`/`QUALIFIER_ADMIN`
> + `AuthService.is_system`/`can_manage_presets`/`can_manage_sync`/`can_admin_qualifier`;
> `Tournament.config` + `validate_tournament_config` (`tournament_config.py`) + the
> `tournament_strategies/` registry; migration `21_20260713000000_pr0_foundations.py`.

**Goal:** land the three shared primitives every later PR builds on: a system actor,
the new roles, and the hybrid-config substrate.

**Depends on:** nothing. **Unblocks:** all other PRs.

## Deliverables

- **System `User`** ([decision](../README.md#decisions-log)): a seeded, reserved
  `User` representing automation. `discord_id` is required+unique today, so pick the
  sentinel approach — a reserved row with a sentinel `discord_id` (document the
  value) and an `is_system`-style marker or a well-known id. Add a helper
  (`UserService.get_system_user()` / a cached accessor) that workers and bot handlers
  pass as `actor`. Ensure `AuditService.write_log` and `event_bus` handle it (it has
  a real `username` to snapshot — that's why a row beats a bare `-1`).
- **New `Role` members**: `PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN` on the
  `Role` enum (`models.py`). Add `AuthService` methods: `can_manage_presets`,
  `can_manage_sync`, `can_admin_qualifier(user, qualifier=None)` (STAFF/super-admin
  OR the role OR per-entity admin membership). Follow the existing `can_*` patterns.
- **Hybrid config substrate** ([decision](../README.md#decisions-log)): add a
  `config = JSONField(null=True)` to `Tournament` and a small validation helper —
  a Pydantic model per config shape + a `validate_config()` used by the service on
  save (raises `ValueError` on unknown keys). Scaffold a **strategy registry**
  module (`application/services/tournament_strategies/` or similar) with a
  register/lookup pattern; concrete strategies land in their feature PRs. No `eval`,
  ever.
- **Migration** for the `Tournament.config` column (roles on `UserRole.role` are a
  `CharEnumField` string — confirm whether a migration is needed).
- **Docs**: note the primitives in the relevant reference docs.

## Decisions that apply

Reserved system `User`; hybrid config (typed columns + validated JSON); dedicated
roles. All in the [decisions log](../README.md#decisions-log).

## Reference implementations

- **sahabot2**: `models/user.py` (`SYSTEM_USER_ID = -1` + `is_system_user_id()` —
  the sentinel idea, though sglman prefers a real row for audit snapshotting);
  `modules/tournament/models/match_schedule.py` (`Tournament.settings_form_schema` /
  `preset_selection_rules` JSON — the hybrid-config precedent).
- **sglman**: `models.py` `Role` enum + `application/services/auth_service.py`
  `can_*` methods; `application/services/audit_service.py` (actor snapshotting);
  `Tenant.config` JSONField as the existing JSON-column precedent.

## Acceptance criteria

- A worker can call a gated service method as the system user without a
  `PermissionError`, and the audit row shows the system actor.
- `AuthService.can_manage_presets/…` return correct results for each role.
- Saving a `Tournament.config` with an unknown key raises `ValueError`; a valid one
  round-trips. Tests cover all three.

## Out of scope

Concrete strategies (per feature PR); any feature model. This PR is plumbing only.
