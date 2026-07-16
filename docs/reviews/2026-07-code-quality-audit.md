# Code Quality Audit — DRY & Engineering Practices

**Date:** 2026-07-16
**Commit audited:** `a402d19` (origin/main) — with the preceding week's work (`a3e40d1..a402d19`, ~42k lines across ~380 files: racetime.gg integration, async qualifiers, SpeedGaming ETL, Discord scheduled events, per-tenant feature flags, the `models.py`→`models/` split, service-module splits, REST API expansion, and the URL-scheme refactor).
**Scope:** whole codebase, not just recent changes. Each finding is labelled **[new]** (introduced in the last week) or **[pre-existing]**.
**Status:** report only — no code was changed. Remediation is delegated to follow-up agents.

## How to read this

Findings are grouped by theme and ranked by severity within each group. Every finding carries a `file:line` reference and a one-line suggested fix (not implemented). Line numbers are anchored to `a402d19`; the handful of files the upstream URL-refactor and feature-flag PRs moved have been re-verified at their current lines.

Two framing notes:

- The codebase is, on the whole, **disciplined**. There are zero module-size violations, no ORM writes in the presentation layer, no bare `asyncio.create_task`, a consistent service→`ValueError`→UI-notify error contract, and genuinely shared helpers in the right places (`utils/ssrf.py`, `_crew_repository.py`, `api/_match_view.py`, `theme/dialog/_helpers.py`). The problems below are drift, not rot.
- The dominant pattern is **copy-paste from a good template**. Most new modules were cloned from a solid sibling and then diverged. That is why the same five or six shapes recur across services, repositories, routers, tabs, and tests — and why a small number of extractions would remove a large fraction of the total debt.

---

## Executive summary

| # | Theme | Severity | Age | Where |
|---|---|---|---|---|
| 1 | Stream-room dialog crashes on open (`AttributeError`) | **High** | pre-existing | `theme/dialog/stream_room_dialog.py:14` |
| 2 | Blocking Discord HTTP on the shared event loop during login | **High** | pre-existing | `pages/auth.py:209-211` |
| 3 | Stub randomizers raise `NotImplementedError` on user-reachable paths | **High** | new | `application/services/seedgen_service.py:240-255` |
| 4 | Twitch/racetime client + link service copy-paste (~230 lines) | **High (DRY)** | new | `application/utils/`, `application/services/` |
| 5 | Repository CRUD boilerplate stamped into ~15 repositories | **High (DRY)** | mixed | `application/repositories/` |
| 6 | Background-worker loop scaffolding cloned 5× | **High (DRY)** | new | `application/services/*_worker.py` |
| 7 | `PlayerAvailability*` is a wholesale clone of `VolunteerAvailability*` | **High (DRY)** | pre-existing | `application/services/`, `application/repositories/` |
| 8 | API: `_load_*_or_404` × 12 + systemic double-fetch + 404/400 drift | **High (DRY)** | mostly new | `api/routers/`, `api/dependencies.py` |
| 9 | Admin CRUD-tab scaffolding cloned into 4 new tabs (8 sub-patterns) | **High (DRY)** | new | `pages/admin_tabs/` |
| 10 | `reports/telemetry.py` is a structural clone of `reports/audit.py` | **High (DRY)** | new | `pages/admin_tabs/reports/` |
| 11 | Test fixture duplication (stub queue ×11, two-tenant ×26, app ×21) | **High (DRY)** | mixed | `tests/` |
| 12 | Real outbound HTTPS calls in a CI test | **High** | new | `tests/test_api_service_health.py:76-84` |
| 13 | `CLAUDE.md` says the `Role` enum has 7 members; it has 11 | **High (docs)** | new | `CLAUDE.md:125` |

**The five extractions that remove the most debt:**

1. A `TenantScopedRepository[T]` base + a `require_found(obj, label)` service helper (touches the most files: ~15 repos, 40+ inline load-or-raise blocks).
2. A shared OAuth-identity client + a provider-parameterized `IdentityLinkService` (collapses the single largest copy-paste — Twitch and racetime).
3. A `NotFoundError → 404` mapping in `ServiceErrorRoute` (simultaneously kills the 12-way `_load_*_or_404` copy-paste, the systemic double-fetch, and the 404-vs-400 inconsistency).
4. A shared admin-CRUD-tab component in `theme/` (page shell, `current_actor()`, `ServiceTableView`, actions-slot builder) that the four new tabs converge onto.
5. Hoist `stub_discord_queue`, an `app` fixture, and a `two_tenants` fixture into `tests/conftest.py`.

---

## 1. Correctness bugs surfaced during the audit

These are not DRY issues, but the review surfaced them and they are the most urgent items. All three are verified against current `main`.

### 1.1 [High, pre-existing] Stream-room "Assign Stage" dialog throws `AttributeError` on open
`theme/dialog/stream_room_dialog.py:14`
```python
stream_rooms = await self.stream_room_repository.get_all()
```
`BaseMatchDialog.__init__` defines only `self.stream_room_service` (`theme/dialog/match_dialog.py:53`); there is no `stream_room_repository` attribute anywhere in the hierarchy. Commit `2216dc5` ("Route presentation reads through services") renamed the attribute in the base class but missed this subclass. Every open of the dialog — wired from the stream-room cell in `pages/admin_tabs/admin_schedule.py:177-183` — raises. The same file at `match_dialog.py:348` shows the correct call: `await self.stream_room_service.get_all_stream_rooms()`. (Doubly wrong: presentation→repository is a layering violation even if the attribute existed.)

