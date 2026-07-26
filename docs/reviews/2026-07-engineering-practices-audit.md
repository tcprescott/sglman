# Engineering-Practices Audit — Extraction Adoption & Convention Drift

**Date:** 2026-07-26
**Commit audited:** `ec743eb` (origin/main)
**Delta window:** `a402d19..ec743eb` — 154 commits, 565 files, +37,642 / −6,782 lines. Dominated by the **native brackets subsystem** (~4,550 lines of service/repo code plus UI, API, CSS and ~5,500 lines of tests), the bracket ↔ scheduled-match integration, the `_oauth_link` refactor, and the single-worker capacity work.
**Scope:** whole codebase. Findings are labelled **[new]** (introduced inside the window) or **[pre-existing]**.
**Status:** report written first, then **remediated in the same branch** — see [§8 Remediation status](#8-remediation-status) for what shipped, what was deliberately deferred, and the one finding the fix attempt disproved (B4).
**Predecessor:** [2026-07-code-quality-audit.md](2026-07-code-quality-audit.md) (commit `a402d19`). §6 records which of its findings verifiably landed.

## Method, and what it means for these numbers

This pass was run **inline rather than as a subagent fan-out**, so every citation below was opened and re-read by the same reviewer that wrote it. In place of an adversarial re-checker, the discipline was **self-refutation before reporting**: every candidate finding was first produced by a cheap heuristic (grep/AST sweep), then the heuristic was assumed wrong and checked against the code. That caught six would-be false positives, which are recorded here rather than quietly dropped — they are the honest measure of how much the raw sweeps overstate:

| Draft finding | Why it was dropped |
|---|---|
| "13 `ui.table()` calls violate the mobile-grid rule" | **All 13 compliant.** My grep only knew the `enable_mobile_grid` route; the tables use the sanctioned inline `Quasar.Screen.lt.md` prop. Running the repo's own `check_table_grid.py` over each file returned exit 0 for every one. |
| "55 `EventType` members are missing from `EventType.ALL`" | **`ALL` is complete.** My regex expected a tuple; `ALL` is a `frozenset` (`event_types.py:110-131`) and contains all 54 registered names. |
| "22 service methods write without auditing" | **Cut to 3.** The sweep didn't know about `write_and_publish` or private wrappers like `race_room_service._audit_and_emit`; 19 of the 22 audit correctly through one of those. |
| "34 hand-rolled audit+publish pairs are drop-in replacements" | **13, not 34.** AST comparison of the actual argument expressions shows 24 of them intentionally pass a *different* event dict (see A1 — that difference is itself the finding). |
| "No REST router calls `require_feature`" | **Correctly gated.** It is applied once per mount in `api/__init__.py:59-107` (9 mounts), not inside routers. |
| "`TenantScopedRepository` adoption stalled at 17/42 repositories" | **Adoption is effectively complete.** The boilerplate it replaced — the `setattr` update loop — now exists at exactly one site tree-wide (`_base.py:46`). Inheritance count is the wrong metric. |
| "98 `except` handlers swallow errors silently" | **Too noisy to report.** Most return a user-facing `(False, message)` tuple — a deliberate Result-style contract. The genuinely silent handlers (`except pass`) were each read and are all justified (`CancelledError` on cancel, `idna` fallback, best-effort storage writes). Only the `print()` cases (F1/F2) survived. |
| "The Swiss cross-validation silently never runs" | **It runs in CI.** The `skipif` at `test_bracket_swiss_crossvalidation.py:149` gates on `BBPPAIRINGS_BIN`, and `.github/workflows/test.yml:78-88` clones and builds bbpPairings and sets that variable. It skips locally, by design. |

Numbers stated below are the post-refutation ones.

**Tree state at audit time:** the full suite is green — `3161 passed, 10 skipped, 81 warnings in 218s`. All 10 skips are accounted for: 6 from the one `skipif` above (parametrized ×6, satisfied in CI) and 4 from in-test parameter-space guards in `test_bracket_engine_round_robin.py:52,126`. Nothing in this report is a test failure.

---

## Executive summary

| # | Theme | Severity | Age | Where |
|---|---|---|---|---|
| A1 | `write_and_publish` extracted but adopted at 7 of ~20 eligible sites; a local reimplementation exists | **Medium (DRY)** | new | `application/services/_bracket/`, `race_room_service.py:346` |
| A2 | `ServiceTableView` adopted by 8 admin tabs; 12 still hand-roll the scaffolding | Medium (DRY) | mixed | `pages/admin_tabs/` |
| A3 | `_load_user_or_404` byte-identical in 3 routers | Low (DRY) | mixed | `api/routers/` |
| B1 | `BracketService.enroll` writes with no audit and no event, unlike its two siblings | **Medium** | new | `bracket_service.py:328` |
| B2 | `set_best_of` mutates a matchup with no audit, via a direct ORM write | **Medium** | new | `_bracket/series.py:63` |
| B3 | `update_note` writes with no audit; `opt_in`/`opt_out` beside it both audit | Low | pre-existing | `volunteer_profile_service.py:54` |
| B4 | ~~`bracket.updated` / `bracket.deleted` have no `EventType`~~ — **retracted, false positive** | — | — | see §2 B4 |
| C1 | `set_seeds` issues one UPDATE per entry (64 queries for a 64-entrant reseed) | Medium (perf) | new | `bracket_service.py:405-408` |
| C2 | Service-layer direct ORM writes where a repository method exists | Low | new | `bracket_service.py:320`, `:136`, `series.py:91` |
| D1 | `check_layer_exports.py` false-positives on the private `_crew_repository.py` | **Medium (guardrail)** | pre-existing | `.claude/scripts/check_layer_exports.py:33` |
| D2 | `check_secret_leak.py` false-positives on a token *prefix* and a public OAuth URL | Medium (guardrail) | pre-existing | `.claude/scripts/check_secret_leak.py` |
| E1 | Two live violations of the 800-line budget, both crossed inside the window | Medium | new | `match_schedule_service.py` (815), `scripts/seed_dev.py` (801) |
| F1 | A swallowed Challonge failure is reported by `print()`; the module has no logger | **Medium** | pre-existing | `challonge_service.py:592` |
| F2 | `print()` on the real Discord bot-ready path in a module that has a logger | Low | pre-existing | `discord_service.py:133` |

### The dominant theme: extractions land, adoption stalls

The previous audit's headline recommendation was five extractions. **All five shipped.** But three of them stopped short of full adoption, and the new brackets subsystem — written after they existed — largely did not pick them up:

- `AuditService.write_and_publish` exists; the 10 bracket lifecycle sites hand-roll the pair anyway.
- `theme/tables/admin_crud.ServiceTableView` exists; 12 admin tabs still hand-roll.
- `NotFoundError → 404` + `require_found` exist and did their job — yet 10 `_load_*_or_404` shims remain, 3 of them byte-identical.

Only `TenantScopedRepository` reached full adoption, and it is the one whose target boilerplate is now provably gone (one site tree-wide). The pattern is clear: **an extraction without a guardrail decays into an optional style choice.** `check_dry_regressions.py` is exactly the right instrument and today knows nothing about any of these three primitives.

### The four highest-leverage fixes

1. **Widen `write_and_publish` so the 24 non-adopters *can* adopt**, then convert the 13 drop-ins and delete `_audit_and_emit`. The reason adoption stalled is diagnosable (A1): the event dict is systematically the audit dict *plus* routing keys, and the helper has no way to say that. _[Done for the signature + 15 sites; the rest deferred on test-stub coupling — §8.]_
2. **Fix D1 and D2** — a two-line diff each. Three of fourteen `check_*` hooks currently cry wolf on untouched `main`; that is what teaches contributors to skim past the other eleven. _[Done — 24/24 hooks now clean tree-wide.]_
3. **Close B1–B3.** Three real audit gaps, each sitting directly beside a correctly-audited sibling. _[Done.]_
4. **Teach `check_dry_regressions.py` the three stalled primitives**, so A1–A3 cannot re-accumulate. _[Done for the audit+publish pair and the local wrapper; `ServiceTableView` adoption (A2) is still unguarded.]_

---

## 1. Theme A — extractions whose adoption stalled

### A1 [Medium, new] `write_and_publish` is bypassed by the subsystem written after it

`AuditService.write_and_publish` (`application/services/audit_service.py:391-407`) exists precisely to collapse the audit-then-publish pairing, and its docstring says so: *"Promotes the audit-then-publish pairing that services previously hand-rolled into one call."* It has **7 call sites**.

An AST sweep comparing the *actual argument expressions* of `write_log(actor, action, details)` against `event_bus.publish(Event.create(type, details, actor))` finds **13 methods where both the actor and the details expression are identical** — mechanical drop-ins:

| Site | Method |
|---|---|
| `_bracket/advancement.py:95` | `_record_result` |
| `_bracket/advancement.py:370` | `override_result` |
| `_bracket/completion.py:99` | `_advance_swiss` |
| `_bracket/completion.py:240` | `_finalize_stage` |
| `_bracket/generation.py:29` | `start_bracket` |
| `_bracket/multistage.py:32` | `advance_stage` |
| `bracket_service.py:98` | `create_bracket` |
| `bracket_service.py:278` | `add_entrant` |
| `bracket_service.py:314` | `drop_entrant` |
| `async_qualifier/async_qualifier_live_race_service.py:186` | `record_finish` |
| `match/match_request.py:20` | `submit_match_request` |
| `volunteer/volunteer_schedule_service.py:270` | `unassign` |
| `race_room_service.py:346` | `_audit_and_emit` — **a private reimplementation of the shared helper** |

Ten of the twelve ordinary sites are in the brackets subsystem, written *after* the helper existed. Worse, the same package is internally inconsistent: `_bracket/scheduling.py:185` and `:286` and `_bracket/series.py` **do** use `write_and_publish`, while its six sibling mixins hand-roll it.

**Why adoption stalled — the diagnosis that makes this fixable.** A further **24 methods** have the pair but pass a *different* dict to each call, so they cannot adopt the helper as written. The difference is not arbitrary; it is almost always the audit dict **plus routing keys** the event needs:

- `crew_service.py:40,98,158,223` — event adds `user_id`
- `match/match_service.py:303,484,519,551,631,690` — event adds `tournament_id`
- `match/match_schedule_service.py:223,360`, `match/match_cancellation.py:40` — event adds `tournament_id`
- `speedgaming_etl_service.py:162,364,394`, `volunteer/volunteer_schedule_service.py:208,284`, `async_qualifier_service.py:487,583`, `discord/discord_event_reconciler_service.py:136,182,209` — same shape

So the helper was extracted for the minority case. **Suggested fix:** give it an optional `event_details` (or `event_extra`) parameter defaulting to the audit dict, adopt at all 13 drop-in sites, delete `race_room_service._audit_and_emit`, and migrate the 24 — then add the hand-rolled pair to `check_dry_regressions.py`, which today contains no reference to `write_log` or `write_and_publish` at all.

### A2 [Medium, mixed] `ServiceTableView` adopted by 8 admin tabs, hand-rolled in 12

`theme/tables/admin_crud.py` provides `admin_page_container` (:43), `refresh_icon_button` (:58), `wire_tab_refresh` (:66), `action_button` (:88), `actions_slot` (:100) and `ServiceTableView` (:105) — the shared component the previous audit asked for. Eight tabs use it (`admin_brackets`, `admin_discord_events`, `admin_discord_roles`, `admin_presets`, `admin_qualifiers`, `admin_racetime`, `admin_speedgaming`, `admin_webhooks`).

Twelve substantive tabs still do not, the largest being `admin_volunteers.py` (405 lines), `admin_schedule.py` (223), `admin_settings.py` (222), `admin_volunteer_roster.py` (211), `admin_equipment.py` (182), `triforce_texts.py` (173), `admin_system_config.py` (156), `admin_theme.py` (126), `admin_challonge.py` (118), `admin_feedback.py` (94), `admin_users.py` (88), `admin_features.py` (73).

Credit where due: the newest tab (`admin_brackets.py`) **did** adopt it. **Suggested fix:** migrate opportunistically, largest first, rather than as a big-bang refactor.

### A3 [Low, mixed] `_load_user_or_404` is byte-identical in three routers

The previous audit's `_load_*_or_404` finding is substantially remediated — `NotFoundError → 404` is now centralized in `ServiceErrorRoute` (`api/dependencies.py:197-225`) and the helpers are thin `require_found` one-liners rather than hand-rolled `HTTPException` raises. Ten remain across nine routers, and three are **literally identical** (md5 `3c545c33…` on all three):

```python
async def _load_user_or_404(user_id: int) -> User:
    return require_found(await UserService().get_user_by_id(user_id), "User")
```

`api/routers/users.py:30`, `api/routers/async_qualifiers.py:52`, `api/routers/tournament_actions.py:30`. **Suggested fix:** hoist this one into a shared `api/_helpers.py`; leave the seven genuinely distinct ones alone.

---

## 2. Theme B — audit & event convention gaps

Each of these was verified by reading the method, not by sweep — and each sits beside a correctly-audited sibling, which is what makes them drift rather than policy.

### B1 [Medium, new] `BracketService.enroll` audits nothing

`application/services/bracket_service.py:328-357`. Staff-gated (`:336`), validates state and cross-tournament identity, then `create_entry` at `:351` — and returns. No `write_log`, no event. Its two siblings in the same class both do: `add_entrant` (`:310-311`) and `drop_entrant` (`:323-324`). Enrolling an entrant into a stage determines who appears in the generated graph, so it is exactly the kind of create CLAUDE.md's *"Audit important actions (create/update/delete)"* rule targets. There is also no `unenroll` counterpart. **Suggested fix:** add `BRACKET_ENTRY_ADDED` to `AuditActions` and audit it.

### B2 [Medium, new] `set_best_of` mutates a matchup with no audit, via a direct save

`application/services/_bracket/series.py:63-92`. Staff-gated, validated, rejects the change once games exist — then `bracket_match.best_of = best_of; await bracket_match.save()` at `:90-91`. Two problems in one method: no audit row for a staff mutation that changes how many games a series needs to clinch, and a direct ORM write where `self.repository.update(...)` exists. **Suggested fix:** route through the repository and audit as `BRACKET_UPDATED`.

### B3 [Low, pre-existing] `update_note` audits nothing, unlike its neighbours

`application/services/volunteer/volunteer_profile_service.py:54-58` writes `profile.note` and returns. The two methods immediately above it — `opt_in` (`:40-44`) and `opt_out` (`:46-52`) — both write an audit row. A staff-visible note on a volunteer's profile is a tracked change everywhere else in the codebase.

### B4 ~~[Low, new] Bracket authoring is half-published~~ — **RETRACTED (false positive)**

The original finding read: *`event_types.py` registers 14 `BRACKET_*` events while `AuditActions` has 16; `BRACKET_UPDATED` and `BRACKET_DELETED` have no `EventType`, so a subscriber never learns a stage was renamed, reseeded, restaged, or deleted — and since `BRACKET_CREATED` **is** published, the subsystem is internally inconsistent.*

**This was wrong, and the codebase already had the answer.** `tests/services/test_event_audit_parity.py` is a ratchet test asserting every `AuditAction` is either emitted as an event or listed in an explicit eventless ledger with a rationale. Both actions are in that ledger, under `_EVENT_CANDIDATES`, with this reasoning recorded at `:35-40`:

> Bracket *definition* authoring, the peer of the tournament CRUD above: both are DRAFT-only (name/stage/config, round chrome, reseeding, delete), so nothing competitive has happened yet for a subscriber to react to. The lifecycle events a bracket does emit start at `BRACKET_STARTED`.

That is a deliberate, documented, test-enforced decision — not drift. The "inconsistency" with `BRACKET_CREATED` is also thinner than claimed: announcing that a stage now exists is useful, while its subsequent draft-edits are noise on a stage nobody is playing yet.

**How it was caught:** the remediation added the two `EventType` members, and the parity ratchet failed with *"Ledger entries that are now emitted events: ['bracket.deleted', 'bracket.updated']"*. The change was reverted. This is the ratchet doing precisely its job — and a reminder that this report's §6 praise for `_no_external_network` ("made mechanically unrepeatable") applies here too: **the audit should have consulted the eventless ledger before calling the asymmetry drift.** Any future claim that an action is missing an event must check that file first.

---

## 3. Theme C — service-layer ORM writes and a write N+1

`enforce_no_orm_writes.py` guards the *presentation* layer only, so these pass every hook. They are convention drift, not rule violations — but the repository method exists in each case.

### C1 [Medium, new] `set_seeds` writes one row at a time

`application/services/bracket_service.py:405-408`:

```python
for entry_id, seed in seeds.items():
    entry = entry_by_id[entry_id]
    entry.seed = seed
    await entry.save()
```

One round-trip per entry — a 64-entrant reseed is 64 sequential UPDATEs on the shared event loop, in an app whose capacity work this window was specifically about not blocking it. The validation above (`:382-403`) is careful and correct; only the write is. **Suggested fix:** a `bulk_update` on the repository, or a single `.update()` per distinct seed.

### C2 [Low, new] Three direct saves where a repository method exists

- `bracket_service.py:320-321` — `drop_entrant` does `entrant.status = …; await entrant.save()`, while `update_bracket` in the same class correctly uses `self.repository.update` (`:181`).
- `bracket_service.py:136-137` — `create_bracket` writes `tournament.save(update_fields=['allow_player_match_requests'])`, a **cross-aggregate write onto `Tournament` from `BracketService`**, bypassing `TournamentRepository`. The behaviour is well-reasoned and commented (`:132-134`); the write path is the issue.
- `_bracket/series.py:91` — as noted in B2.

---

## 4. Theme D — guardrail precision drift

The hook suite is this repo's best engineering-practices asset: **all 24 scripts in `.claude/scripts/` are wired into `settings.json`** — no dead guardrails — and 21 of them are clean tree-wide. Two are not, and both fire on unmodified `main`.

### D1 [Medium, pre-existing] `check_layer_exports.py` demands a private base be made public

Running it over the tree flags exactly one file:

```
EXPORT CONVENTION VIOLATION in 'application/repositories/_crew_repository.py':
  CrewRepository is defined but not exported from '.../__init__.py'.
```

`CrewRepository` (`_crew_repository.py:19`) is a `Generic[T]` base consumed by exactly two siblings (`commentator_repository.py:12`, `tracker_repository.py:12`). It lives in a deliberately underscore-prefixed module, and the **previous audit cited it as an example of a shared helper in the right place**. Exporting a type-parameterized base from the package's public `__all__` would be wrong.

The cause is at `check_layer_exports.py:33`: eligibility keys purely on the `_repository.py` filename suffix and never tests for a leading underscore. `_base.py` and `_tenant.py` escape only by accident — their names don't end in `_repository.py`. I confirmed this by running the hook against all three: `_base.py` → exit 0, `_tenant.py` → exit 0, `_crew_repository.py` → exit 2. **Suggested fix:** return `None` from `package_for()` when the basename starts with `_`.

### D2 [Medium, pre-existing] `check_secret_leak.py` flags two non-secrets

Two files flagged tree-wide, neither a secret:

- `application/services/api_token_service.py:25` — `TOKEN_PREFIX = 'wizzrobe_pat_'`, a public, non-sensitive prefix that by design appears in every token.
- `application/utils/clients/challonge_client.py:34` — `TOKEN_URL = 'https://api.challonge.com/oauth/token'`, a documented public OAuth endpoint sitting between `AUTHORIZE_URL` and `BASE_URL`, neither of which is flagged.

**Suggested fix:** exempt names ending `_PREFIX`/`_URL`, or any value parsing as an `https://` URL.

**Why D1/D2 rate Medium rather than Low.** Neither is a code defect. But both fire on *every* edit to those files, and a guardrail suite is only as trusted as its noisiest member — the failure mode is contributors learning to skim past hook output, which silently disarms the eleven hooks that are catching real bugs. This is the cheapest high-leverage fix in the report.

---

## 5. Theme E & F — module budget and error reporting

### E1 [Medium, new] Two live 800-line budget violations, both crossed this window

`check_file_length.py` sets `SOFT_LIMIT = 800`. Two files exceed it, and each is the largest module in its tree:

| File | Lines | Crossed at |
|---|---|---|
| `application/services/match/match_schedule_service.py` | 815 | `5265539` — "Merge the bracket and the schedule into one system", 2026-07-26 |
| `scripts/seed_dev.py` | 801 | during the bracket seed work, 2026-07-23 |

The hook is registered as **PostToolUse**, which by design cannot block a write (its own docstring says so) — it warned and the code landed. `match_schedule_service.py` is the more urgent of the two: it grew +482 lines this window absorbing the bracket integration, and it is a service, not a fixture script. **Suggested fix:** split the bracket-integration seam out of `match_schedule_service.py`; treat `seed_dev.py` (1 line over) as a watch item.

### F1 [Medium, pre-existing] A swallowed Challonge failure goes to stdout, not the logger

`application/services/challonge_service.py:589-593`:

```python
try:
    await self._sync_tournament(cmatch.tournament, actor, force=True)
except (ValueError, ChallongeAPIError) as e:
    print(f"[challonge] post-push re-sync failed for tournament "
          f"{cmatch.tournament_id}: {e}")
```

The comment above it is right that the failure must not undo the push. But `print()` means this never reaches structured logs or Sentry — a silently stale bracket with no diagnostic trail. And `challonge_service.py` (600 lines) has **no logger at all**: it is one of the few service modules with no `getLogger` call, against 44 modules that have one. **Suggested fix:** add `logger = logging.getLogger(__name__)` and use `logger.warning(..., exc_info=True)`.

### F2 [Low, pre-existing] `print()` on the real Discord bot-ready path

`application/services/discord/discord_service.py:133` prints bot-ready on the live (non-mock) path, in a module that already defines `logger` at `:17`. The other nine `print()` calls in that module, plus `challonge_client.py:366`, are deliberate `MOCK_DISCORD`/`MOCK_*` dev-mode output and `main.py:239` is CLI guidance — all correct as they stand.

### F3 [Low, pre-existing] Three "coroutine was never awaited" warnings in the suite

The green run emits three `RuntimeWarning: coroutine '…' was never awaited`:

- `application.repositories._tenant._scoped` (surfacing via `_pytest/stash.py:108`)
- `WebhookService._deliver_one`, from `tests/services/test_webhook_service.py:200`
- a `_DummyDiscord.send_dm_with_volunteer_acknowledgment_button` stub, via `tests/conftest.py:68`

The webhook one is **deliberate** — the stub at `:198-201` explicitly calls `coro.close()` to assert on enqueued coroutines without running them. The other two look like stubs that accept a call and drop the coroutine. Harmless today, but this warning class is also how a genuinely un-awaited service call hides, so it is worth driving to zero (close the coroutine in the stubs) rather than living with three permanent ones. **Suggested fix:** `close()` the coroutine in the `_DummyDiscord` stub and the `_scoped` call site, then consider `-W error::RuntimeWarning` for that class.

---

## 6. Positives worth preserving

**Every mechanical rule is clean across the whole tree.** Verified by sweep, not sampled:

- Zero `application.repositories` imports in `pages/`, `theme/`, `api/`, `discordbot/`; zero `service.repository.*` reach-through anywhere.
- Zero NiceGUI imports in the service layer, bar six deliberate lazy `from nicegui import app` calls inside `tenant_context.py` / `tenant_session.py`.
- Zero bare `asyncio.create_task`/`ensure_future` outside `main.py:85` (the bot task) and three tests; zero `Client.current`; zero `requests`/`time.sleep` in runtime code.
- 21 of 24 hooks clean tree-wide, and **all 24 wired** into `settings.json`.
- The mobile-grid rule holds at every `ui.table()` site (13 checked individually against the hook).
- Zero `TODO`/`FIXME`/`XXX`/`HACK` in runtime source.
- Docs in lockstep: all **59** `Model` subclasses appear in `docs/reference/data-model.md`.
- 133 test files carrying 2,478 test functions, which parametrize out to 3,161 passing tests — with exactly one `skipif` marker in the whole suite and zero `xfail`s.

**The Swiss engine is cross-validated against a reference implementation.** `tests/services/test_bracket_swiss_crossvalidation.py` checks the in-house Swiss pairer against bbpPairings, a FIDE-grade implementation — and `.github/workflows/test.yml:78-88` clones and builds that binary in CI so the check actually executes rather than skipping. Building a third-party binary in CI to validate your own algorithm is a level of rigor worth protecting; the local skip is a convenience, not a gap.

**`bracket_repository.py` is the model to copy, not refactor.** Every read goes through `scoped()`; every create stamps `current_tenant_id()`; and each of the four deliberately-**unscoped** worker reads carries a docstring justifying why a scoped read would raise and why the exemption is safe (`:264-275`, `:277-291`, `:293-312`). `settle_game` (`:314-327`) is a compare-and-swap whose docstring names the exact double-count race it prevents — *"counting one game's win twice would let a Bo3 'clinch' 2-0 off a single game."* This is what the rest of the repository layer should read like.

**Previous-audit remediations verified landed** (each re-checked against `ec743eb`, not taken on trust):

| Prior finding | Status |
|---|---|
| §1.1 stream-room dialog `AttributeError` | Fixed — `stream_room_dialog.py` no longer touches the broken attribute |
| §1.2 blocking Discord HTTP during login | Fixed — `pages/auth.py:329` uses `asyncio.to_thread` |
| §1.3 stub randomizers raising `NotImplementedError` | Fixed — zero occurrences in `seedgen_service.py` |
| §2A.2 repository update boilerplate ×20 | Fixed — `TenantScopedRepository` (`_base.py`); the `setattr` loop exists at exactly one site tree-wide (`_base.py:46`) |
| §8 `_load_*_or_404` + 404/400 drift | Mostly fixed — `NotFoundError → 404` in `ServiceErrorRoute` (`api/dependencies.py:197-225`); residual in A3 |
| §9 admin CRUD-tab scaffolding | Partly fixed — `theme/tables/admin_crud.py` shipped; adoption incomplete (A2) |
| §11 test fixture duplication | Fixed — `app`, `stub_discord_queue`, `two_tenants`, `two_tenant_api` all hoisted into `tests/conftest.py` |
| §12 real outbound HTTPS in CI | Fixed **and ratcheted** — the autouse `_no_external_network` fixture (`tests/conftest.py:71-97`) monkeypatches `socket.connect` to raise on any non-loopback address, so the class cannot recur |
| §2D "Low" `random.seed(1234)` unrestored | Fixed — now wrapped in `getstate`/`setstate` with `try/finally` (`test_utils_coverage.py:479-489`) |
| §13 `CLAUDE.md` Role enum count | Fixed — `CLAUDE.md:125` says eleven |

The `_no_external_network` fixture is the template for how every finding in this report should ideally be closed: not just fixed, but made mechanically unrepeatable.

---

## 7. Leverage-ordered remediation

Ordered by debt removed per unit of effort, safest first. Each wave should leave the tree green.

**Wave 1 — restore guardrail trust (tiny diff, highest leverage).**
Fix D1 (`package_for()` skips `_`-prefixed basenames) and D2 (exempt `*_PREFIX`/`*_URL`). Two small edits take the hook suite from 21/24 clean to 24/24, which is the precondition for everything below being *enforced* rather than merely recommended.

**Wave 2 — widen and adopt `write_and_publish`.**
Add an optional `event_details`/`event_extra` parameter, convert the 13 drop-in sites, delete `race_room_service._audit_and_emit`, then migrate as many of the 24 divergent sites as the widened signature allows. Largest single DRY win in the report, and the diagnosis in A1 makes it mechanical rather than judgment-heavy.

**Wave 3 — close the audit gaps.**
B1 (`enroll`), B2 (`set_best_of` — audit *and* route through the repository), B3 (`update_note`). Decide B4 explicitly and record the decision in `event_types.py` the way the qualifier block does.

**Wave 4 — service-layer write hygiene.**
C1 (`set_seeds` → bulk update; the clearest correctness-adjacent win, since it runs on the shared event loop), then C2's three direct saves.

**Wave 5 — module budget and logging.**
Split the bracket-integration seam out of `match_schedule_service.py` (E1). Give `challonge_service.py` a logger and convert F1; convert F2.

**Wave 6 — opportunistic DRY.**
Migrate admin tabs onto `ServiceTableView` largest-first (A2); hoist `_load_user_or_404` into `api/_helpers.py` (A3).

**Close the loop (do this with Wave 2, not after).**
Extend `check_dry_regressions.py` — which today references none of these primitives — to block:
1. `write_log(...)` followed by `event_bus.publish(...)` in the same function, naming `AuditService.write_and_publish` in the block message;
2. a new private `_audit_and_*` wrapper in `application/services/`;
3. a new `_load_*_or_404` whose body is a bare `require_found` one-liner already present in another router.

`check_dry_regressions.py` is the model the previous audit named for this, and A1–A3 are the evidence that an extraction without one decays back into optional style.

---

## 8. Remediation status

Landed in the same branch as this report, in the leverage order of §7. The full
suite is green and **all 24 guardrail hooks are clean tree-wide** (they were
21/24 when the report was written).

### Shipped

| Finding | What changed |
|---|---|
| **D1** | `check_layer_exports.py` now skips underscore-prefixed modules — `_crew_repository.py`, `_base.py` and `_tenant.py` are package-private by convention. |
| **D2** | `check_secret_leak.py` gained `is_public_config()`: names ending `_URL`/`_PREFIX`/… are exempt **only when the value is also benign**. A `*_URL` carrying userinfo (`user:pw@host`) or a query credential (`?access_token=…`) is still flagged. Verified against a probe covering both directions. |
| **A1 (partial)** | `write_and_publish` gained `event_extra=` / `event_details=`, and **15 sites** migrated: the 12 mechanical drop-ins (10 in brackets), `race_room_service._audit_and_emit` (now builds its detail dict then delegates), and crew signup/undo. Five now-dead `Event`/`event_bus` imports removed. |
| **A3** | `load_user_or_404` hoisted into `api/_helpers.py`; the three byte-identical copies deleted and their orphaned imports cleaned. |
| **B1** | `BracketService.enroll` now writes `BRACKET_ENTRY_ADDED` (new audit action, registered in the eventless ledger). |
| **B2** | `set_best_of` now audits `BRACKET_UPDATED` and writes via `repository.update_match`. |
| **B3** | `update_note` now audits `VOLUNTEER_NOTE_UPDATED` (new action, ledgered as tenant-internal/personal). |
| **C1** | `set_seeds` → `BracketRepository.set_entry_seeds`: one statement per distinct seed instead of one UPDATE per entry. A 64-entrant reseed drops from 64 sequential round-trips to a handful. |
| **C2** | `drop_entrant` → `update_entrant`; `create_bracket`'s cross-aggregate write → `TournamentRepository.update`; `set_best_of` → `update_match`. Three named `update_*` methods added to `BracketRepository` for its five-model aggregate, each delegating to the one shared setattr-and-save. |
| **E1** | `match_schedule_service.py` **815 → 409** lines: notifications extracted to `_schedule_notifications.MatchNotificationMixin`, with `_match_recipients.py` and `_dm_context.py` holding what both halves share (the original module re-exports them, so external lazy importers are unaffected). `seed_dev.py` **801 → 768** via `seed_observability_for_tenant`, following the existing `seed_*_for_tenant` convention. |
| **F1** | `challonge_service.py` gained a module logger; the swallowed post-push re-sync failure is now `logger.warning(..., exc_info=True)` instead of `print()`, so it reaches Sentry. |
| **F2** | Discord bot-ready `print()` → `logger.info`. |
| **Loop closed** | `check_dry_regressions.py` gained two rules — `audit-publish-pair` (a new `write_log` → `event_bus.publish` sequence) and `local-audit-emit-wrapper` (a new private `_audit_and_*`). Both verified to fire on a planted regression and to stay silent on a verbatim rewrite of every existing service. `CLAUDE.md`'s event-publishing section was rewritten to teach `write_and_publish` first, since it previously documented the exact shape the new rule blocks. |

### Deliberately not done

- **A1, the remaining ~22 divergent sites.** Migratable in principle, but 17 test
  files stub `audit_service.write_log` and assert on its call args, so converting
  them means churning assertions across all 17 — a large, risky diff for a pure
  DRY win on sites that behave correctly today. The widened signature plus the new
  hook mean the *next* site written gets it right; the backlog can be worked
  file-by-file. **Two sites must not be mechanically converted**:
  `crew_service.update_crew_approval` (`:196`) and `acknowledge_crew_assignment`
  (`:257`) audit **conditionally** but publish **unconditionally** — folding them
  into one call would silently make the event conditional. Whether that asymmetry
  is intentional (a UI-refresh nudge) or a latent bug is an open question worth its
  own look.
- **A2** (12 admin tabs onto `ServiceTableView`) — mechanical but broad; genuinely
  opportunistic, best done per-tab alongside other work in each file.
- **F3** (three `coroutine was never awaited` warnings) — investigated and left.
  The webhook one is deliberate (`coro.close()` at `test_webhook_service.py:198`),
  and the other two are GC-timing artefacts surfacing at the point where
  `conftest.py` *already* closes captured coroutines. No un-awaited service call
  hides behind them.

### Retracted

- **B4** — the fix attempt tripped the `test_event_audit_parity` ratchet, which
  revealed the omission was a documented decision. See §2 B4. Net effect: one
  finding disproved by trying to fix it, which is the cheapest possible way to
  learn a finding was wrong.

### Test-visible consequences of the code motion

Two test files needed updating, both legitimately:
`test_match_schedule_coverage.py`'s fan-out assertions compare `__qualname__`,
which now reads `MatchNotificationMixin.notify_*` (7 strings), and
`test_crew_service.py`'s `audit_service` stub needed `write_and_publish` added
beside `write_log`. Nothing else in 3,161 tests was coupled to the split — the
`MatchPlayers.filter`-style patch targets kept working because they patch the
shared model class, not the module that references it.
