# Seed Generation Reference

*Implementation reference for randomizer seed generation: `SeedGenerationService`, the per-randomizer generators, and the settings presets under `presets/`. Part of the [documentation index](../README.md).*

## Overview

Tournaments for randomized games need a freshly rolled game ("seed") for every match. Each [`Tournament`](../../models.py) carries a nullable `seed_generator` column naming the randomizer to use; staff roll a seed per match from the admin schedule, and the resulting URL is stored and shown to players, crew, and API consumers.

| File | Contents |
|---|---|
| [`application/services/seedgen_service.py`](../../application/services/seedgen_service.py) | `SeedGenerationService`: `AVAILABLE_RANDOMIZERS`, `generate_seed()` dispatch, per-randomizer generators |
| [`application/services/match_schedule_service.py`](../../application/services/match_schedule_service.py) | `MatchScheduleService.generate_seed()` — the production entry point: locking, validation, persistence, DMs, audit |
| [`presets/`](../../presets) | Per-randomizer settings files (`alttpr/`, `ootr/`, `smmap/`) |
| [`models.py`](../../models.py) | `Tournament.seed_generator`, `GeneratedSeeds`, `Match.generated_seed` |
| [`theme/dialog/tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py) | Seed Generator select on the tournament create/edit dialog |
| [`pages/admin_tabs/admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py), [`theme/tables/match.py`](../../theme/tables/match.py) | The per-row **Generate** button and its `roll` event handling |
| [`.env.example`](../../.env.example) | `OOTR_API_KEY`, `SMMAP_SPOILER_TOKEN` (see [deployment.md](../deployment.md)) |

### Selecting a randomizer per tournament