### 1.2 [High, pre-existing] Blocking Discord calls freeze the event loop during OAuth login
`pages/auth.py:209-211`
```python
access_token = discordClient.oauth.get_access_token(code, _redirect_uri()).access_token
bearer_client = APIClient(access_token, bearer=True)
current_user = bearer_client.users.get_current_user()
```
`zenora.APIClient` is synchronous (`requests`-based). Two network round-trips to Discord run inside `async def oauth_callback`, blocking the single shared event loop — and therefore every other connected user's UI — for their duration. The async-safety guardrail hook only pattern-matches `import requests` / `time.sleep`, so this slips through. Fix: `asyncio.to_thread(...)` or an async `httpx` token exchange.

### 1.3 [High, new] Stub randomizers raise `NotImplementedError` on user-reachable paths
`application/services/seedgen_service.py:240-255` (added in `ef57580`). The four stubs (`_generate_mmr`, `_generate_smdash`, `_generate_dk64r`, `_generate_wwr`) `raise NotImplementedError`, and all four are listed in `AVAILABLE_RANDOMIZERS` (`:30-41`) — so they are selectable in the tournament dialog (`theme/dialog/tournament_edit_dialog.py:54`) and valid for preset creation (`preset_service.py:183`). A `STUB_RANDOMIZERS` set already exists (`:45`) but is never used to filter the selectable list. Downstream failures:
- **Async qualifier roll:** `AsyncQualifierService.roll_permalinks` (`async_qualifier_service.py:373`) propagates the `NotImplementedError`; the roll dialog catches only `(ValueError, PermissionError)` (`admin_qualifiers.py:328`) → unhandled UI exception. Permalinks rolled before the raise persist with **no audit row** (the `write_log` after the loop is never reached).
- **REST:** `POST /seeds` (`api/routers/seeds.py:43`) → HTTP 500, because `ServiceErrorRoute` only maps `PermissionError`/`ValueError` (`api/dependencies.py:191-213`).
- **Match seed:** survives only via the blanket `except Exception` in `MatchScheduleService.generate_seed` (`match_schedule_service.py:285-290`) — returning "check the server logs" plus a Sentry error for a configuration the dropdown itself offered.

Fix: raise `ValueError("… not yet implemented")` from the stubs (the documented user-error contract), or filter `STUB_RANDOMIZERS` out of the selectable list.

---

## 2. DRY violations (the core ask)

### 2A. Services, repositories, utilities

#### High

**[new] 2A.1 — Twitch and racetime transport + link code is copy-pasted (~230 lines).**
The identity integrations were built by cloning Twitch into racetime days later.
- Clients: `application/utils/twitch_client.py` vs `application/utils/racetime_client.py` — `build_authorize_url` and `_opt_str` are byte-identical (`twitch_client.py:31-45` vs `racetime_client.py:36-49`); `exchange_code` identical modulo the error class (`:54-70` vs `:59-75`); `get_me` shares the parse/raise scaffold including the same inline `import json as _json` quirk (`:81-90` vs `:80-91`); the mock scaffolding (`_MOCK_IDENTITIES` + `MockXClient`) is identical (`:106-127` vs `:105-126`).
- Services: `application/services/twitch_service.py:30-112` vs `application/services/racetime_service.py:27-108` — `_redirect_uri`, `is_configured`, `player_authorize_url`, `_oauth_client`, `exchange_player_code` are line-for-line parallel; `record_player_link`/`unlink_player` differ only in field prefix and audit action, including the same duplicate-account check.
- *Suggested extraction:* `application/utils/oauth_identity_client.py` (base `OAuthIdentityClient`) + a provider-parameterized `IdentityLinkService`; Twitch and racetime become ~10-line configurations.

**[mixed] 2A.2 — Repository CRUD boilerplate is stamped into ~15 repositories.**
The `for key, value in fields.items(): setattr(obj, key, value); await obj.save()` update appears in 19 methods across 15 files (`preset_repository.py:35`, `race_room_profile_repository.py:30`, `speedgaming_episode_repository.py:37`, `webhook_repository.py:30`, `tournament_repository.py:184`, `racetime_bot_repository.py:38`, `volunteer_shift_repository.py:66`, `user_repository.py:171`, `volunteer_position_repository.py:51`, `stream_room_repository.py:84`, `async_qualifier_repository.py:54,85,107,219,260`, `discord_scheduled_event_repository.py:47`, `racetime_room_repository.py:72`, `speedgaming_event_link_repository.py:50`, `tenant_repository.py:63`). The matching `create`/`get_by_id` shapes (`Model.create(tenant_id=current_tenant_id(), **fields)` / `Model.get_or_none(id=..., tenant_id=current_tenant_id())`) recur 82×. `async_qualifier_repository.py` alone re-declares the quartet across 5 sibling classes. `_crew_repository.py` already proves a generic base works here. *Extraction:* `TenantScopedRepository[T]` in `application/repositories/_base.py`. (~10 of the 15 copies are new this week.)

**[new] 2A.3 — Background-worker loop scaffolding is cloned 5×.**
The ~28-line `_loop`/`start`/`stop` + module-global `_task` skeleton is identical (only the log string differs) in `race_room_worker.py:82-106`, `speedgaming_sync_worker.py:61-85`, `discord_event_worker.py:56-80`, `service_health_worker.py:36-60`, and `volunteer_reminder.py:105-129` (whose docstrings literally say "modeled on" the others). The per-item `tenant_scope`/try-except `_tick` iteration is structurally repeated too. *Extraction:* `run_worker_loop(tick, interval, name)` / a `BackgroundLoop` class in `application/utils/`.

