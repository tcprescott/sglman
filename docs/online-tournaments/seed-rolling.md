# Feature 2: Seed rolling

> Part of the [Online Tournaments plan](README.md) (proposed, not implemented).
> Cross-cutting decisions, roadmap, and shared risks live in the
> [overview](README.md).

SGLMan already rolls `alttpr`, `ootr`, `smmap`, `ff1r`, `z1r`
([seed-generation.md](../reference/seed-generation.md)). The target: **every
randomizer SahasrahBot supports is eventually supported in SGLMan.**

Source: `alttprbot/services/seedgen/`, `models/presets.py`.

## User-managed presets first

Per the [design principle](README.md#design-principle-user-definable-tournament-logic),
presets are **data a tenant admin authors in the UI**, not files in the repo:

- A tenant-scoped `Preset` model (`name`, `randomizer`, `settings` JSON,
  `description`) with CRUD on an admin tab gated by the new `PRESET_MANAGER` role
  (or STAFF); `SeedGenerationService.generate_seed` takes a preset instead of
  opening hard-coded paths. Existing `presets/` files ship as importable defaults.
- This is the foundation both [Async Qualifier](async-qualifiers.md) pools and the
  [racetime room lifecycle](racetime-room-lifecycle.md) seed-attach step sit on.
  (sahabot2's analog is `RandomizerPreset` + a `Tournament.randomizer_preset` FK and
  `preset_selection_rules` JSON — precedent for per-match conditional preset choice.)

## Incremental randomizer coverage

Confirmed SahasrahBot randomizer families to bring over include ALTTPR (+ door
rando + **mystery weightsets**), SM, SMZ3, SM VARIA/DASH, CT: Jets of Time, and
the OoTR/Zelda/FF families SGLMan already partially covers. First implementation
task of that phase: enumerate the authoritative list from
`alttprbot/services/seedgen/` and track coverage as a checklist here. Each backend
follows the existing pattern (async HTTP, env-var credentials, `ValueError` on
missing config).

**Mystery support** (weighted random settings) is part of seed rolling, not a
separate feature: a weightset is just a `Preset` variant whose payload the
generator samples — same user-managed authoring story.

### Local development / testing (`MOCK_SEEDGEN`)

Every real backend needs credentials, is slow, or is simply unreachable from a
dev sandbox, so rolling a pool's seeds would fail there. Set `MOCK_SEEDGEN=true`
(the dev `.env` and `./start.sh mock` do) and `SeedGenerationService.generate_seed`
short-circuits to a believable, unique `https://mock.seedgen.local/<randomizer>/…`
permalink — after validating the randomizer is one of `AVAILABLE_RANDOMIZERS` —
without touching any backend. This lets the [async-qualifier](async-qualifiers.md)
"Roll" flow and the browser-validation loop exercise the full
roll → draw → submit → review → par-score → leaderboard lifecycle end to end. The
flag is refused when `ENVIRONMENT=production` (`application/utils/mock_seedgen.py`),
mirroring `MOCK_DISCORD`/`MOCK_CHALLONGE`.

### Coverage checklist

Phase 1 (preset infrastructure) is **implemented** — see [PR 1](implementation/pr-1-presets.md). Only ALTTPR reads `preset.settings` today; the remaining backends stay hard-coded until the randomizer-coverage expansion PR, tracked below.

| Randomizer | In SGLMan today | Ported |
|---|---|---|
| alttpr | ✅ | — |
| alttpr door rando | — | ☐ |
| alttpr mystery (weightsets) | — | ☐ |
| sm | — | ☐ |
| smz3 | — | ☐ |
| sm varia / dash | — | ☐ |
| ct jets of time | — | ☐ |
| ootr | ✅ (partial) | — |
| ff1r | ✅ | — |
| z1r | ✅ | — |
| smmap (Map Rando) | ✅ | — |

## Data model

`Preset` (tenant-scoped) + preset FKs from `Tournament` and
[`AsyncQualifierPool`](async-qualifiers.md). `preset.*` audit/event members. No new
enums.

## Roadmap

- **Phase 1** ✅ *implemented* — user-managed presets + seedgen preset selection:
  `Preset` model, admin tab, `SeedGenerationService` preset arg, built-in preset
  import. ALTTPR-first; immediately useful on-site too. This is the recommended
  starting point for the whole plan.
- **Phase 9+** — randomizer coverage expansion: incremental backends toward full
  SahasrahBot parity; mystery weightsets.

(Full ordering across all features: [roadmap](README.md#phased-roadmap).)

## Feature-specific risks

- **Credential surface.** Each new backend adds an upstream API + credential;
  follow the existing pattern (env-var read, `ValueError` on missing config, never
  blocking I/O). Track which backends need which secrets in
  [deployment.md](../deployment.md) as they land.

See the [overview](README.md#cross-cutting-risks) for cross-cutting risks
(config/code boundary especially — presets are the canonical example of
user-definable data).