The tournament create/edit dialog ([`tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py)) renders a select whose options are `['None'] + SeedGenerationService.AVAILABLE_RANDOMIZERS`. [`TournamentService`](../../application/services/tournament_service.py) normalizes the literal string `"None"` to `NULL` on create. On **update** the normalized `None` then falls through the `if seed_generator is not None` change guard, so picking `None` on an existing tournament leaves the stored value unchanged — once set, the generator cannot be cleared from the dialog. The admin Settings tab lists each tournament's `seed_generator` read-only.

### Generation flow

1. The admin Schedule tab's match table shows a **Generate** button (casino icon) in the Seed column for rows where `tournament_seed_generator` is set and no seed exists yet ([`theme/tables/match.py`](../../theme/tables/match.py); the card/mobile layout has the same button). Clicking emits a `roll` event that ends in `on_generate_seed` in [`admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py).
2. `on_generate_seed` calls `MatchScheduleService.generate_seed(match_id, actor=...)`, which validates permission and state (see [API](#seedgenerationservice-api) below), then dispatches `SeedGenerationService.generate_seed(match.tournament.seed_generator)`.
3. The returned string is persisted as a [`GeneratedSeeds`](../../models.py) row and linked from the match:

   | `GeneratedSeeds` field | Value |
   |---|---|
   | `seed_url` | the generator's return value (a URL for most randomizers; a plain string for Z1R) |
   | `seed_info` | `"Generated seed for match {id}"` |
   | `created_at` / `updated_at` | automatic timestamps |

   `Match.generated_seed` is a nullable FK to `GeneratedSeeds` (`related_name='matches'`). Note: `MatchScheduleService` passes a `tournament=` kwarg to `GeneratedSeeds.create()`, but the model defines no such field, so no tournament linkage is stored.
4. Players are DM'd the seed URL in the background via the Discord queue (respecting each user's `dm_notifications` opt-out), and an audit entry `match.seed_rolled` (`AuditActions.MATCH_SEED_ROLLED`) is written with `match_id`, `preset` (which holds the randomizer name), and `seed_url`.

The seed is displayed on the home Schedule and Player tabs and in the admin match table — values matching `^https?://` render as truncated hyperlinks, anything else as plain text. The REST API exposes it as `MatchResponse.generated_seed` (`GeneratedSeedBase`: `id`, `seed_url`, `seed_info`, `created_at`) in [`api.py`](../../api.py) ([rest-api.md](rest-api.md)). The admin match dialog's **Clear Seed** button ([`match_dialog.py`](../../theme/dialog/match_dialog.py)) sets the FK back to `NULL` via `MatchService.update_match(clear_seed=True)`; the `GeneratedSeeds` row itself is not deleted.

## SeedGenerationService API

`SeedGenerationService` ([`seedgen_service.py`](../../application/services/seedgen_service.py)) is stateless — instantiate it freely; `MatchScheduleService` creates one in its constructor. See [services.md](services.md) for the surrounding service layer.

```python
AVAILABLE_RANDOMIZERS = ['alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'test']
```

This class constant drives both the tournament dialog options and `MatchScheduleService`'s validity check. The module docstring lists eight randomizers, but `mmr` and `wwr` are **not** registered here (or in the dispatch map) — their generator methods exist as unreachable TODO stubs.

### Public methods

| Method | Behavior | Returns |
|---|---|---|
| `generate_seed(randomizer: str) -> str` | Looks up `randomizer` in an internal dispatch map (`alttpr`, `ff1r`, `z1r`, `smmap`, `ootr`, `test`) and awaits the matching private generator. | Seed URL (or seed/flags string for Z1R). Raises `ValueError("Unsupported randomizer: …")` for unknown names. |
| `generate_alttpr_for_tournament(tournament_id: int, balanced: bool = True) -> str` | ALTTPR generation with a community triforce text embedded; see [below](#alttpr-tournament-generation-and-triforce-texts). Raises `ValueError` when the tournament does not exist. | ALTTPR permalink URL. |

### Dispatch targets (private generators)

| Method | Registered in dispatch map | Summary |
|---|---|---|
| `_generate_alttpr` | yes | pyz3r customizer roll from `presets/alttpr/casualboots.yaml` |
| `_generate_ff1r` | yes | Local URL construction: random seed substituted into a fixed flags URL |
| `_generate_z1r` | yes | Local string: random seed number + fixed flags string |
| `_generate_smmap` | yes | HTTP POST to maprando.com with `presets/smmap/community_race_s4.json` |
| `_generate_mmr` | **no** | TODO stub returning `https://example.com/mmr-seed-url` |
| `_generate_ootr` | yes | HTTP POST to ootrandomizer.com with `presets/ootr/sgl25.json` |
| `_generate_wwr` | **no** | TODO stub returning `https://example.com/wwr-seed-url` |
| `_generate_test` | yes | 5-second sleep, then a fixed example URL |

### Error behavior

`SeedGenerationService` **raises**; it never returns error tuples:

- `ValueError` — unsupported randomizer name, missing `OOTR_API_KEY`, or unknown tournament id (tournament variant).
- Network/HTTP failures propagate from `aiohttp` (the OOTR call sets `raise_for_status=True`) and from pyz3r.

`MatchScheduleService.generate_seed(match_id, actor)` is the boundary that converts everything into a `(success: bool, message: str, seed_url: Optional[str])` tuple for the UI:

| Outcome | Tuple |
|---|---|
| Concurrent click (per-match `asyncio.Lock` in class-level `_seed_locks` already held) | `(False, "Seed generation already in progress for this match", None)` |
| Actor fails `AuthService.can_transition_match` | `(False, "You do not have permission to roll a seed for this match", None)` |
| Match already has a seed | `(False, "A seed has already been generated for this match", None)` |
| `tournament.seed_generator` is `NULL` | `(False, "No seed generator configured for this tournament", None)` |
| Generator not in `AVAILABLE_RANDOMIZERS` | `(False, "Seed generator '…' not found", None)` |
| Any exception during generation | `(False, "Error generating seed: …", None)` |
| Success | `(True, "Seed generated successfully for match ID {id}", seed_url)` |

The UI maps these to `ui.notify` colors and silently skips the "already in progress" case.

## Supported randomizers

| Key | Game | Upstream | Preset file | Env var | Return shape |
|---|---|---|---|---|---|
| `alttpr` | A Link to the Past Randomizer | alttpr.com via [pyz3r](https://github.com/tcprescott/pyz3r) | [`presets/alttpr/casualboots.yaml`](../../presets/alttpr/casualboots.yaml) | — | `https://alttpr.com/h/<hash>` |
| `ff1r` | Final Fantasy 1 Randomizer | none (URL built locally) | — | — | `https://4-8-6.finalfantasyrandomizer.com/?s=<seed>&f=<flags>` |
| `z1r` | Zelda 1 Randomizer | none (string built locally) | — | — | `"<seed> - <flags>"` (not a URL) |
| `smmap` | Super Metroid Map Rando | `https://maprando.com/randomize` | [`presets/smmap/community_race_s4.json`](../../presets/smmap/community_race_s4.json) | `SMMAP_SPOILER_TOKEN` (optional) | `https://maprando.com<seed_url>` |
| `mmr` | Majora's Mask Randomizer | not implemented | — | — | stub URL (unreachable) |
| `ootr` | Ocarina of Time Randomizer | `https://ootrandomizer.com/api/sglive/seed/create` | [`presets/ootr/sgl25.json`](../../presets/ootr/sgl25.json) | `OOTR_API_KEY` (required) | `https://ootrandomizer.com/seed/get?id=<id>` |
| `wwr` | Wind Waker Randomizer | not implemented | — | — | stub URL (unreachable) |
| `test` | — (testing) | none | — | — | fixed example URL after 5 s |

### alttpr

`_generate_alttpr` loads [`casualboots.yaml`](../../presets/alttpr/casualboots.yaml), then calls pyz3r's `ALTTPR.generate(settings=preset['settings'], endpoint='/api/customizer')` and returns `seed.url` — an alttpr.com permalink of the form `https://alttpr.com/h/<hash>`. The customizer endpoint is required because the preset defines a custom item pool and starting equipment. No credentials needed.

### ff1r

`_generate_ff1r` performs no HTTP request. It takes a hard-coded URL on `4-8-6.finalfantasyrandomizer.com` (the version-pinned 4.8.6 site) containing a fixed flags string in the `f` query parameter, generates a random 8-hex-digit uppercase seed (`'%008x' % random.randrange(16 ** 8)`), and substitutes it into the `s` parameter with `urllib.parse`. The FF1R site renders the game from flags + seed client-side, so the rewritten URL *is* the seed.

### z1r

`_generate_z1r` also performs no HTTP request: it returns `f"{seed} - {flags}"` where `seed = random.randint(0, 8999999999999999999)` and the flags string is hard-coded (`5K!ELDXj35eUlQNR4XAhcL18nJBPgbC4Hpw`). Players enter both into the offline Zelda 1 Randomizer tool. Because the value is not a URL, the match tables render it as plain text rather than a link.

### smmap

`_generate_smmap` POSTs `multipart/form-data` to `https://maprando.com/randomize` with two parts: `spoiler_token` (from `SMMAP_SPOILER_TOKEN`, falling back to a built-in default literal) and `settings` (the raw JSON text of [`community_race_s4.json`](../../presets/smmap/community_race_s4.json)). The JSON response's `seed_url` path is appended to `https://maprando.com`.

### mmr

`_generate_mmr` is a TODO stub returning `https://example.com/mmr-seed-url`. It is not in the dispatch map or `AVAILABLE_RANDOMIZERS`, so it cannot be selected on a tournament and `generate_seed('mmr')` raises `ValueError`.

### ootr

`_generate_ootr` loads [`sgl25.json`](../../presets/ootr/sgl25.json) and POSTs it as the JSON body to `https://ootrandomizer.com/api/sglive/seed/create` with query parameters `key=<OOTR_API_KEY>`, `version=8.3.0`, and `encrypt=true` (`raise_for_status=True`). If `OOTR_API_KEY` is unset it raises `ValueError('OOTR_API_KEY is not configured.')` rather than silently sending `key=None`. The response's `id` becomes `https://ootrandomizer.com/seed/get?id=<id>`.

### wwr

`_generate_wwr` is a TODO stub identical in status to `mmr`: unregistered and unreachable through `generate_seed`.

### test

`_generate_test` awaits `asyncio.sleep(5)` to simulate processing time, then returns `https://example.com/test-seed-url`. It **is** selectable on tournaments — its purpose is exercising the full UI flow (button spinner, per-match lock, persistence, DMs) without calling an external service.

## ALTTPR tournament generation and triforce texts

`generate_alttpr_for_tournament(tournament_id, balanced=True)` rolls the same `casualboots.yaml` preset but first embeds a community-submitted end-game text from the tournament's approved [triforce text](../features/triforce-texts.md) pool ([`triforce_text_service.py`](../../application/services/triforce_text_service.py)):

- **`balanced=True`** (default) — `TriforceTextService.get_balanced_text()`: pick a random *submitter* with approved texts, then a random text of theirs, so every submitter is weighted equally regardless of how many texts they had approved. Texts whose submitter was deleted form their own bucket.
- **`balanced=False`** — `get_random_text()`: a uniformly random approved text.

When a text is found, it is injected into the customizer settings before generation:

```python
preset['settings']['texts']['end_triforce'] = "{NOBORDER}\n" + text
```

(`{NOBORDER}` is an ALTTP text-engine directive; the text itself is up to 3 newline-joined lines of ≤19 characters, validated at submission time.) When the pool is empty the method falls back to a plain seed with the preset's default text. The method raises `ValueError` if the tournament id does not exist.

Note: the match-rolling flow always calls `generate_seed('alttpr')` → `_generate_alttpr`, which does **not** inject texts; `generate_alttpr_for_tournament` currently has no caller in the codebase.

## Presets

```
presets/
├── alttpr/
│   ├── casualboots.yaml      # used by _generate_alttpr and generate_alttpr_for_tournament
│   └── sglive2025.yaml       # not referenced by any code
├── ootr/
│   └── sgl25.json            # used by _generate_ootr
└── smmap/
    └── community_race_s4.json  # used by _generate_smmap
```

There is no preset-selection mechanism: each generator method opens its preset path as a hard-coded relative path (so the process must run from the repository root, as `start.sh` and the Docker image do). `Tournament.seed_generator` chooses the randomizer only, never the preset. The ALTTPR YAMLs carry a top-level `customizer: true` flag plus `goal_name`/`description` metadata; only the `settings` mapping is sent to the API.

| Preset | Configures |
|---|---|
| [`alttpr/casualboots.yaml`](../../presets/alttpr/casualboots.yaml) | "Casual w/ Boots Start": Standard world state, Ganon goal, 7/7 crystals, assured sword, starting Pegasus Boots + 3 boss heart containers, no-glitches logic, advanced item placement, standard dungeon items, hints/spoilers off, `tournament: true`, full custom item pool and prize-pack drop counts under `settings.custom` |
| [`alttpr/sglive2025.yaml`](../../presets/alttpr/sglive2025.yaml) | "SpeedGaming Live 2024 Settings" (`goal_name: sglive2024` despite the filename): Open world state, randomized weapons, quickswap allowed, Ganon goal 7/7, same starting boots equipment, custom pool with item-overflow replacements, no enemizer, spoilers/hints off. Currently unused by code |
| [`ootr/sgl25.json`](../../presets/ootr/sgl25.json) | Complete OOTR web-API settings payload (`user_message: "SGL 2025"`): glitchless logic, Closed Deku / open Kakariko / open Door of Time, stones bridge, adult start, fast Gerudo Fortress, 2 empty dungeons (rewards mode, Light Medallion), Ganon Boss Key on LACS, songs shuffled on song locations, `hint_dist: sgl2025`, curated allowed-tricks list, plandomized Temple of Time reward, spoiler log created, `encrypt: true` |
| [`smmap/community_race_s4.json`](../../presets/smmap/community_race_s4.json) | Map Rando settings export (`version: 119`, "Community Race Season 4"): Hard skill-assumption preset with individual tech and notable-strat toggles, "Bosses" objective preset (Kraid/Phantoon/Draygon/Ridley), Standard map layout, Ammo doors, save-the-animals off |

## Adding a randomizer or preset

1. Drop a settings file under `presets/<randomizer>/` if the upstream API takes one (skip for purely local generators like `ff1r`/`z1r`).
2. Add an `async def _generate_<name>(self) -> str` to [`seedgen_service.py`](../../application/services/seedgen_service.py) that loads the preset, calls the upstream service with `aiohttp` (never blocking `requests`), and returns the seed URL/string. Read any credential from an environment variable and raise `ValueError` with a clear message when it is missing (see `_generate_ootr`).
3. Register the name in **both** `AVAILABLE_RANDOMIZERS` and the `generator_map` inside `generate_seed` — a method alone is unreachable (see `mmr`/`wwr`).
4. Document the new env var in [`.env.example`](../../.env.example) and [deployment.md](../deployment.md), and add it to the deployment environment.
5. Select the new name as the tournament's Seed Generator in the tournament dialog; the admin schedule's Generate button picks it up with no further wiring. Update this page and the preset table above.

To change which preset an existing randomizer uses, edit the hard-coded path in its `_generate_*` method (and `generate_alttpr_for_tournament` for ALTTPR, which loads its preset independently).

Related: [services.md](services.md) (service layer), [data-model.md](data-model.md) (`GeneratedSeeds`, `Match`, `Tournament` schemas), [frontend.md](frontend.md) (match table internals).