**[pre-existing] 2A.4 — `PlayerAvailability*` is a wholesale clone of `VolunteerAvailability*` (~150 lines).**
`player_availability_service.py:18-117` vs `volunteer_availability_service.py:21-124`: `set_windows`, `clear`, `availability_map`, `covers`, `effective_segments` are identical except the model class, audit action, and the volunteer opt-in check — `effective_segments` is byte-identical (`:101-116` vs `:109-124`). The repos are identical except the model name. The pure algorithms (`covers`, `effective_segments`) will drift silently if a precedence bug is fixed in only one. *Extraction:* a shared `availability_windows.py` (pure functions over a `starts_at/ends_at/status` protocol) + a generic `AvailabilityRepository[T]`.

**[pre-existing] 2A.5 — Recipient-collection loops are triplicated in `MatchScheduleService` (~90 lines).**
`notify_match_participants` (`:303-334`), `notify_match_crew` (`:348-382`), and `_collect_notified_discord_ids` (`:541-559`) each build the players/commentators/trackers/watchers set with the same filter+prefetch+opt-in loops; the send loop is verbatim twice (`:326-334` vs `:374-382`). These are also raw ORM reads that belong in a repository. *Extraction:* one `collect_match_recipients(...)` helper + one `_send_dms(...)` loop.

#### Medium

- **[new] 2A.6 — Load-or-`ValueError` helper re-declared per service.** A verbatim-modulo-type `_require` sits in `preset_service.py:171-175`, `race_room_profile_service.py:114-118`, `speedgaming_sync_service.py:147-151`, `racetime_bot_service.py:290-294`, `webhook_service.py:312-316`, and the two async-qualifier services (`async_qualifier_service.py:679-689` vs `async_qualifier_live_race_service.py:289-299`). 40+ more inline `raise ValueError("… not found")` blocks exist (`equipment_service.py:130,162,197,221`; `tournament_service.py:46-48,69-71`; etc.). *Extraction:* `require_found(obj, label)` in a shared module or on the CRUD base.
- **[pre-existing] 2A.7 — `MatchService` repeats "Match … not found" 7×** (`match_service.py:319-321,524-526,561-563,600-602,665-667,698-700,744-746`; the last diverges to "Match not found"). *Extraction:* `_require_match(match_id)`.
- **[new] 2A.8 — Async-qualifier admin gate repeated ~14×** across the two split services (`async_qualifier_service.py:101,119,161,199,210,221,232,241,255,574,652,699,722`; `async_qualifier_live_race_service.py:89,113,306`) — the module split extracted rules/draw but left the gate + `_require_*` helpers behind. *Extraction:* `async_qualifier_access.py`.
- **[new] 2A.9 — `can_manage_sync` gate repeated 12×** (`speedgaming_sync_service.py:33,41,57,93,124,141`; `discord_event_sync_service.py:37,43,59,90`; `race_room_service.py:98-101`; `race_room_profile_service.py:121-125`). *Extraction:* `AuthService.ensure_can_manage_sync(actor)` or a `@gated(...)` decorator.
- **[new] 2A.10 — Super-admin gate: a helper in one service, inlined 6× in another** (`racetime_bot_service.py:296-301` vs `tenant_service.py:143,164,190,209,218,233`). *Extraction:* `AuthService.ensure_super_admin`.
- **[new] 2A.11 — `AuthService` permission ladder written 3×** (`auth_service.py:218-226,229-238,241-257`) — identical `is_system → is_super_admin → is_staff → has_role` cascade. *Extraction:* `_system_admin_staff_or(user, role)`.
- **[new] 2A.12 — Config-blob validator duplicated** (`tournament_config.py:38-56` vs `async_qualifier_config.py:29-41`). *Extraction:* `validate_config_blob(config, model_cls, label)`.
- **[new] 2A.13 — Sorted-JSON→sha256 `_content_hash` duplicated** (`speedgaming_etl_service.py:457-461` vs `discord_event_reconciler_service.py:258-267`); `_opt_str` defined 3× (`racetime_client.py:48`, `twitch_client.py:43`, `speedgaming_etl_service.py:463`). *Extraction:* `stable_content_hash(obj)` in utils.
- **[new] 2A.14 — SG ETL re-implements match-roster sync owned by `MatchParticipants`** (`speedgaming_etl_service.py:326-351`, per-user `is_player_enrolled_by_id`, vs the batch `match_participants.py:53-88`). *Fix:* call `MatchParticipants`.
- **[new] 2A.15 — racetime entrant→User mapping + unmatched-handle capture duplicated** (`race_room_service.py:192-197,213,222` vs `async_qualifier_live_race_service.py:272-278,215-218`). *Extraction:* `map_entrants_to_users(entrants)`.
- **[pre-existing] 2A.16 — `events/dispatch_queue.py:17-56` is a self-declared clone of `services/discord_queue.py:8-48`** (~45 lines; the docstring admits it). Two *instances* is fine; two *copies* is not. *Extraction:* `CoroutineQueue(name)` in a layer-neutral module.
- **[new] 2A.17 — `reports_service` vs `analytics_service` duplicate constants + helpers** — `DEFAULT_MATCH_DURATION_MIN = 90` and `ON_TIME_THRESHOLD_MIN = 5` are defined in both (`reports_service.py:21-22`, `analytics_service.py:25-26`); drift here makes the Reports and Insights "on-time %" silently disagree. `_eastern` and hours-from-window math are also duplicated. *Extraction:* `reporting_shared.py`.
- **[mixed] 2A.18 — `DiscordService` guild-resolution + error-mapping boilerplate** — the `get_guild`→`fetch_guild` fallback appears 6× (`discord_service.py:298-303,336,417,448-453,478-483,511-515`; `_get_guild` was added in the same commit as two call sites that re-inline it), the not-connected preamble 10×, and the `except Forbidden/HTTPException/Exception → (False, msg)` tail is copied into all three scheduled-event wrappers.
- **[new, correctness-adjacent] 2A.19 — `is_mock_speedgaming` re-implemented with divergence** — canonical `speedgaming_client.py:35-43` (`.strip().lower()`, accepts `'on'`, raises in production) vs the inline re-check at `service_health_service.py:235` (no `.strip()`, no `'on'`, silently ignores). `MOCK_SPEEDGAMING=on` mocks everywhere **except** the health board, which reports the live host. See also §3.2. *Fix:* call the canonical helper.

