# DK64 Randomizer backend (`dk64r`) — implementation plan

> Sub-plan of [PR 11 — randomizer coverage expansion](pr-11-randomizer-coverage.md)
> ("several small PRs, one per randomizer family"). Status: **design settled**
> (see [Decisions](#decisions-from-planning-review)) — ready to implement once
> the `DK64R_API_KEY` is issued and the built-in preset payload is supplied
> (the two remaining [open questions](#open-questions)).

**Goal:** promote the registered `dk64r` stub
([seed-generation.md](../../reference/seed-generation.md#stub-randomizers)) to a
real backend against the DK64 Randomizer API at `api.dk64rando.com`, so a
tournament or qualifier pool with a `dk64r` preset rolls a real seed from the
admin schedule with no further wiring.

## Upstream API

Base URL `https://api.dk64rando.com/api`; every endpoint accepts an optional
`branch=stable|dev` query parameter (we pin `stable`). Contract verified
against three sources that agree everywhere they overlap: the DK64R swagger
(`openapi: 3.0.0`), the dk64randomizer.com web client JS, and the server
source ([2dos/DK64-Randomizer](https://github.com/2dos/DK64-Randomizer) —
`controller/app.py` + `worker/tasks.py`). Where the swagger is loose or wrong,
the server code below is authoritative.

**Authentication (omitted from the swagger, enforced by the server):** every
endpoint except `/current_total` is wrapped in `@enforce_api_restrictions()`,
which requires **either** a `Referer` on the allowlist
(`https://dk64randomizer.com/`, `https://dev.dk64randomizer.com/`) **or** a
valid **`X-API-Key`** header (keys provisioned server-side in
`api_keys.cfg`). The browser client passes silently via its referer; a
server-to-server caller like SGLMan must send an API key issued by the DK64R
team. Never spoof the referer — request a key (see open questions).

| Endpoint | Used by us | Contract (verified) |
|---|---|---|
| `POST /convert_settings` | yes | Body `{"settings": "<string>"}` — always a *string*: either a site "settings string" or a settings JSON dict serialized with `json.dumps`. **Bidirectional**: a settings string converts to the full settings JSON object; a JSON-as-string converts to `{"settings_string": "..."}`. One call converts one direction — it does not normalize a dict to a dict. |
| `POST /submit-task` | yes | Body `{"settings_data": "<settings JSON, as a string>"}` → `{task_id, status: "queued", priority}`. Priority is keyed on caller IP: first submission, or >300 s since the last, goes to the **High** queue; anything sooner goes to **Low**. `400` = missing `settings_data`/wrong content type. |
| `GET /task-status/{task_id}` | yes | Statuses: `queued` (with integer `position`), `started`, `finished`. On `finished`, `result` is an **object** (the swagger's `type: string` is wrong): `{"patch": <base64 zip>, "hash": <in-game visual hash>, "seed_number": <int>, "password"?: ...}` from the worker's `generate_seed`. A crashed task returns **HTTP 500** with the exception text; the web client also defends against a `failed` status inside a 200, so handle both. `404` = unknown task. The client polls every 5 s. |
| `GET /get_seed?hash=` | no | Serves `generated_seeds/<hash>.lanky` — the `hash` parameter is matched against the **filename**, and the worker stores files by **`seed_number`**. So the "hash"/"seed id" in URLs is `result["seed_number"]`, not `result["hash"]` (the visual in-game hash). We never fetch the file; the permalink below makes the site do it. |
| `GET /get_spoiler_log?hash=` | no (v1) | Spoiler log JSON, gated by an `Unlock Time` field the worker writes into the stored log: `425` until it passes. Out of scope — SGLMan stores no spoiler for any backend. |
| `GET /current_total` | probe only | Total-seeds counter. **The only undecorated endpoint** — the health-probe target that works without a credential. |
| `GET /get_version`, `GET /get_presets`, `GET /get_selector_info` | no | Version / site preset list (each entry: `name`, `description`, `settings_string`) / settings-UI metadata. All key-gated. Notable: the site's own presets travel as **settings strings**, confirming that format as the portable one. |

### Player-facing permalink (verified)

The web client's `try_to_load_from_args` reads `?seed_id=<value>` from the
page URL, fetches that value as the `hash` argument of `/get_seed`, and
patches the player's locally-cached ROM in-browser. Combined with the
filename-lookup above, the shareable seed link is:

```
https://dk64randomizer.com/randomizer.html?seed_id=<result["seed_number"]>
```

That URL is what `_generate_dk64r` returns and what lands in
`GeneratedSeeds.seed_url` (rendered as a hyperlink by the existing match
tables, DM'd to players unchanged). Cosmetics stay a player-side concern —
the site applies them locally when the player opens the link, exactly as it
does for its own seed-id links.

Unlike `ootr`/`smmap` (single synchronous POST), DK64R is a **task queue**:
submit → poll → result. That asynchrony is the one genuinely new shape this
backend introduces to `SeedGenerationService`.

## Generation flow

New `_generate_dk64r(preset: Optional[Preset]) -> str` in
[`seedgen_service.py`](../../../application/services/seedgen_service.py),
following the existing backend pattern (async `aiohttp`, `ValueError` for
user-surfaceable failures):

1. **Credential.** Read `DK64R_API_KEY` from the environment; raise
   `ValueError('DK64R_API_KEY is not configured.')` when missing (the
   `OOTR_API_KEY` pattern). Send it as `X-API-Key` on every call.
2. **Resolve settings.** `preset.settings` when a preset is supplied, else the
   committed default `presets/dk64r/<default>.json` (payload pending — see
   open questions). Canonical stored shape:
   `{"settings_string": "<string copied from dk64randomizer.com>"}` — the same
   format the site's own presets use, copy-paste authorable with no
   Presets-tab UI change, and it survives upstream version changes because
   `/convert_settings` re-expands it against the branch's current generator.
   A full settings JSON dict is also accepted (any dict without
   `settings_string` is treated as one) and submitted as-is.
3. **Branch.** Pop an optional `_branch` key (`'stable'` default) from a copy
   of the settings — a preset opts into `dev` by storing `"_branch": "dev"`.
   The value is the `branch=` query param on every API call below; it is
   stripped from the payload before anything is sent upstream. Validated
   against `{'stable', 'dev'}` (anything else → `ValueError`).
4. **Convert** (settings-string shape only). `POST /convert_settings?branch=…`
   with `{"settings": settings_string}` → the full settings JSON object.
   Full-JSON presets skip this step — converting a dict yields a settings
   *string* (the other direction), not a normalized dict.
5. **Submit.** `POST /submit-task?branch=…` with
   `{"settings_data": json.dumps(settings_dict)}` → `task_id`. `400`/`403`
   become `ValueError` carrying the upstream `error` message.
6. **Poll.** `GET /task-status/{task_id}?branch=…` every `POLL_INTERVAL` (5 s —
   the reference client's own cadence) until `finished`, bounded by
   `GENERATION_TIMEOUT` (10 min) — both module constants, not env vars, since
   they are not credentials. HTTP `500`, a defensive `failed` status, or
   timeout → `ValueError`; unrecognized terminal states are treated as
   failures with the raw status in the message. `queued`'s `position` is
   ignored in v1 (no progress channel exists for any backend).
7. **Return**
   `https://dk64randomizer.com/randomizer.html?seed_id={result["seed_number"]}`.
   (A `dev`-branch preset returns the `dev.dk64randomizer.com` host to match.)

Spoiler behavior is left to the preset payload (**trust the preset** —
consistent with every other backend); SGLMan does not rewrite
`generate_spoilerlog` / `delayed_spoilerlog_release`.

The inline await is deliberate: `MatchScheduleService.generate_seed` already
serializes per-match rolls behind an `asyncio.Lock` and the Generate button
shows a spinner, so a queue wait of a few minutes degrades gracefully; the
timeout bounds the worst case.

**Bulk-roll caveat:** the High/Low priority split is keyed on caller IP with a
300 s cooldown, so an async-qualifier "roll N seeds" burst puts every seed
after the first into the Low-priority queue from one server IP. Fine for
per-match rolls; for large pools, expect the later seeds to queue longer
(worth asking the DK64R team whether API-key callers can bypass the cooldown —
see open questions).

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
tuple) — missing `DK64R_API_KEY`, unconvertible settings, submit rejection
(`400`/`403`), task crash (HTTP 500 or `failed`), poll timeout. Transport
errors propagate from `aiohttp` as today. `MOCK_SEEDGEN` already
short-circuits `dk64r` before the generator is reached, so dev environments
and the browser-validation loop keep working unchanged.

### Race safety

Spoiler availability is controlled entirely inside the settings payload, and
the worker turns it into the stored log's `Unlock Time`:

- `generate_spoilerlog` **true** → log unlocked immediately.
- false + `delayed_spoilerlog_release: <hours>` → log unlocks that many hours
  after generation (the racer-friendly mode).
- false + no delay → locked ~5 years (effectively never).

Race-safety therefore lives in the **preset payload**, authored by the tenant
— consistent with every other backend, where SGLMan trusts the preset rather
than rewriting settings. Whether SGLMan should nonetheless force-override the
spoiler keys on every roll is an open question.

## Design brief (per /plan-feature)

### 1. Feature flag — **yes: `DK64_RANDOMIZER`**

Decided: gate `dk64r` behind a per-tenant feature flag. The governing
principle (worth documenting as a convention, see §6) is broader than this one
backend:

> **Any randomizer that requires an API key to generate a seed is gated behind
> a per-tenant feature flag.** The key's owner attaches usage restrictions we
> must agree to, and a per-tenant availability gate is how a super-admin
> records that a given community is authorized (and has agreed) to use it.

So this is an **authorization gate**, not a beta toggle — which is exactly the
"authorization-style gate at the entry surfaces" the flag system is for.

- **Registry.** Add `FeatureFlag.DK64_RANDOMIZER` to
  [`models/enums.py`](../../../models/enums.py) and a `FeatureFlagSpec` to
  [`application/feature_flags.py`](../../../application/feature_flags.py)
  (category `'Online tournaments'`; **`established=False`** — it ships dark and
  requires the key + agreement, so there is **no** migration-30-style
  backfill, and therefore **no migration at all**).
- **The gating shape is new.** Every existing flag guards a whole
  page/tab/router; `dk64r` is one *value* in a shared "Seed Generator" select.
  So the gate is a per-value filter of the randomizer list, applied at the two
  places a tenant *selects* a randomizer, plus the roll boundary:
  - A `FLAG_GATED_RANDOMIZERS = {'dk64r': FeatureFlag.DK64_RANDOMIZER}` map and
    a `SeedGenerationService.available_randomizers(live_flags: set[FeatureFlag])
    -> list[str]` helper that drops any gated randomizer whose flag is not in
    `live_flags`. `AVAILABLE_RANDOMIZERS` stays the full set (validity is not
    availability — a stored `dk64r` preset is still a valid row).
  - **Tournament dialog** ([`tournament_edit_dialog.py`](../../../theme/dialog/tournament_edit_dialog.py))
    — `randomizer_choices = ['None'] + available_randomizers(live)` where
    `live = await FeatureFlagService().enabled_flags()`.
  - **Presets tab** ([`admin_presets.py`](../../../pages/admin_tabs/admin_presets.py))
    — the create/edit randomizer `ui.select` uses `available_randomizers(live)`.
  - **Roll boundary** ([`match_schedule_service.py`](../../../application/services/match_schedule_service.py))
    — `generate_seed` gains, next to its existing `can_transition_match`
    authorization check, an `is_enabled(DK64_RANDOMIZER)` gate **when the
    resolved randomizer is flag-gated**, returning the standard
    `(False, "…", None)` tuple if off. This is the deliberate exception to
    "no flag read in a service": it lives at the roll's orchestration/authz
    boundary (which already does auth), not in a low-level transaction, and it
    is what actually stops a keyed API call — enforcing the usage agreement at
    call time rather than trusting that the config was created while the flag
    was on.

### 2. Model sketch + tenant impact

**No new or changed models; no migration; no new leak test.** The existing
tenant-scoped `Preset` (`randomizer='dk64r'`, `settings` JSON) and
`GeneratedSeeds` rows carry everything. The new `FeatureFlag` member is an enum
value stored in the existing `TenantFeatureFlag.flag` column — no schema
change, and no backfill because it ships dark. `tests/test_feature_flags.py`
enforces enum↔registry parity, so the enum member and the `FeatureFlagSpec`
must land together.

### 3. Layer touchpoints

- **Service** — `_generate_dk64r` + dispatch edits + the
  `FLAG_GATED_RANDOMIZERS` map / `available_randomizers` helper in
  `seedgen_service.py`; the roll-boundary flag gate in
  `match_schedule_service.py`. No new `AuditActions`/`EventType`:
  `match.seed_rolled` already covers the roll.
- **UI** — the two selector filters above (tournament dialog, Presets tab).
  The admin **Features** tab lists the new flag automatically from the
  registry; the Generate button and async-qualifier roll-N need no change.
- **REST API** — `require_feature` is per-router and `dk64r` is a field value,
  not a router, so it does not apply directly. The preset-create and
  tournament-create endpoints accept a `randomizer`/`seed_generator` field: the
  **roll-boundary gate is the hard backstop** for anything configured via the
  API while the flag is off (no keyed call happens). Optionally, mirror the
  selector filter as field validation in those create/update paths so the API
  rejects a gated randomizer up front with a clear 4xx rather than only
  failing at roll time — recommended for parity, but the roll gate is what
  guarantees safety.
- **Service health** — register
  `_Probe('seedgen_dk64', 'DK64 Randomizer (api.dk64rando.com)', 'seedgen', …)`
  in `service_health_service.py`, probing
  `https://api.dk64rando.com/api/current_total` — the one endpoint that needs
  no credential. Optionally surface a `CREDENTIAL_WARNING` when
  `DK64R_API_KEY` is unset (the web-push/VAPID probe pattern).
- **Env/config** — `DK64R_API_KEY` documented in
  [deployment.md](../../deployment.md) + `.env.example` and added to the
  deployment environment once issued.
- **Built-in preset** — `presets/dk64r/<name>.json` with the SGL community
  settings (payload pending). `PresetService.import_builtins` discovers it
  automatically (`dk64r` is already in `AVAILABLE_RANDOMIZERS`).
- **Repository / bot** — none.

### 4. Test plan

`tests/services/test_seedgen_service.py` (no network — conftest socket guard;
all HTTP mocked):

- Drop `dk64r` from the two stub parametrizations; keep `test_exact_membership`
  unchanged; add `dk64r` to the `MOCK_SEEDGEN` parametrization.
- New `TestGenerateDk64r`: missing `DK64R_API_KEY` → `ValueError` (the
  `OOTR_API_KEY` precedent); happy path (`settings_string` preset → convert →
  submit → poll `queued`→`started`→`finished` → URL is
  `randomizer.html?seed_id=<seed_number>` and the `X-API-Key` header is sent);
  full-JSON preset skips `/convert_settings` and submits as-is; `_branch: dev`
  routes calls to the dev branch/host and is stripped from the payload;
  no-preset fallback loads the built-in file; submit `400`/`403` →
  `ValueError`; task-status HTTP 500 → `ValueError`; defensive `failed`
  status → `ValueError`; poll timeout (patched sleep/clock) → `ValueError`.
- `available_randomizers`: `dk64r` present iff `DK64_RANDOMIZER ∈ live_flags`;
  all ungated randomizers always present.

Feature-flag coverage — `tests/test_feature_flags.py`: the parity test picks up
the new member automatically; add an assertion that `DK64_RANDOMIZER` is
**not** in `established_flags()` (ships dark). `MatchScheduleService.generate_seed`
behavior test: with the flag off, a `dk64r` tournament returns the
`(False, …, None)` tuple and makes no upstream call; with it on (and
`MOCK_SEEDGEN`), it succeeds.

No API-router or isolation tests: no new endpoints, roles, or scoped models.

### 5. Seed (dev fixture) additions

- One `dk64r` `Preset` row via `get_or_create` in the `scripts/seed_online.py`
  preset block (settings-string shape, so the fixture also documents the
  authoring path).
- Provision `DK64_RANDOMIZER` available+enabled for the dev tenant(s) in
  `scripts/seed_dev.py` so the selector actually offers `dk64r` in dev.
  (`tests/test_feature_flags.py`'s `db` fixture already turns every flag on
  for tenant 1.) Dev rolls stay on `MOCK_SEEDGEN`.

### 6. Docs touchpoints

On implementation: [feature-flags.md](../../features/feature-flags.md) (add the
`DK64_RANDOMIZER` row **and** the "API-key randomizers are flag-gated"
principle), [seed-generation.md](../../reference/seed-generation.md) (remove
`dk64r` from both stub tables, add a `dk64r` section + supported-table row +
env-var row, and note the flag gate),
[seed-rolling.md](../seed-rolling.md) coverage checklist,
[pr-11-randomizer-coverage.md](pr-11-randomizer-coverage.md) checklist,
[current-state.md](../../current-state.md), and
[deployment.md](../../deployment.md) + `.env.example` for `DK64R_API_KEY`.

## Resolved questions

Answered by verifying the swagger against the dk64randomizer.com web client
and the server source (`controller/app.py`, `worker/tasks.py`):

- **`task-status` contract** — statuses `queued`/`started`/`finished`;
  `result` is an object `{patch, hash, seed_number, password?}` (swagger's
  `string` typing is wrong); task crashes surface as HTTP 500 (the client
  also defends against a `failed` status); the client polls at 5 s.
- **Player-facing URL** —
  `https://dk64randomizer.com/randomizer.html?seed_id=<seed_number>`; the
  `/get_seed` "hash" parameter is a filename lookup and the worker names
  files by `seed_number` (`result["hash"]` is the in-game visual hash, not
  the identifier).
- **Authentication** — required for everything except `/current_total`:
  allowlisted `Referer` (browser) or `X-API-Key` (server-to-server). SGLMan
  needs an issued key → `DK64R_API_KEY`.
- **Priority queue** — IP-keyed 300 s cooldown: first/spaced submissions go
  High, rapid ones go Low. Matters for bulk qualifier rolls.
- **Polling budget** — 5 s matches the reference client; 10-min cap stands.
- **Race safety mechanics** — `generate_spoilerlog` /
  `delayed_spoilerlog_release` (hours) drive the stored log's `Unlock Time`;
  `425` until it passes.
- **Preset format** — settings strings are the site's own portable preset
  format; store `{"settings_string": ...}` canonically.

## Decisions (from planning review)

- **Feature flag: yes** — `DK64_RANDOMIZER`, per the API-key principle in §1
  (also gates the roll, not just selection).
- **Spoiler policy: trust the preset** — no SGLMan override.
- **Branch: per-preset `_branch` override** — default `stable`, opt into `dev`.
- **API key: SGL will obtain one** — `DK64R_API_KEY`; hard prerequisite to
  go live.

## Open questions

1. **API key provisioning.** SGL is obtaining an `X-API-Key` from the DK64R
   team (server-side `api_keys.cfg`). Two things to confirm while requesting
   it: (a) any usage policy that should be reflected in the flag's
   description/agreement copy, and (b) whether key-holders bypass the IP
   cooldown — otherwise a bulk qualifier "roll N" puts every seed after the
   first in the Low-priority queue from SGL's single server IP.
2. **Built-in preset payload.** Please provide the SGL community settings
   string to commit as `presets/dk64r/<name>.json` (a copy-pasted settings
   string from dk64randomizer.com is the ideal form).

Everything else (task-status contract, player permalink, auth mechanism,
priority behavior, poll cadence, spoiler mechanics, preset format) is resolved
above.
