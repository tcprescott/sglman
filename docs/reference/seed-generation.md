# Seed Generation Reference

*Implementation reference for randomizer seed generation: `SeedGenerationService`, the per-randomizer generators, and the settings presets under `presets/`. Part of the [documentation index](../README.md).*

## Overview

Tournaments for randomized games need a freshly rolled game ("seed") for every match. Each [`Tournament`](../../models/tournament.py) either references a [`Preset`](#presets-db-backed) (the `preset` FK — a tenant-authored randomizer + settings blob) or names a randomizer directly via the legacy nullable `seed_generator` column. The FK wins when both are set. Staff roll a seed per match from the admin schedule, and the resulting URL is stored and shown to players, crew, and API consumers.

| File | Contents |
|---|---|
| [`application/services/seedgen_service.py`](../../application/services/seedgen_service.py) | `SeedGenerationService`: `AVAILABLE_RANDOMIZERS`, `generate_seed()` dispatch, per-randomizer generators |
| [`application/services/match/match_schedule_service.py`](../../application/services/match/match_schedule_service.py) | `MatchScheduleService.generate_seed()` — the production entry point: locking, validation, persistence, DMs, audit |
| [`application/services/preset_service.py`](../../application/services/preset_service.py) | `PresetService`: CRUD (gated by `AuthService.can_manage_presets`) + `import_builtins` from the `presets/` files |
| [`presets/`](../../presets) | Built-in settings files (`alttpr/`, `ootr/`, `smmap/`) — starting rows imported into the `Preset` table |
| [`models/tournament.py`](../../models/tournament.py) | `Tournament.seed_generator`, `Tournament.preset`, `Preset`, `GeneratedSeeds`, `Match.generated_seed` |
| [`theme/dialog/tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py) | Seed Generator + Seed Preset selects on the tournament create/edit dialog |
| [`pages/admin_tabs/admin_presets.py`](../../pages/admin_tabs/admin_presets.py) | Admin **Presets** tab: preset CRUD + import built-ins |
| [`pages/admin_tabs/admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py), [`theme/tables/match.py`](../../theme/tables/match.py) | The per-row **Generate** button and its `roll` event handling |
| [`application/randomizer_credentials.py`](../../application/randomizer_credentials.py) | `CredentialSpec` registry: which credential each keyed randomizer needs |
| [`application/services/randomizer_credential_service.py`](../../application/services/randomizer_credential_service.py) | `RandomizerCredentialService`: per-tenant credential CRUD + roll-time resolution |
| [`pages/admin_tabs/admin_randomizer_keys.py`](../../pages/admin_tabs/admin_randomizer_keys.py) | Admin **Randomizer Keys** tab: enter/clear this community's credentials |

### Selecting a randomizer per tournament

The tournament create/edit dialog ([`tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py)) renders two selects:

- **Seed Generator** — options `['None'] + SeedGenerationService.AVAILABLE_RANDOMIZERS`. [`TournamentService`](../../application/services/tournament_service.py) normalizes the literal string `"None"` to `NULL` on create. On **update** the normalized `None` then falls through the `if seed_generator is not None` change guard, so picking `None` on an existing tournament leaves the stored value unchanged — once set, the generator cannot be cleared from the dialog.
- **Seed Preset** — options are the tenant's `Preset` rows (loaded via `PresetService.list_selectable`), plus a `— None —` entry (id `0`) that maps back to `NULL`. `TournamentService.create_tournament`/`update_tournament` take a `preset_id`; it is validated against the tenant-scoped `PresetRepository` (a preset from another tenant is rejected), and on update `None` clears the FK while omitting the argument leaves it untouched. When set, the preset's `randomizer` overrides the Seed Generator choice.

The admin Settings tab lists each tournament's `seed_generator` read-only.

### Generation flow

1. The admin Schedule tab's match table shows a **Generate** button (casino icon) in the Seed column for rows where `tournament_seed_generator` is set and no seed exists yet ([`theme/tables/match.py`](../../theme/tables/match.py); the card/mobile layout has the same button). Clicking emits a `roll` event that ends in `on_generate_seed` in [`admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py).
2. `on_generate_seed` calls `MatchScheduleService.generate_seed(match_id, actor=...)`, which validates permission and state (see [API](#seedgenerationservice-api) below), then resolves the randomizer + preset — `tournament.preset` (its `randomizer` + `settings`) when the FK is set, else the legacy `tournament.seed_generator` string with no preset — and dispatches `SeedGenerationService.generate_seed(randomizer, preset)`.
3. The returned string is persisted as a [`GeneratedSeeds`](../../models/tournament.py) row and linked from the match:

   | `GeneratedSeeds` field | Value |
   |---|---|
   | `tenant` | required FK (`on_delete=CASCADE`, `related_name='generated_seeds'`) |
   | `seed_url` | the generator's return value (a URL for most randomizers; a plain string for Z1R) |
   | `seed_info` | `"Generated seed for match {id}"` |
   | `created_at` / `updated_at` | automatic timestamps |

   `Match.generated_seed` is a nullable FK to `GeneratedSeeds` (`related_name='matches'`). Note: `MatchScheduleService` passes a `tournament=` kwarg to `GeneratedSeeds.create()`, but the model defines no such field, so no tournament linkage is stored.
4. Players are DM'd the seed URL in the background via the Discord queue (respecting each user's `dm_notifications` opt-out), and an audit entry `match.seed_rolled` (`AuditActions.MATCH_SEED_ROLLED`) is written with `match_id`, `randomizer`, `preset` (the preset name, or `None` when rolled from the legacy `seed_generator`), and `seed_url`.

The seed is displayed on the home Schedule and Player tabs and in the admin match table — values matching `^https?://` render as truncated hyperlinks, anything else as plain text. The REST API exposes it as `MatchResponse.generated_seed` (`GeneratedSeedBase`: `id`, `seed_url`, `seed_info`, `created_at`) in the [`api/`](../../api/) package ([rest-api.md](rest-api.md)). The admin match dialog's **Clear Seed** button ([`match_dialog.py`](../../theme/dialog/match_dialog.py)) sets the FK back to `NULL` via `MatchService.update_match(clear_seed=True)`; the `GeneratedSeeds` row itself is not deleted.

## SeedGenerationService API

`SeedGenerationService` ([`seedgen_service.py`](../../application/services/seedgen_service.py)) is stateless — instantiate it freely; `MatchScheduleService` creates one in its constructor. See [services.md](services.md) for the surrounding service layer.

```python
AVAILABLE_RANDOMIZERS = ['alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'mmr', 'smdash', 'dk64r', 'wwr', 'test']
STUB_RANDOMIZERS = {'mmr', 'smdash', 'wwr'}
PRESET_AWARE_RANDOMIZERS = {'alttpr', 'dk64r'}          # use preset.settings when given
TRIFORCE_TEXT_RANDOMIZERS = {'alttpr'}                  # can embed community triforce texts
```

`AVAILABLE_RANDOMIZERS` is the full validity set — it drives `MatchScheduleService`'s validity check and stays whole regardless of what any tenant has configured. What a tenant may *select* is the narrower `SeedGenerationService.available_randomizers(configured)`, which drops randomizers whose credential this community has not supplied; the tournament dialog, the Presets tab, and the REST `/seeds/randomizers` catalogue all render that filtered list. See [Per-tenant credentials](#per-tenant-credentials).

### Stub randomizers

`mmr` (Majora's Mask), `smdash` (Super Metroid: DASH), and `wwr` (Wind Waker) are **registered stubs** (`STUB_RANDOMIZERS`): they are selectable on tournaments and appear in every UI/API surface that reads `AVAILABLE_RANDOMIZERS`, but their `_generate_*` methods are not yet wired to an upstream API and **raise `ValueError`** (the documented user-error contract). Rolling one from the schedule surfaces the generic "Seed generation failed" notification (the exception is caught in `MatchScheduleService.generate_seed`); under `MOCK_SEEDGEN` the mock short-circuit returns a fake permalink before the stub is reached, so they render normally in dev.

### Per-tenant credentials

A randomizer whose upstream is key-gated needs a credential, and that credential belongs to the **community**, not the deployment: each one supplies the key it was issued and is bound by the terms attached to it. This replaces the former process-wide `*_API_KEY` environment variables; there is no deployment-wide fallback.

Which credentials exist is declared once in [`application/randomizer_credentials.py`](../../application/randomizer_credentials.py), so the admin form and the availability check stay generic:

```python
@dataclass(frozen=True)
class CredentialSpec:
    randomizer: str   # 'ootr'
    key: str          # stable key persisted on RandomizerCredential.key
    label: str        # 'OoT Randomizer API key'
    help_text: str    # what it is / where a community obtains one
```

Values live in `RandomizerCredential` (`tenant`, `randomizer`, `key`, `value`), unique on `(tenant, randomizer, key)`. `value` is **plaintext at rest and guarded at the service layer** — the same contract as `RacetimeBot.client_secret`, `ChallongeConnection.access_token`, and `Webhook.secret`: `RandomizerCredentialService.list_status` reports configured-or-not and never the value, the audit entries (`randomizer_credential.set` / `.cleared`) name the credential and nothing else, and `resolve()` — the one unmasked read — is called only by `SeedGenerationService` mid-roll. Community STAFF/`PRESET_MANAGER` manage them on the admin **Randomizer Keys** tab (gated by `AuthService.can_manage_presets`); the input is write-only and a stored value is never rendered back.

The credential acts at two kinds of surface:

- **Selection** — `available_randomizers(configured)` filters the tournament dialog, the Presets tab randomizer select, and the REST `/seeds/randomizers` catalogue, where `configured` is `RandomizerCredentialService.configured_randomizers()` (a randomizer counts only when *every* credential it declares is set). A *stored* preset on an unconfigured randomizer stays valid and editable — its value is re-added to its own editor.
- **Roll time** — resolution happens inside each generator, so a missing credential raises `MissingCredentialError` (a `ValueError`) naming it. There is deliberately **no boundary pre-check**: resolution sits after the `MOCK_SEEDGEN` short-circuit, so dev and CI keep rolling every backend with no credentials at all. `MatchScheduleService.generate_seed` catches `MissingCredentialError` specifically and surfaces its message (its blanket handler still hides raw upstream text); the REST `POST /seeds` answers **400** with the message; `AsyncQualifierService.roll_permalinks` lets it propagate, aborting the batch before any permalink row is written.

To promote a stub to a real backend, replace the `ValueError("… not yet implemented.")` body with an actual generator (drop a preset under `presets/<name>/` if the upstream API takes one, and read any credential with `await self._credential(randomizer, key)` after registering a `CredentialSpec` — see [Adding a randomizer](#adding-a-randomizer-or-preset)) and remove the name from `STUB_RANDOMIZERS`. No changes to `AVAILABLE_RANDOMIZERS` or the dispatch map are needed. `dk64r` was promoted this way.

### Public methods

| Method | Behavior | Returns |
|---|---|---|
| `generate_seed(randomizer: str, preset: Optional[Preset] = None) -> str` | Convenience wrapper over `generate_seed_call` returning just the permalink. | Seed URL (or seed/flags string for Z1R). Raises `ValueError("Unsupported randomizer: …")` for unknown names, `MissingCredentialError` for an unconfigured credential, or a `SeedProviderError` subclass naming what the upstream did. |
| `generate_seed_call(randomizer, preset=None, *, surface=None) -> ProviderCall` | Looks up `randomizer` in an internal dispatch map and runs the matching private generator **inside the provider envelope** (below). For `PRESET_AWARE_RANDOMIZERS` (`alttpr`, `dk64r`), a supplied `preset` provides the settings; the other backends ignore it (still hard-coded until randomizer-coverage expansion). A keyed backend resolves this tenant's credential inside its generator, i.e. after the `MOCK_SEEDGEN` short-circuit. **Use this wherever the roll is persisted** — the returned `ProviderCall` carries the `RolledSeed` (permalink + settings as sent) plus attempts and latency, which is what a `GeneratedSeeds` row records. | `ProviderCall`. |
| `available_randomizers(configured: set[str]) -> list[str]` (classmethod) | `AVAILABLE_RANDOMIZERS` minus any randomizer not in `configured` that declares a credential. Pure and DB-free — the caller passes `RandomizerCredentialService.configured_randomizers()`. Drives the selector surfaces. | Filtered list of randomizer keys. |
| `supports_triforce_texts(generator: Optional[str]) -> bool` (classmethod) | Membership in `TRIFORCE_TEXT_RANDOMIZERS`. Four consumers: `AuthService.can_submit_triforce_text`, `TriforceTextService` (both the submit guard and the `seed_generator__in=…` tournament filter), the home **Triforce Texts** tab, and the REST `/seeds/randomizers` response field `supports_triforce_texts`. | `bool`. |
| `generate_alttpr_for_tournament(tournament_id: int, balanced: bool = True) -> str` | ALTTPR generation with a community triforce text embedded; see [below](#alttpr-tournament-generation-and-triforce-texts). Raises `ValueError` when the tournament does not exist. | ALTTPR permalink URL. |

### Dispatch targets (private generators)

| Method | Registered in dispatch map | Summary |
|---|---|---|
| `_generate_alttpr` | yes | pyz3r customizer roll from `preset.settings` when a preset is given, else the built-in `presets/alttpr/casualboots.yaml` settings |
| `_generate_ff1r` | yes | Local URL construction: random seed substituted into a fixed flags URL |
| `_generate_z1r` | yes | Local string: random seed number + fixed flags string |
| `_generate_smmap` | yes | HTTP POST to maprando.com with `presets/smmap/community_race_s4.json` |
| `_generate_ootr` | yes | HTTP POST to ootrandomizer.com with `presets/ootr/sgl25.json` |
| `_generate_dk64r` | yes | Task-queue roll against api.dk64rando.com from `preset.settings` (else `presets/dk64r/sgl.json`); needs the tenant's `dk64r.api_key` (Donkey Kong 64) |
| `_generate_mmr` | yes | **Stub** — raises `ValueError` (Majora's Mask) |
| `_generate_smdash` | yes | **Stub** — raises `ValueError` (Super Metroid: DASH) |
| `_generate_wwr` | yes | **Stub** — raises `ValueError` (Wind Waker) |
| `_generate_test` | yes | 5-second sleep, then a fixed example URL |

### The provider envelope

Every generator runs inside `application/utils/seed_provider.py`, one execution
contract for all outbound randomizer calls. Randomizer upstreams are third-party
services with no availability promise, and a seed roll is the most time-critical
thing the app does — a race is scheduled, the players are waiting, and the roll
happens minutes before.

| Rule | Value | Why |
|---|---|---|
| Per-attempt timeout | 60s | Bounds a *hang*. An ALTTPR customizer roll genuinely takes tens of seconds under load |
| Attempts | 3 | |
| Backoff | 1s, 2s | Short — someone is waiting |
| Retryable | timeout, connection error, 429, 5xx | The upstream's problem; it may pass |
| Not retryable | 4xx except 429, parse/schema errors, missing credential | Our payload's problem; it will fail identically |

Per-provider overrides live in `PROVIDER_TIMEOUTS` / `PROVIDER_ATTEMPTS`. DK64R
differs on both axes: its whole roll (submit → poll → result) legitimately runs
for minutes, so the outer budget exceeds the poll deadline rather than cutting it
short — and re-running the roll would submit a **second generation task**, so it
gets exactly one attempt.

Failures normalize into a taxonomy that all subclasses `ValueError`, which is what
lets the existing UI (`except ValueError` → `ui.notify`) and REST 400 mapping
surface them unchanged:

`SeedProviderTimeout`, `SeedProviderUnavailable`, `SeedProviderRateLimited`,
`SeedProviderInvalidRequest`, `SeedProviderBadResponse` — each carrying
`provider`, `operation`, `attempts`, `status_code` and the provider's own message.

### Error behavior

`SeedGenerationService` **raises**; it never returns error tuples:

- `ValueError` — unsupported randomizer name, or unknown tournament id (tournament variant). `MissingCredentialError` (a `ValueError`) when the tenant has not configured a credential the backend needs.
- A `SeedProviderError` subclass for anything the upstream did — already retried where retrying could help, and already bounded.

`MatchScheduleService.generate_seed(match_id, actor)` is the boundary that converts everything into a `(success: bool, message: str, seed_url: Optional[str])` tuple for the UI:

| Outcome | Tuple |
|---|---|
| Concurrent click (per-match `asyncio.Lock` in class-level `_seed_locks` already held) | `(False, "Seed generation already in progress for this match", None)` |
| Actor fails `AuthService.can_run_match` | `(False, "You do not have permission to roll a seed for this match", None)` |
| Match already has a seed | `(False, "A seed has already been generated for this match", None)` |
| Neither `tournament.preset` nor `tournament.seed_generator` is set | `(False, "No seed generator configured for this tournament", None)` |
| Generator not in `AVAILABLE_RANDOMIZERS` | `(False, "Seed generator '…' not found", None)` |
| A `SeedProviderError` (upstream down / rate-limiting / rejected the settings) | `(False, str(e), None)` — the envelope's curated message, so the reader can tell "try again in a minute" from "this preset will never roll" |
| Any other exception during generation | `(False, "Seed generation failed. Please check the server logs.", None)` |
| Success | `(True, "Seed generated successfully for match ID {id}", seed_url)` |

The UI maps these to `ui.notify` colors and silently skips the "already in progress" case.

## Supported randomizers

| Key | Game | Upstream | Preset file | Credential | Return shape | Notes |
|---|---|---|---|---|---|---|
| `alttpr` | A Link to the Past Randomizer | alttpr.com via [pyz3r](https://github.com/tcprescott/pyz3r) | [`presets/alttpr/casualboots.yaml`](../../presets/alttpr/casualboots.yaml) (fallback when no preset) | — | `https://alttpr.com/h/<hash>` | `ALTTPR.generate(settings, endpoint='/api/customizer')` — the customizer endpoint is required because these presets define a custom item pool and starting equipment |
| `ff1r` | Final Fantasy 1 Randomizer | none (URL built locally) | — | — | `https://4-8-6.finalfantasyrandomizer.com/?s=<seed>&f=<flags>` | Random 8-hex-digit seed substituted into a hard-coded flags URL on the version-pinned 4.8.6 site; the site builds the game client-side, so the URL *is* the seed |
| `z1r` | Zelda 1 Randomizer | none (string built locally) | — | — | `"<seed> - <flags>"` (**not** a URL, so tables render it as plain text) | Random seed number + hard-coded flags string; players enter both into the offline tool |
| `smmap` | Super Metroid Map Rando | `https://maprando.com/randomize` | [`presets/smmap/community_race_s4.json`](../../presets/smmap/community_race_s4.json) | `smmap.spoiler_token` | `https://maprando.com<seed_url>` | `multipart/form-data` with a `spoiler_token` part (never defaulted — a leaked token unlocks spoiler logs for race seeds) and a `settings` part carrying the raw preset JSON |
| `ootr` | Ocarina of Time Randomizer | `https://ootrandomizer.com/api/sglive/seed/create` | [`presets/ootr/sgl25.json`](../../presets/ootr/sgl25.json) | `ootr.api_key` | `https://ootrandomizer.com/seed/get?id=<id>` | JSON body POST with query params `key`, `version=8.3.0`, `encrypt=true` and `raise_for_status=True`; an unset key raises rather than sending `key=None` |
| `dk64r` | Donkey Kong 64 Randomizer | `https://api.dk64rando.com/api` (task queue) | [`presets/dk64r/sgl.json`](../../presets/dk64r/sgl.json) | `dk64r.api_key` | `https://dk64randomizer.com/randomizer.html?seed_id=<seed_number>` | Asynchronous submit → poll → result; see below |
| `mmr` | Majora's Mask Randomizer | none yet (**stub**) | — | — | raises `ValueError` | |
| `smdash` | Super Metroid: DASH | none yet (**stub**) | — | — | raises `ValueError` | |
| `wwr` | Wind Waker Randomizer | none yet (**stub**) | — | — | raises `ValueError` | |
| `test` | — (testing) | none | — | — | fixed example URL after a 5 s sleep | Selectable on tournaments on purpose: it exercises the full UI flow (button spinner, per-match lock, persistence, DMs) without an external call |

### dk64r

`_generate_dk64r(preset=None)` rolls against the DK64 Randomizer **task queue** at `https://api.dk64rando.com/api` — the one backend with an asynchronous submit → poll → result shape. It requires this tenant's `dk64r.api_key` credential (raises `MissingCredentialError` when unset), sent as the `X-API-Key` header on every call. See [Per-tenant credentials](#per-tenant-credentials).

Settings resolve from `preset.settings` (else the committed [`presets/dk64r/sgl.json`](../../presets/dk64r/sgl.json)). The canonical stored shape is `{"settings_string": "<string copied from dk64randomizer.com>"}` — the site's own portable preset format; a full settings JSON dict is also accepted and submitted as-is. An optional `"_branch": "dev"` key routes calls to the `dev` branch/host (default `stable`) and is stripped before anything is sent; an unrecognised value raises **before** the first HTTP call. The flow: `POST /convert_settings` (settings-string shape only — expands it to the full settings JSON), `POST /submit-task` → `task_id`, then `GET /task-status/{task_id}` every 5 s until `finished`. Any non-200 response, a `failed` or unrecognised status, a `finished` whose `result` is not a dict, a missing `seed_number`, or the 10-minute deadline each raise `ValueError`. The `result.seed_number` becomes the player-facing permalink. Spoiler behavior is whatever the preset encodes (Wizzrobe trusts the preset).

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

## Presets (DB-backed)

Presets are tenant-authored `Preset` rows (`randomizer`, `name`, `settings` JSON, `description`), managed on the admin **Presets** tab via [`PresetService`](../../application/services/preset_service.py) (CRUD gated by `AuthService.can_manage_presets` — STAFF, `PRESET_MANAGER`, super-admin, or the system actor). A tournament links one through its `preset` FK; when set, seed generation resolves the preset's `randomizer` + `settings` and it overrides the legacy `seed_generator` string.

The committed `presets/` files remain as **built-in starting rows**: `PresetService.import_builtins` (the "Import Built-ins" button) parses them and inserts any not already present (idempotent, matched by `(randomizer, name)`).

```
presets/                       # built-in files imported into the Preset table
├── alttpr/
│   ├── casualboots.yaml       # also the _generate_alttpr fallback when no preset
│   └── sglive2025.yaml
├── dk64r/
│   └── sgl.json               # _generate_dk64r fallback (settings-string shape; placeholder value)
├── ootr/
│   └── sgl25.json             # used by _generate_ootr (hard-coded until coverage expansion)
└── smmap/
    └── community_race_s4.json # used by _generate_smmap (hard-coded until coverage expansion)
```

For ALTTPR-style files the payload lives under a top-level `settings` key (with sibling `goal_name`/`description`/`customizer` metadata); `import_builtins` stores that `settings` subtree so it is handed to the randomizer unchanged. Other backends store the whole parsed file as `settings`. Only the `PRESET_AWARE_RANDOMIZERS` (`alttpr`, `dk64r`) read `preset.settings`; the other generators still open their hard-coded paths.

## Adding a randomizer or preset

1. Drop a settings file under `presets/<randomizer>/` if the upstream API takes one (skip for purely local generators like `ff1r`/`z1r`).
2. Add an `async def _generate_<name>(self) -> str` to [`seedgen_service.py`](../../application/services/seedgen_service.py) — or `(self, preset: Optional[Preset] = None)` if it consumes preset settings — that calls the upstream service with `aiohttp` (never blocking `requests`) and returns the seed URL/string. Read any credential with `await self._credential('<name>', '<key>')`, which raises a clear `MissingCredentialError` when the community has not set it (see `_generate_ootr`).
3. Register the name in **both** `AVAILABLE_RANDOMIZERS` and the `generator_map` inside `generate_seed` — a method alone is unreachable — and, for a preset-consuming backend, in `PRESET_AWARE_RANDOMIZERS`. Omit that last one and `generate_seed` calls the generator with no arguments, so it silently rolls its committed default forever.
4. Register a `CredentialSpec` for each credential in [`application/randomizer_credentials.py`](../../application/randomizer_credentials.py) — that alone puts it on the admin **Randomizer Keys** tab and into `available_randomizers`. No environment variable, and nothing to add to the deployment.
5. Select the new name as the tournament's Seed Generator in the tournament dialog; the admin schedule's Generate button picks it up with no further wiring. Add a row to the [Supported randomizers](#supported-randomizers) table.

To change which settings an ALTTPR tournament rolls, author or edit a `Preset` on the admin **Presets** tab and select it on the tournament — no code change. For the still-hard-coded backends, edit the path in the `_generate_*` method (and `generate_alttpr_for_tournament` for ALTTPR, which loads `casualboots.yaml` independently).

Related: [services.md](services.md) (service layer), [data-model.md](data-model.md) (`GeneratedSeeds`, `Match`, `Tournament` schemas), [frontend.md](frontend.md) (match table internals).