#### Low (abbreviated)

`User.preferred_name` re-implemented (`async_qualifier_rules.py:47`, `discord_event_reconciler_service.py:234`); optimistic-concurrency check ×2 (`user_service.py:254-257,288-291`); M2M grant/revoke quadruplets (`tournament_service.py:255-301`, `async_qualifier_service.py:208-228`); name-uniqueness create/rename pair in 6 services; racetime bot status writers ×3 (`racetime_bot_service.py:211-272`); `_audit_and_emit` exists in exactly one service (`race_room_service.py:283-298`) while siblings hand-roll audit-then-publish — *promote to `AuditService.write_and_publish`*; `EventType.ALL` (`events/event_types.py:90-106`) hand-repeats every member (drift hazard — build it programmatically); `to_utc_aware(dt)` belongs in `utils/timezone.py` (naive-datetime fix-up copied at `service_health_service.py:271,449`, `challonge_service.py:68`, `speedgaming_etl_service.py:453`).

### 2B. API layer

*One clean bill up front:* no router imports `application.repositories` or reaches through `service.repository.*` — the forbidden-import rule holds across the whole `api/` package.

#### High

- **[mostly new] 2B.1 — `_load_*_or_404` helper copy-pasted into 12 routers** (plus 3 verbatim copies of `_load_user_or_404` and ~12 inline equivalents). The identical 4-line `Model.get_or_none(id=..., tenant_id=require_tenant_id())` → `HTTPException(404)` shape recurs in `async_qualifiers.py:44`, `async_qualifier_live_races.py:31`, `race_rooms.py:31`, `race_room_profiles.py:20`, `speedgaming.py:28`, `discord_events.py:27`, `presets.py:25`, `racetime_bots.py:31`, `seeds.py:38`, `match_actions.py:31`, `tournament_actions.py:22`, `stream_room_actions.py:15`. Helper names even drift (`_load_or_404` vs `_load_<entity>_or_404`).
- **[new] 2B.2 — Systemic load-then-discard double fetch.** Nearly every by-id route runs *two* queries for the same row: the router's `_load_*_or_404` result is thrown away, then the service re-fetches by id (e.g. `async_qualifiers.py:72-74` → `async_qualifier_service.py:98-99`). ~30 sites. Root cause: services signal "missing" with `ValueError("… not found")`, which `ServiceErrorRoute` maps to **400**, so routers preload solely to get a **404**. *Fix (highest-leverage in the whole API):* add `NotFoundError(LookupError)` mapped to 404 in `ServiceErrorRoute`, then delete every preload — this also resolves 2B.1 and 2B.6.
- **[new] 2B.3 — `AsyncQualifierRun` serialized two inconsistent ways** — `AsyncQualifierRunResponse` (`schemas/async_qualifiers.py:146-167`, omits `live_race_id`) vs `RunResponse` (`schemas/async_qualifier_live_races.py:28-42`, omits the vod/reattempt/review fields). Same rows, different shapes, no documented reason. *Fix:* one shared schema with `live_race_id: Optional[int]`.
- **[pre-existing] 2B.4 — The volunteer / player-availability twin** — `schemas/volunteers.py:98-117` vs `schemas/player_availability.py:11-31` are field-for-field near-identical (same guarding comment); the same two-line hardening had to be applied twice this week, and the routers repeat the same tuple-repacking adapter (`volunteers.py:223`, `player_availability.py:44`). *Extraction:* shared `AvailabilityWindowInput`/`SetAvailabilityRequest`.

#### Medium

