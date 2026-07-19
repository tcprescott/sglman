# DK64 Randomizer backend (`dk64r`) — implementation plan

> Sub-plan of [PR 11 — randomizer coverage expansion](pr-11-randomizer-coverage.md)
> ("several small PRs, one per randomizer family"). Status: **proposed** — the
> [open questions](#open-questions) need answers before implementation starts.

**Goal:** promote the registered `dk64r` stub
([seed-generation.md](../../reference/seed-generation.md#stub-randomizers)) to a
real backend against the DK64 Randomizer API at `api.dk64rando.com`, so a
tournament or qualifier pool with a `dk64r` preset rolls a real seed from the
admin schedule with no further wiring.

## Upstream API

Base URL `https://api.dk64rando.com/api`; every endpoint accepts an optional
`branch=stable|dev` query parameter (we pin `stable`). Source: the DK64R
swagger (`openapi: 3.0.0`, version 1.0.0). No authentication appears in the
spec — see [open questions](#open-questions).

| Endpoint | Used by us | Purpose |
|---|---|---|
| `POST /convert_settings` | yes | Normalizes a settings payload — accepts a site "settings string" **or** a settings JSON dict (stringified) and "automatically converts as needed" — into the canonical settings JSON for the branch's current version. |
| `POST /submit-task` | yes | Body `{"settings_data": "<output of convert_settings, as a string>"}` → `{task_id, status, priority}`. Generation is **queued**, not synchronous. |
| `GET /task-status/{task_id}` | yes | `{task_id, status, result, position}`; `404` unknown task, `500` task failed. Polled until terminal. |
| `GET /get_seed?hash=` | maybe | The generated **lanky** patch file (`application/zip`). Only needed if we serve/link the file directly rather than a site permalink. |
| `GET /get_spoiler_log?hash=` | no (v1) | Spoiler log JSON; `425` = locked (race seed), `403` = denied. Out of scope initially — SGLMan stores no spoiler for any backend. |
| `GET /get_version` | probe only | API/generator version — a good health-probe target. |
| `GET /get_presets`, `GET /get_selector_info`, `GET /current_total` | no | Site preset list / settings-UI metadata / seed counter. Our presets are tenant-authored `Preset` rows, not the site's list. |

Unlike `ootr`/`smmap` (single synchronous POST), DK64R is a **task queue**:
submit → poll → fetch result. That asynchrony is the one genuinely new shape
this backend introduces to `SeedGenerationService`.

## Generation flow

New `_generate_dk64r(preset: Optional[Preset]) -> str` in
[`seedgen_service.py`](../../../application/services/seedgen_service.py),
following the existing backend pattern (async `aiohttp`, `ValueError` for
user-surfaceable failures):

1. **Resolve settings.** `preset.settings` when a preset is supplied, else the
   committed default `presets/dk64r/<default>.json` (file to be provided — see
   open questions). Two accepted shapes, both stored as the JSON dict
   `Preset.settings` already requires:
   - `{"settings_string": "<string copied from dk64randomizer.com>"}` — the
     copy-paste-friendly authoring path; no Presets-tab UI change needed.
   - a full DK64R settings JSON object (e.g. captured from a previous
     `convert_settings` output).
2. **Convert.** `POST /convert_settings?branch=stable` with the settings string
   (or the JSON dict serialized to a string). Always convert, even for JSON
   presets — it re-normalizes the payload against the branch's current
   generator version, which is what keeps stored presets working across
   upstream releases.
3. **Submit.** `POST /submit-task?branch=stable` with
   `{"settings_data": json.dumps(converted)}` → `task_id`. A `400` (invalid
   payload) becomes `ValueError` with the upstream error message.
4. **Poll.** `GET /task-status/{task_id}` every `POLL_INTERVAL` (5 s) until a
   terminal status, bounded by `GENERATION_TIMEOUT` (10 min) — both module
   constants, not env vars, since they are not credentials. On timeout, task
   `500`, or a terminal failure status: `ValueError`. The exact status
   vocabulary and the shape of `result` are unconfirmed — see open questions;
   the implementation treats any unrecognized terminal state defensively as a
   failure with the raw status in the message.
5. **Return the player-facing seed reference** built from the seed hash in
   `result`. The canonical shape is an open question; the fallback is the
   direct patch-file download `https://api.dk64rando.com/api/get_seed?hash=<hash>`.
   Whatever is chosen is stored verbatim in `GeneratedSeeds.seed_url` and
   rendered by the existing match tables (hyperlink when it matches
   `^https?://`).

The inline await is deliberate: `MatchScheduleService.generate_seed` already
serializes per-match rolls behind an `asyncio.Lock` and the Generate button
shows a spinner, so a queue wait of a few minutes degrades gracefully; the
timeout bounds the worst case. Surfacing the queue `position` to the UI would
require a progress channel that no other backend has — out of scope.

### Dispatch changes

- Remove `'dk64r'` from `STUB_RANDOMIZERS`; `AVAILABLE_RANDOMIZERS` and the
  `generator_map` entry already exist.
- `generate_seed` currently special-cases only ALTTPR for preset pass-through.
  Introduce `PRESET_AWARE_RANDOMIZERS = {'alttpr', 'dk64r'}` and hand `preset`
  to any generator in that set — the first concrete step of the PR 11 pattern
  (each promoted backend joins the set instead of growing another `if`).

### Failure modes

All converted to `ValueError` (the documented user-error contract, surfaced by
`MatchScheduleService` as the `(False, "Error generating seed: …", None)`
tuple) — invalid/unconvertible settings, submit rejection, task failure,
poll timeout. Transport errors propagate from `aiohttp` as today.
`MOCK_SEEDGEN` already short-circuits `dk64r` before the generator is reached,
so dev environments and the browser-validation loop keep working unchanged.

## Design brief (per /plan-feature)

### 1. Feature flag

**None (recommendation — confirm).** This promotes an existing stub inside the
seed-generation subsystem, which is not flag-gated for any other backend;
gating one randomizer would be a retrofit CLAUDE.md says to avoid. Rollout
control already exists per tenant: a tournament only rolls `dk64r` if its
staff select the generator/preset.

### 2. Model sketch + tenant impact

**No new or changed models; no migration; no new leak test.** The existing
tenant-scoped `Preset` (`randomizer='dk64r'`, `settings` JSON) and
`GeneratedSeeds` rows carry everything. Seed-coverage tests are unaffected.

### 3. Layer touchpoints

- **Service** — the whole change: `_generate_dk64r` + dispatch edits in
  `seedgen_service.py` as above. No new `AuditActions`/`EventType`:
  `match.seed_rolled` already covers the roll, and its absence of
  backend-specific events is deliberate.
- **Repository / UI / API / bot** — none. The tournament dialog, Presets tab,
  admin schedule Generate button, async-qualifier roll-N, and the REST seed
  surfaces all read `AVAILABLE_RANDOMIZERS`/`Preset` and pick this up for free.
- **Service health** — register
  `_Probe('seedgen_dk64', 'DK64 Randomizer (api.dk64rando.com)', 'seedgen', …)`
  in `service_health_service.py`. Prefer probing
  `https://api.dk64rando.com/api/get_version` over the bare host root if
  `_http_reachable` would count the root's non-200 as down.
- **Built-in preset** — `presets/dk64r/<name>.json` with the SGL community
  settings (payload pending). `PresetService.import_builtins` discovers it
  automatically (`dk64r` is already in `AVAILABLE_RANDOMIZERS`).

### 4. Test plan

`tests/services/test_seedgen_service.py` (no network — conftest socket guard;
all HTTP mocked):

- Drop `dk64r` from the two stub parametrizations; keep `test_exact_membership`
  unchanged; add `dk64r` to the `MOCK_SEEDGEN` parametrization.
- New `TestGenerateDk64r`: happy path (convert → submit → poll
  queued→complete → returned URL contains the hash); `settings_string` preset
  converted via `/convert_settings`; full-JSON preset accepted; no-preset
  fallback loads the built-in file; submit `400` → `ValueError`; task failure
  status → `ValueError`; poll timeout (patched sleep/clock) → `ValueError`;
  unrecognized terminal status → `ValueError`.

No API-router or isolation tests: no new endpoints, roles, or scoped models.

### 5. Seed (dev fixture) additions

One `dk64r` `Preset` row via `get_or_create` in the
`scripts/seed_online.py` preset block (settings-string shape, so the fixture
also documents the authoring path). Dev rolls stay on `MOCK_SEEDGEN`.

### 6. Docs touchpoints

On implementation: [seed-generation.md](../../reference/seed-generation.md)
(remove `dk64r` from both stub tables, add a `dk64r` section + supported-table
row), [seed-rolling.md](../seed-rolling.md) coverage checklist,
[pr-11-randomizer-coverage.md](pr-11-randomizer-coverage.md) checklist,
[current-state.md](../../current-state.md). [deployment.md](../../deployment.md)
/ `.env.example` only if an API credential turns out to exist.

## Open questions

1. **Player-facing seed URL.** What should `GeneratedSeeds.seed_url` hold —
   a dk64randomizer.com permalink (what is the exact pattern for retrieving a
   generated seed by hash?), the direct
   `api.dk64rando.com/api/get_seed?hash=<hash>` zip download, or the bare hash
   as plain text (the `z1r` precedent)? How do players actually patch for a
   race today?
2. **`task-status` contract.** The swagger types `status`/`result` only as
   strings. What are the actual status values, and does `result` carry the seed
   hash directly or a JSON payload? Is there a reference implementation (e.g.
   SahasrahBot's DK64 support) to mirror?
3. **Race safety.** Which settings key(s) control spoiler-log generation and
   the `425` spoiler lock? Should SGLMan force race-locked seeds regardless of
   what the preset says (the way race seeds demand it), or trust the preset?
4. **Authentication.** The spec shows none. Is `submit-task` genuinely
   anonymous, or is there a key for priority/race generation that SGL should
   use (→ env var + deployment docs + credential-warning probe)?
5. **Branch pinning.** Always `stable`, or should a preset be able to opt into
   `dev` (e.g. an optional `_branch` key in `Preset.settings`)?
6. **Built-in preset payload.** Can you provide the SGL community settings
   (settings string is fine) to commit as `presets/dk64r/<name>.json`?
7. **Feature flag.** Confirm the no-flag recommendation in §1.
8. **Polling budget.** Are 5 s intervals with a 10-minute cap acceptable for
   the Generate-button UX, or does DK64R's queue routinely run longer?
