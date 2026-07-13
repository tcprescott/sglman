# PR 1 — User-managed presets + seedgen preset selection

> Feature 2. Roadmap phase 1. The recommended **first feature PR** — useful on-site
> too, and the foundation qualifiers (PR 9) and room seeding (PR 6) sit on.

**Goal:** presets become tenant-authored DB rows; seed generation takes a preset
instead of hard-coded paths.

**Depends on:** PR 0 (roles). **Unblocks:** PR 6 (seed attach), PR 9 (pool presets),
PR 11 (coverage).

## Deliverables

- **`Preset` model** (tenant-scoped): `name`, `randomizer`, `settings` (JSONField),
  `description`; composite `unique (tenant, randomizer, name)`; repo + service +
  migration + leak test.
- **`Tournament.preset`** FK (nullable, `SET_NULL`), coexisting with the existing
  `seed_generator` string — spell out the coexistence: FK wins when set; document a
  backfill of legacy `seed_generator` values into `Preset` rows (can be a follow-up
  data step). See [gap 4.8](../gap-analysis.md).
- **`SeedGenerationService.generate_seed`** takes a resolved `Preset` (randomizer +
  settings) instead of opening a hard-coded path. Keep ALTTPR-first working; other
  backends still hard-coded until PR 11.
- **Admin Presets tab** (gated by `PRESET_MANAGER` / STAFF): CRUD, plus **import of
  the built-in `presets/` files** as starting rows.
- **Update the existing call site** `MatchScheduleService.generate_seed` to resolve
  the tournament's `Preset` FK ([gap seedgen-preset-refactor](../gap-analysis.md)).
- **Docs**: update [seed-rolling.md](../seed-rolling.md) coverage checklist +
  [reference/seed-generation.md](../../reference/seed-generation.md).

## Decisions that apply

User-managed presets (DB rows, UI-authored); hybrid config; `PRESET_MANAGER` role.

## Reference implementations

- **sahabot2**: `models/*` `RandomizerPreset` + `Tournament.randomizer_preset` FK +
  `preset_selection_rules` JSON (per-match conditional preset choice — a later
  extension, not required now).
- **sglman**: `application/services/seedgen_service.py` (dispatch + per-randomizer
  generators), `theme/dialog/tournament_edit_dialog.py` (seed-generator select),
  `application/services/match_schedule_service.py:generate_seed`.

## Acceptance criteria

- A `PRESET_MANAGER` creates/edits a preset in the UI; a tournament references it;
  rolling an ALTTPR seed for a match uses the preset's settings (verify against a
  real roll via the `verify` skill).
- `casualboots.yaml` etc. import as built-in presets and still produce the same seed.
- Leak test: presets don't cross tenants.

## Out of scope

Non-ALTTPR backends (PR 11); mystery weightsets (PR 11); per-match settings
submission (not ported — see [gap](../gap-analysis.md) "deliberately out of scope").