- **[new] 2B.5 — Schemas hand-mirror service `as_dict()` dicts** — `SyncResultResponse`, `ReconcileResultResponse`, `ProbeResultResponse`, `RacetimeBotResponse` each re-declare a field list that already lives in the model and the service serializer, and the routers convert via `.as_dict()` only for FastAPI to re-validate into the mirror (`service_health.py:29,35,41` repeats it 3× in one file). *Fix:* let the `from_attributes` schemas validate the dataclass/model directly.
- **[pre-existing→spreading] 2B.6 — 404 vs 400 for the identical "missing id", sometimes within one router.** In `match_actions.py`, seat/start/finish/confirm preload → 404 but update/delete/etc → 400; in `async_qualifiers.py`, a missing qualifier → 404 but a missing pool/permalink/run → 400. Also `webhooks.py:43-45`, `triforce.py:74-86`, `crew.py` (approval→404 vs acknowledge→400). *Fixed for free by 2B.2.*
- **[mixed] 2B.7 — Response-envelope inconsistency** — one paginated envelope (`AuditLogPage`), one limit-only bare list (`matches.py`), and ~25 unbounded bare lists (every new router chose unbounded). *Fix:* a shared `Page[T]` + `pagination` dependency for the high-cardinality collections.
- **[mixed] 2B.8 — Partial-update semantics: three coexisting conventions** — `model_dump(exclude_unset=True)` (new routers), full explicit `Optional` pass (`stream_room_actions.py`, `webhooks.py`, `users.py`), and `clear_*` boolean flags (`match_actions.py`, and new `QualifierUpdateRequest.clear_window`, `PoolUpdateRequest.clear_preset` — which combine `exclude_unset` *and* `clear_*` in one model).
- **[mixed] 2B.9 — Auth-dependency placement drift + a real double-authentication.** Router-level vs per-endpoint `require_api_actor` is inconsistent; and because `_resolve_token` is a plain helper rather than a cached `Depends`, every write endpoint in `volunteers.py` authenticates the bearer token **twice** per request (router-level `:34` + `require_write_actor` per endpoint) — two `ApiTokenService().authenticate` DB round-trips, and the tenant lookup added this week runs twice too. *Fix:* make token resolution a cached dependency.
- **[new] 2B.10 — Read-only-token rejection block tripled** in `api/dependencies.py` (`:92-102`, `:122-137`, `:154-167`).
- **[new] 2B.11 — Router-side tenant filtering of an unscoped service read** — `race_rooms.py:43-45` fetches *all* tenants' open rooms via `RacetimeRoomService().list_open_rooms()` then filters in the presentation layer; any future caller inside a tenant request leaks cross-tenant rows by default. *Fix:* add a scoped `list_open_rooms_for_current_tenant()` and keep the documented unscoped one for the bot loop only.

#### Low (abbreviated)

Inline self-or-staff logic duplicated (`users.py:77-78,149-150`, `triforce.py:45-52`); router-side response assembly mutating ORM state (`volunteers.py:158`); `volunteers.create_shift` re-finds the created row heuristically with a wrong-row fallback (`volunteers.py:126-134`); hand-built response dicts re-declaring schema fields where `from_attributes` would do (`volunteers.py:40-69`, `users.py:36-49`, `tokens.py:50-59`, `audit.py:49-58`); tag/prefix/`body`-vs-`payload` naming drift; `PUT /webhooks/{id}` that is semantically a PATCH; stale `RoleRequest.role` description listing 3 of 11 roles (`schemas/user_actions.py:34`).

### 2C. Presentation layer (`pages/`, `theme/`, `discordbot/`)

*Clean bill on the hard NiceGUI failures:* no `asyncio.create_task`/`ensure_future`, no `Client.current`, no `async with client`, no `time.sleep`, no `requests`, and no per-user module-level state anywhere in the layer. No ORM *writes* either — every mutation goes through a service.

#### High

- **[new] 2C.1 — Admin CRUD-tab scaffolding cloned into 4 new tabs.** `admin_presets.py`, `admin_racetime.py`, `admin_speedgaming.py`, and `admin_discord_events.py` are structural clones of `admin_webhooks.py`/`admin_discord_roles.py`, repeating eight blocks that should be shared components — the codebase already proves the pattern with `TournamentTableView`/`UserTableView`/`build_refreshable_board`:
  1. **Page-header scaffold** (column + header-row + title + separator) — ~22 sites.
  2. **`_current()` actor helper** — 7 copies + 73 raw call sites of the same one-liner across 42 files. *Extract `current_actor()`.*
  3. **`refresh_table()`** (fetch → `table.rows = [...]` → `table.update()`) — 11 sites. *Extract a generic `ServiceTableView`.*
  4. **Toolbar refresh icon-button** — 11 sites.
  5. **`selected_tab` refresh wiring** — 10 sites, each depending on a tab-name string that must match the label in `pages/admin.py` (a rename silently kills refresh).
  6. **`body-cell-actions` slot template** — 12 sites. *Extract an `actions_slot([...])` builder.*
  7. **Delete-row handler** — 5 sites.
  8. **Add/Edit dialog scaffold** — 7+ sites, **none of which use the existing `theme/dialog/_helpers.py`** (`dialog_header`, `dialog_actions`, `mobile_sheet`, `submit_on_enter`); the new inline dialogs therefore lack mobile-sheet mode, the standard header, and Enter-to-submit. This is the sharpest drift: a helper module exists and the new code ignored it.
- **[new] 2C.2 — `reports/telemetry.py` is a structural clone of `reports/audit.py`.** `_parse_details` is verbatim (`telemetry.py:39-50` vs `audit.py:27-43`); `PAGE_SIZE`, the filter strip, the expandable-details `body` slot (`:221-240` vs `:153-174`), and the pager (`:246-256` vs `:182-204`) are near-verbatim. *Extraction:* `paginated_event_log(...)` + `parse_details` into `reports/shared.py`.

#### Medium

