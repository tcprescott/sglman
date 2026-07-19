# PR 11 — Randomizer coverage expansion

> Feature 2 completion. Roadmap phase 9+. Incremental; can be **several small PRs**,
> one per randomizer family, rather than one large one.

**Goal:** extend seed generation toward every randomizer SahasrahBot supports, plus
mystery weightsets — each as a user-managed `Preset` backend.

**Depends on:** PR 1 (preset model + preset-arg seedgen). **Unblocks:** broader
tournament/qualifier game coverage.

## Deliverables

- **First task**: enumerate the authoritative supported list from SahasrahBot's
  `alttprbot/services/seedgen/` and fill the coverage checklist in
  [seed-rolling.md](../seed-rolling.md). Known families to bring over: ALTTPR door
  rando, **mystery weightsets**, SM, SMZ3, SM VARIA/DASH, CT: Jets of Time, and the
  OoTR/Zelda/FF families (plus the longer tail — TWWR, SMB3R, Z2R, SMR, etc.).
  DK64 (`dk64r`, already a registered stub) has its own sub-plan:
  [dk64-randomizer.md](dk64-randomizer.md).
- **Per backend**: an `async def _generate_<name>` on `SeedGenerationService`
  following the existing pattern (async HTTP via `aiohttp`/`httpx`, env-var
  credentials, `ValueError` on missing config), registered in the dispatch map and
  `AVAILABLE_RANDOMIZERS`; the `Preset.settings` payload feeds it. Document each new
  credential in [deployment.md](../../deployment.md) + `.env.example`.
- **Mystery** ([gap preset-mystery-discriminator](../gap-analysis.md)): register the
  weightset backend as its **own randomizer key** (the generator samples the weighted
  payload), not an overloaded fixed-settings preset.
- Update the checklist + preset docs as each lands.

## Decisions that apply

User-managed presets; a new randomizer *primitive* is a reviewed code change, a new
tournament using it is pure config.

## Reference implementations

- **SahasrahBot** `alttprbot/services/seedgen/` (the authoritative backend set +
  mystery weightset logic); **sahabot2** `randomizer` handling per game.
- **sglman**: `application/services/seedgen_service.py` (existing
  `_generate_alttpr`/`_generate_ootr`/`_generate_smmap` as the pattern to copy).

## Acceptance criteria

- Each added randomizer rolls a real seed from a user-authored preset (verify a real
  roll per backend); mystery produces a valid weighted seed; the coverage checklist
  reflects reality.

## Out of scope

Per-match conditional preset selection (a later extension); intentionally-excluded
randomizers with no usable API (document, don't stub — see
[reference/seed-generation.md](../../reference/seed-generation.md)).