- **[pre-existing] 2C.3 — Challonge Disconnect handler misses `PermissionError`** — `admin_challonge.py:64-70` catches only `ValueError`, but `ChallongeService.disconnect` raises `PermissionError`; a stale non-staff session gets an unhandled exception instead of a toast.
- **[pre-existing] 2C.4 — Deactivated accounts bypass `is_active` on four pages** — `pages/volunteer.py:21`, `home_tabs/player_edit_info.py:77`, `home_tabs/player.py:39`, `home_tabs/stage_timeline.py:19` resolve the user with raw `User.get_or_none(...)` instead of `get_user_from_discord_id(...)` (which enforces `is_active`). A deactivated-but-session-holding account still gets a working page.
- **[new] 2C.5 — OAuth link pages ×3** — `racetime_oauth.py` and `twitch_oauth.py` are line-for-line identical except the service class and strings; `_read_callback_code` is copy-pasted 3× (`racetime_oauth.py:82`, `twitch_oauth.py:82`, `challonge_oauth.py:137`). Drift already exists: `challonge_oauth.py`'s finish handler lacks the `except ValueError → warning` branch the other two have. *Extraction:* `pages/_oauth_link.py`.
- **[new] 2C.6 — Profile "link account" sections ×3** — `challonge_link_section.py`, `twitch_link_section.py:13-47`, `racetime_link_section.py:13-47` are 48-line files identical except service/attrs/copy. *Extraction:* `render_link_section(...)`.
- **[pre-existing] 2C.7 — Equipment table duplicated across admin and home** — status-badge slot, mobile grid card, checkout/checkin handlers, and `_STATUS_LABELS` (defined 3×) are duplicated between `admin_equipment.py` and `home_tabs/equipment.py`. *Extraction:* `theme/tables/equipment.py`.
- **[pre-existing] 2C.8 — Match state/seed cell templates duplicated in page-side `extra_slots`** — `home_tabs/schedule.py:41-92` and `home_tabs/player.py:93-138` each embed a ~50-line Vue template, already diverged (player drops the icon/timestamp). `theme/tables/match_slots.py` exists to centralize exactly these.
- **[mixed] 2C.9 — Three coexisting error-toast conventions** (see §3.1).
- **[mixed] 2C.10 — KPI card helper triplicated** (`dashboard.py:155-159`, `insights.py:144-148`, `telemetry.py:264-268`); row-click filter handler ×4 (`audit.py`, `crew.py`, `stream_rooms.py`, `telemetry.py`).

#### Low (abbreviated)

Leaderboard table + `_fmt` duplicated (`admin_qualifiers.py:459-475` vs `qualifiers.py:228-248`); one-time-secret reveal dialog ×2; dead duplicate table slots (`admin_settings.py:129-169`, 15 dead lines); `TournamentTableView`/`UserTableView` share an unextracted `BaseTableView` shape; a racy sync `@ui.refreshable` that kicks a background render (`triforce_texts.py:75-129`); a dead `schedule()` helper (`reports/shared.py:220-222`); module-level service singletons (`platform.py:23`, `qualifiers.py:55` — verified stateless, so drift-not-bug); a captured-but-unused `client` param (`admin_discord_events.py:124`) and a background dialog with no client capture (`admin_speedgaming.py:183,209`).

#### `discordbot/` — Low, pre-existing

The crew/match/volunteer acknowledgment handlers share a sound `_ack_common.py` core but still duplicate the defer/parse/resolve-tenant/lookup ladder (~55 lines × 3). More notably, `crew_signup.py:29-93` and `watch_buttons.py:27-77` **drift from that pattern**: no `interaction.response.defer()` (the 3-second Discord-deadline risk the ack handlers explicitly guard against), no outer `except Exception`, and an inlined "no account" message instead of the shared `MSG_NO_ACCOUNT`. *Extraction:* a `run_dm_interaction(...)` wrapper.

### 2D. Tests

*Verdict up front:* the suite is stronger than a glance suggests — the `*_coverage.py` modules are real behavior tests (ordering, upsert transitions, concurrency via `Event`/`Queue.join` rather than sleeps), the new API modules uniformly cover the 401 / 403-role / 403-read-only / 404 matrix plus tenant isolation, and `api_helpers.py` is genuinely reused across 22 files. The problems are fixture duplication and a handful of specific hazards.

#### High

- **[new] 2D.1 — Real outbound HTTPS calls in a CI test.** `tests/test_api_service_health.py:76-84` POSTs `/service-health/refresh`, which runs all 12 probes; CI sets no `MOCK_*` env vars (`.github/workflows/test.yml:60`), so five probes make real network calls to speedgaming.org, api.challonge.com, alttpr.com, ootrandomizer.com, and maprando.com (5s timeout each). The assertions don't fail on a DOWN probe, so it won't go red on an outage — it just hits third-party production hosts on every CI run and behaves differently online vs offline. The service-level test (`tests/services/test_service_health.py`) shows the right pattern ("no probe touches the network"). *Fix:* mock `_PROBES` or set the `MOCK_*` flags.
- **[mixed] 2D.2 — `stub_discord_queue` copy-pasted 11×.** An identical autouse fixture already lives in `tests/services/conftest.py:4-19` but only applies there; 11 `test_api_*.py` modules re-paste it (two even carry the comment "mirrors services conftest"). *Fix:* hoist one copy to `tests/conftest.py`.
- **[new] 2D.3 — Two-tenant setup duplicated across 26 sites in 20+ files, with four drifting slug conventions** (`tenant-b` ×7, `beta` ×11, `b` ×4, `community` ×2) plus a private `_tenants` helper re-defined in 4 modules and scattered `two_tenants`/`two_tenant_api`/`tenants_with_staff` fixtures. *Fix:* one parametrizable `two_tenants` fixture in `conftest.py`.

#### Medium

- **[pre-existing] 2D.4 — `app` fixture re-pasted 21×** wrapping `api_helpers.build_api_app()`.
- **[pre-existing] 2D.5 — `bypass_auth` fixture in 13 near-identical copies** across `tests/services/`.
- **[new] 2D.6 — `def utc(...)` re-defined in 10 modules — one with an incompatible signature** (`test_volunteer_services_coverage.py:37` is `utc(hour, minute=0, day=4)`; every other copy is `utc(hour, minute=0)`, so a copy-paste between them silently produces wrong dates). `make_user`/`_user` is re-defined in 21 modules with drifting signatures. *Fix:* `tests/factories.py`.
- **[new] 2D.7 — Duplicate coverage across old/new modules** — `TestPlayersLabel` and the `*_dm` builders are asserted in both `test_match_schedule_service.py` and `test_utils_coverage.py`; `test_infra_coverage.py:401-408` duplicates `test_error_handlers.py:54-60`.
- **[mixed] 2D.8 — Old tests ignore the shared helpers** — `test_api_tokens.py:29-31` and `test_api_matches.py:29-50` hand-build the app and re-implement `client_for`/`create_user_token` inline, giving the tree two ways to fake API auth.
- **[new] 2D.9 — Untested background workers** — `discord_event_worker.py`, `speedgaming_sync_worker.py`, and `service_health_worker.py` have zero test references, while their sibling `race_room_worker.py` shows the achievable bar (`_tick` eligibility tests). Given the rule that worker `_tick` bodies must wrap scoped data in `tenant_scope(...)`, these are exactly where a `require_tenant_id()` crash would ship. Also: `validate_async_qualifier_config` is never driven by any test.

#### Low (abbreviated)

Status-only mutation assertions without persistence checks (`test_api_router_gaps.py:383-402,176-182`); magic `tenant_id=1` at 11 sites despite `DEFAULT_TEST_TENANT_ID` in conftest; `random.seed(1234)` left unrestored (`test_utils_coverage.py:359-365`); naive `datetime.now()` in older service tests vs aware elsewhere; implementation-detail coupling in the coverage modules (poking `_queue`, `_worker_task`, `_subscribers`; section headers named after source line numbers).

---

## 3. Other engineering-practice findings

### 3.1 Error-handling convention drift [medium, mixed]
Three conventions coexist for the same failure classes:
- **New admin tabs:** `except (ValueError, PermissionError) → ui.notify(..., 'warning')`.
- **`admin_schedule.py`:** `PermissionError → negative`, `ValueError → warning` (the 6-line ladder pasted 4×).
- **Class dialogs** (`tournament_edit_dialog.py:266-271`, `user_edit_dialog.py:110-115,319-324`, `match_dialog.py:261-266,275-280`, and 5 more): `PermissionError → negative`, **`ValueError → negative` with an `Error:` prefix — which contradicts the documented convention** ("catch in UI and show `ui.notify(str(e), color='warning')`", per CLAUDE.md).

Broad `except Exception` in UI handlers that swallow programming errors as toasts: `admin_challonge.py:111-112`, `tournament_edit_dialog.py:155-157`, `match_result_dialog.py:112-114`, `station_assignment_dialog.py:127-128`. *Fix:* one `notify_error(e)` mapper used everywhere; ban bare `except Exception` in handlers outside documented fire-and-forget boundaries.

### 3.2 Naming / consistency drift [medium/low, new]
- **`race_room` vs `racetime_room`** for one domain: `RaceRoomService` (lifecycle) vs `RacetimeRoomService` (slug lookup); the model is `RacetimeRoom` but its enum is `RaceRoomStatus`, its settings `RaceRoomProfile`, its worker `race_room_worker`, its audit namespace `race_room.*`. Arbitrary and grep-hostile.
- **`sg_` vs `speedgaming`** mixed on one model (`related_name='sg_episodes'`, field `sg_episode_id` in `models/speedgaming.py:54,58` vs `speedgaming_episode` in `models/match.py:31`); audit namespace `sg_sync.*` vs service `SpeedGamingETLService`.
- **Two truthy-env grammars** — mock modules accept `('1','true','yes')` while worker switches accept `('1','true','yes','on')`, across 13 duplicated literal sites, no shared helper despite `environment.py:56` already having the logic. The `MOCK_SPEEDGAMING=on` split-brain (§2A.19) is the concrete consequence. *Fix:* an `env_flag(name)` helper.

### 3.3 Dead code & export hygiene [medium, mixed]
- **`get_platform_host()` is dead** (`application/utils/environment.py:29`, zero callers) — which makes the documented `PLATFORM_HOST` env var (`docs/deployment.md:101`, `docs/features/multitenancy.md`) inert. New this week. *Fix:* wire it up or delete it (and the doc rows).
- **Three split helper modules are not re-exported** from `application/services/__init__.py` — `match_participants` (`MatchParticipants`), `async_qualifier_draw` (`AsyncQualifierDraw`), `async_qualifier_rules` (`validate_counts`/`validate_window`) — while every comparable sibling is. Consumers import the submodule paths directly, bypassing the package interface. Low urgency (intra-package only), but the export hook can't see it because it only inspects `*_service.py`/`*Service`-named symbols.
- **Six unreferenced new methods:** `TenantService.add_member`/`list_members`/`list_memberships_for_user` (`tenant_service.py:189-202` — which also strands the `tenant.member_added/removed` audit path), `AsyncQualifierRepository.get_with_relations`, `MatchRepository.list_sourced_for_link`, `TenantMembershipRepository.tenant_ids_for_user`. Plus the pre-existing dead `Match.is_confirmed` property.
- `ruff --select F401,F811,F841` is clean repo-wide; `models/`, `repositories/`, and `api/` package exports all resolve with no stale names.

### 3.4 Feature-flag correctness gaps [medium, new]
- **The single default feature group can be deleted or un-defaulted with no guard** (`feature_flag_service.py:276-325`). Once there are zero defaults, `_group_flag_keys` returns `set()` for every ungrouped tenant, silently turning off all group-derived features platform-wide — and the UI notify asserts the opposite ("its tenants fell back to the default", `platform.py:431`). No test covers it. *Fix:* raise `ValueError` on deleting/unsetting the last default.
- **The volunteer-reminder worker ignores `FeatureFlag.VOLUNTEERS`** (`volunteer_reminder.py:40-70`) even though the two sibling workers (`race_room_worker.py:60`, `speedgaming_sync_worker.py:54`) gained exactly this per-tenant flag check this week — so a community that switched Volunteers off still gets reminder DMs. *Fix:* skip inside the existing `tenant_scope` when the flag is disabled.
- **`FEATURE_GROUP_UPDATED` audit payload records only `changed_fields`, not values** (`feature_flag_service.py:306-309`) — a group edit changes availability live for every assigned tenant, but the audit row can't answer "which flags changed" (the CREATE sibling logs the full flag list).

### 3.5 Config / magic values [low, new]
`RACETIME_BASE = 'https://racetime.gg'` (`racetime_client.py:22`) and `SPEEDGAMING_BASE = 'https://speedgaming.org'` (`speedgaming_client.py:24`) are not env-overridable, unlike the Challonge/Twitch/Discord endpoints — only relevant for staging-against-staging. Worker cadences and timeouts are named module constants (acceptable). `seedgen_service.py:152,168` embeds full randomizer-flag URLs/strings as inline literals (preset-shaped data in code).

### 3.6 Documentation drift
- **[high, new] `CLAUDE.md:125` says the `Role` enum "has seven members"; it now has eleven** (`models/enums.py:4-20` — `PRESET_MANAGER`, `SYNC_ADMIN`, `QUALIFIER_ADMIN`, `SUPER_ADMIN` added). Because `CLAUDE.md` is always loaded, this misleads every session about the authorization surface — notably omitting the one global role. `docs/features/role-based-auth.md` (the "canonical" list) is likewise four roles behind and omits the new `AuthService.can_manage_presets/can_manage_sync/can_admin_qualifier` gates.
- **[low] `docs/current-state.md`** still labels PRs 2–10 and the REST expansion "In progress | this PR" though all are merged.
- Otherwise current: `docs/reference/data-model.md` (exact model/enum counts), `services.md`, and `rest-api.md` all cover the new work.

### 3.7 Module-size watch [low, trend]
No module exceeds the 800-line guideline (largest is 789). But four of the five 700+ modules grew this week and bear watching: `match_service.py` (789 — 11 lines of headroom), `async_qualifier_service.py` (749, already post-split), `theme/dialog/match_dialog.py` (739), `scripts/seed_dev.py` (737), `discord_service.py` (721).

---

## 4. Cross-cutting themes & recommended remediation order

Ordered by leverage (debt removed per unit of effort), safest first:

1. **`NotFoundError → 404` in `ServiceErrorRoute`.** One change resolves three findings: the 12-way `_load_*_or_404` copy-paste (2B.1), the ~30-site double-fetch (2B.2), and the 404/400 inconsistency (2B.6). Add the exception, map it, delete the preloads.
2. **`TenantScopedRepository[T]` base + `require_found(obj, label)` helper** (2A.2, 2A.6, 2A.7). Highest file-count reach; `_crew_repository.py` already proves the base pattern.
3. **Shared OAuth-identity client + `IdentityLinkService`** (2A.1) and the parallel UI extractions — `pages/_oauth_link.py` (2C.5) and `render_link_section` (2C.6). Largest single copy-paste in the codebase.
4. **Shared admin-CRUD-tab component in `theme/`** (2C.1): page shell, `current_actor()`, `ServiceTableView`, actions-slot builder — and route the new inline dialogs through the existing `theme/dialog/_helpers.py`.
5. **`BackgroundLoop` + `CoroutineQueue`** (2A.3, 2A.16), and give the three untested workers `_tick` tests (2D.9) while you're in there.
6. **`env_flag()` helper** (3.2) — this also closes the `MOCK_SPEEDGAMING=on` split-brain (2A.19), a real behavior bug.
7. **Test-fixture consolidation** — hoist `stub_discord_queue`, `app`, and `two_tenants` to `conftest.py`; add `tests/factories.py` (2D.2–2D.6).

The three correctness bugs (§1) and the feature-flag gaps (§3.4) are independent of the above and should be fixed on their own regardless of the DRY work. The stub-randomizer contract break (§1.3) and the CI network calls (§2D.1) are the two most likely to bite in production/CI soon.

---

## 5. Positives worth preserving

So remediation doesn't refactor away the good patterns:

- **Genuinely shared, correctly-placed helpers:** `application/utils/ssrf.py` (webhook + web-push both delegate), `application/repositories/_crew_repository.py` (generic base over Commentator/Tracker), `api/_match_view.py` (`serialize_match` shared by two routers), `theme/dialog/_helpers.py`, `theme/availability_editor.py`, `pages/service_health_view.py` (reused by `/platform` and the admin tab), `MatchScheduleService._transition`.
- **Drift guards already in place:** `tests/services/test_event_audit_parity.py` turns a missing `EventType`-for-`AuditAction` into a red test; the strict-`xfail` convention; the conftest `db` fixture's tenant auto-stamp shim.
- **Verified clean in the recent delta:** the feature-flag layer is correct (repositories landed, the 366-line service does no direct ORM I/O, reads pass explicit `tenant_id`, writes stamp it, `require_tenant_id()` fails loud); `TenantFeatureFlag` has the tenant FK + composite unique + a cross-tenant leak test; the new audit actions are all `AuditActions` constants and the deliberate absence of events is documented; the URL refactor left no dead `?tab=` handling and no gated-tab leak; the four seed-generator stubs are trivially parallel (not worth abstracting); `PR #96` removed the strict `xfail` in `test_repositories_coverage.py` by actually fixing the underlying `search_by_name` bug.
