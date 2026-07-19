# Wizzrobe — Project Structure, Best-Practices & Scalability Review

**Date:** 2026-07-02  **Scope:** whole repository (~270 Python files, ~37.6k LOC)
**Method:** 10-dimension parallel review with adversarial verification (see [Methodology](#methodology)).

---

## 1. Executive summary

Wizzrobe is a **well-architected codebase for its size and stage.** The three-layer
pattern (presentation → service → repository → models) is not just documented — it is
*mechanically enforced* by a suite of `.claude/` PreToolUse hooks, and the enforcement
holds: zero ORM writes and zero repository imports leaked into `pages/`/`theme/`, no
service imports NiceGUI, and repositories are genuinely pure data access. Tests mirror the
service layer nearly 1:1, the REST API and the web UI share one business layer, and the
docs are unusually honest and current. This is a repo a new contributor can learn quickly.

The debt is **concentrated, not diffuse.** It clusters in five places:

1. **One live data-loss bug** — deleting a stream room hard-deletes every match ever
   assigned to it (unintended `ON DELETE CASCADE`), exposed at a REST endpoint.
2. **The match domain's "god-file trio"** — `match_service.py` (1181 lines),
   `theme/tables/match.py` (1144), `theme/dialog/match_dialog.py` (667) — where the same
   logic is written 2–6 times and glued by a fragile positional-tuple contract.
3. **The entry surfaces the architecture never defined** — `api/`, `discordbot/`,
   `middleware/` — which bypass services into repositories and, in one case, hold a
   business rule the service layer lacks.
4. **Observability of the background/notification half** — Discord DM failures, seed
   generation, and live-update errors all report via `print()`, invisible to the Sentry
   integration the project deliberately set up.
5. **The single-process ceiling** — six in-process singletons pin the app to one worker.
   This is a documented, reasonable tradeoff today, but it lacks a written escape plan and
   a fail-fast guard.

Nothing here requires a rewrite. Every item is an **incremental, mechanical fix**, and the
patterns needed to fix them already exist in-repo as proof points (`_transition` template
method, generic `CrewRepository`, the `match_events` decoupling seam,
`volunteer_reminder`'s idempotent stamp).

### Overall health verdict

> A disciplined three-layer application whose architecture is genuinely enforced and whose
> weak spots are legible and bounded. Fix the one cascade-delete data-loss path this week,
> put the background failure paths on the logger, and start chipping the match-domain
> god-files apart along the seams the codebase already demonstrates. Left unaddressed, the
> match trio and the scattered configuration will make each new match-adjacent feature
> progressively more expensive; addressed incrementally, this codebase scales comfortably
> to the next tier of features and contributors. **Grade: B+ (solid, with one urgent fix).**

### Dimension scorecard

| Dimension | Health | Headline |
|---|---|---|
| Layer discipline | 🟢 Strong | Enforced boundary holds in UI; drift only at `api/`/`discordbot/` edges |
| Package structure | 🟢 Strong | Clean; god-file trio + mislabeled `middleware/` are the debts |
| Runtime scalability | 🟡 Watch | Unbounded match load on the public hot path; sync OAuth blocks the loop |
| Growth scalability | 🟡 Watch | Match domain pays a 2–6× copy tax; config scattered across 12+ modules |
| NiceGUI / async | 🟢 Strong | Worst anti-patterns eliminated & hook-enforced; ~4 background-task slot bugs remain |
| API / security | 🟢 Strong | Excellent token model & OAuth CSRF; edge gaps (`is_active`, rate-limit key) |
| Data model | 🟠 **Action** | **Unintended CASCADE data-loss path**; missing unique constraints & indexes |
| Testing / CI | 🟡 Watch | Great service coverage; auth gate, UI, and Postgres/migrations untested |
| Error / audit / observability | 🟡 Watch | Request path excellent; background path runs on `print()` |
| Docs accuracy | 🟢 Strong | Load-bearing refs in sync; `CLAUDE.md` Role list is stale |

Legend: 🟢 healthy · 🟡 watch/plan · 🟠 needs action · 🔴 urgent

---

## 2. Critical & high-priority findings (verified)

Each finding below was **independently verified against source** during this review (see
the ✓ tags). `file:line` references are clickable.

### 🔴 CRITICAL — Deleting a StreamRoom hard-deletes every match assigned to it

- **Where:** `models.py:257` / `models.py:266`; live path `application/services/stream_room_service.py:85` → `api/routers/stream_room_actions.py`
- **What:** `Match.stream_room` and `Match.generated_seed` are nullable FKs declared with
  **no `on_delete`**, so they inherit Tortoise's default `CASCADE`. The init migration
  confirms it: `migrations/models/0_20260608213149_init.py:76-77` —
  `"stream_room_id" INT REFERENCES "streamroom" ("id") ON DELETE CASCADE`. Deleting a stream
  room therefore deletes **every match ever assigned to that room** (historic and upcoming),
  which cascades into `matchplayers`, `matchacknowledgment`, `commentator`, `tracker`, and
  `matchwatcher`. `delete_stream_room` has no guard, and it's exposed at
  `DELETE /api/stream-rooms/{id}`. The fields being nullable proves detach (`SET_NULL`) was
  the intended semantic — `ChallongeMatch.match` already does this correctly with
  `on_delete=fields.SET_NULL` (`models.py:675`).
- **Fix (small):** Change both FKs to `on_delete=fields.SET_NULL` (already `null=True`) +
  aerich migration; add a `ValueError` guard in `delete_stream_room` when referencing
  matches exist, steering admins to the existing `is_active` soft-retire flag.
- **Verified:** ✓ model + migration DDL + live delete endpoint all confirmed.

### 🟠 HIGH — Attribution & history FKs default to CASCADE, destroying *other users'* records

- **Where:** `models.py:396` (AuditLog.user), `:429` (UserRole.granted_by), `:361`/`:371`
  (Commentator/Tracker.approved_by), `:189-193` (EquipmentLoan borrower/checked_out_by/checked_in_by)
- **What:** Deleting user A cascade-deletes rows that belong to user B and erases history:
  A's entire **audit trail** vanishes (`init.py:104` `user_id ... ON DELETE CASCADE`); role
  grants A made *for B* are deleted, revoking B's access (`init.py:186`); B's crew signups
  are deleted because A approved them (`init.py:112`,`166`); the equipment loan rows the
  model's own docstring calls "the asset's full lending history" are deleted
  (`12_add_equipment.py:30-32`). The team already knows the right pattern — the *newer*
  `TriforceText.approved_by` (`init.py:178`) and `VolunteerAssignment.checked_in_by`
  (`13_...:8`) correctly use `SET NULL` — it just was never applied backward.
- **Fix (medium):** One migration pass — `SET_NULL` on nullable attribution FKs
  (`granted_by`, `approved_by×2`, `checked_in_by`, `AuditLog.user` made nullable),
  `RESTRICT` on non-nullable history FKs (`EquipmentLoan.borrower`, `checked_out_by`) so a
  user with lending history can't be hard-deleted. Persist actor username/discord_id into
  `AuditLog.details` so attribution survives the FK nulling.
- **Verified:** ✓ migration DDL confirmed for all cited FKs, including the `SET NULL`
  counter-examples.

### 🟠 HIGH — Older junction tables lack unique constraints; duplicate prevention is a race

- **Where:** `models.py:301` (MatchPlayers), `:323` (TournamentPlayers), `:356`/`:366`
  (Commentator/Tracker), `:201` (UserTeams)
- **What:** These have no `unique_together` on their natural keys, while their newer siblings
  (MatchAcknowledgment, MatchWatcher, UserRole, VolunteerAssignment, VolunteerQualification)
  all do. Uniqueness rests entirely on check-then-insert in services — a TOCTOU race under
  the shared event loop (double-click, concurrent API call). `docs/reference/data-model.md:317`
  itself concedes: "No unique constraint on (tournament, user) — duplicate-enrollment
  prevention relies on … checks."
- **Fix (medium):** Add `unique_together` on each natural key; write the aerich migration
  with a preceding dedupe (`DELETE … keep MIN(id)`). Keep the service checks for friendly
  errors, but let the DB be the arbiter.
- **Verified:** ✓ (docs concede it; newer models show the contrast).

### 🟠 HIGH — Unbounded match load on the public hot path

- **Where:** `theme/tables/match.py:658`
- **What:** `MatchTableView.refresh()` calls `get_matches_for_display(only_upcoming=False)`
  ("# Get all matches") then filters state in a **Python list comprehension**. The repo query
  has no limit/offset and prefetches 9 relations; `ui.table` pagination is commented out.
  The public home-page schedule mounts this for **anonymous visitors**, so cost grows linearly
  with total match history per connected client. Compounding it: every `match.created` event
  makes the realtime bridge fire a **full unbounded reload for every connected client**
  (`theme/tables/match.py:640`), a query stampede exactly at peak event load.
- **Fix (medium):** Push the state filter into the repository query, default the UI to
  `only_upcoming=True` with an explicit "show past" toggle + date bound, set a real
  pagination dict on `ui.table`. For CREATED events, fetch just the one new match and
  append the row (mirroring the existing `update_row_by_id` path CHANGED/DELETED already use).
- **Verified:** ✓ unbounded load and "Get all matches" comment confirmed.

### 🟠 HIGH — Synchronous Discord OAuth calls block the shared event loop on every login

- **Where:** `middleware/auth.py:181`
- **What:** The OAuth callback makes two **synchronous** HTTPS calls to Discord
  (`discordClient.oauth.get_access_token(...)` and `bearer_client.users.get_current_user()`
  — zenora is a requests-based client, called **without `await`** inside `async def`),
  freezing the entire loop — all users' UI, websockets, REST, and the bot heartbeat — for
  each login. Login bursts at event check-in serialize the whole app. Directly violates
  `CLAUDE.md`'s own "never block the event loop" rule.
- **Fix (small):** Wrap both calls in `await asyncio.to_thread(...)`, or replace zenora with
  two `httpx.AsyncClient` calls (the app already depends on httpx).
- **Verified:** ✓ both sync calls confirmed with no `await`.

### 🟠 HIGH — `is_active` deactivation is enforced on the API but not the web UI

- **Where:** `api/dependencies.py:48` (enforced) vs `middleware/auth.py:185` (not)
- **What:** A user deactivated by Staff is rejected by the REST API, but can still log in via
  Discord OAuth and use every page/action their roles allow — nothing in the web auth path
  checks `User.is_active`. A repo-wide grep confirms `is_active` never appears in
  `middleware/auth.py` or `auth_service.py`.
- **Fix (small):** Refuse login in `oauth_callback` when the resolved user is inactive, and
  treat inactive users as unauthenticated in `get_user_from_discord_id`/`protected_page`.
- **Verified:** ✓ `middleware/auth.py` absent from the `is_active` grep hit-list.

### 🟠 HIGH — Match lifecycle transitions implemented twice with divergent rules

- **Where:** `application/services/match_service.py:734,766` vs `match_schedule_service.py:113`
- **What:** `MatchService.seat_players`/`finish_match` duplicate the `MatchScheduleService`
  versions but enforce **different rules** (MatchService.finish only checks `seated_at`, never
  double-finish; MatchScheduleService requires `started_at` and rejects double-finish). The
  `MatchService` variants have **zero production callers** (UI + REST both use
  `MatchScheduleService`) — yet `tests/services/test_match_service.py:381-401` actively tests
  the dead permissive variant, cementing the divergence so a future dev could wire it by accident.
- **Fix (small):** Delete `MatchService.seat_players`/`finish_match` and their tests;
  `MatchScheduleService._transition` is already the correct single template.
- **Verified:** ✓ grep confirms only test callers of the MatchService variants; guard divergence confirmed.

### 🟠 HIGH — Crew-signup "closed after finish" rule lives only in the Discord handler

- **Where:** `discordbot/crew_signup.py:70`; missing from `application/services/match_service.py:836`
- **What:** The `if match.finished_at is not None` guard exists only in the Discord button
  path. `MatchService.signup_crew` never checks it, so the **web UI and REST API allow crew
  signup on finished matches** — and the public schedule renders live "Sign Up" buttons on
  finished matches.
- **Fix (small):** Move the guard into `MatchService.signup_crew` as a `ValueError` (all
  three callers already handle that pattern); delete the Discord-only check.
- **Verified:** ✓ (workflow verifier confirmed; guard present only in bot handler).

### 🟠 HIGH — Challonge scheduling section on the player dashboard is dead code + a latent NameError

- **Where:** `pages/home_tabs/player.py:155` (+ `:45`)
- **What:** `challonge_section` is an **async `@ui.refreshable` called without `await`** from
  a *sync* `render_player_dashboard`, so its body never executes — the "Upcoming matches to
  schedule" section silently never renders. And if it ever did run, line 45 references
  `challonge_container`, which is **assigned nowhere in the repo** (grep finds exactly one
  use, zero definitions) → `NameError`.
- **Fix (small):** Make the dashboard async and `await challonge_section()`; delete the
  undefined `with challonge_container:` wrapper.
- **Verified:** ✓ bare call + `challonge_container` never assigned, both confirmed.

### 🟠 HIGH — Background-task UI handlers fail silently (empty slot context)

- **Where:** `theme/error_page.py:73`, `pages/admin_tabs/admin_challonge.py:95`,
  `theme/dialog/_helpers.py` (Enter-to-submit)
- **What:** Several handlers scheduled via `background_tasks.create(...)` call `ui.notify` /
  `ui.dialog` / `ui.run_javascript` **without capturing `context.client`** and re-entering
  it. In NiceGUI 3.x a background task starts with an empty slot stack, so these raise
  `RuntimeError` server-side and the user sees **nothing**: the error-report button on 50x
  pages never opens, the Challonge per-tournament **Sync button gives no feedback and leaves
  a stale "Last synced"** (the raise happens before the refresh lines), and Enter-to-submit
  in dialogs silently fails. The correct `context.client` capture *is* applied in the
  high-traffic handlers — it's just missing on these secondary paths.
- **Fix (small):** For direct button handlers, pass the coroutine to `on_click` directly (no
  `background_tasks.create`) so NiceGUI awaits it in slot context; fix `submit_on_enter` once
  to enter the dialog slot, covering all 13 dialogs.
- **Verified:** ✓ code paths confirmed (bare tasks calling UI fns; refresh unreachable after raise).

### 🟠 HIGH — Background/notification failures are invisible: `print()`, no traceback, no Sentry

- **Where:** `application/services/discord_queue.py:15`, `application/match_events.py:46`,
  `application/services/match_schedule_service.py` (10 sites), `seedgen`/`generate_seed`
- **What:** Every DM failure, live-update subscriber error, and Challonge auto-push error
  reports via `print(f"... {e}")` — discarding the traceback and bypassing the Sentry logging
  integration the project explicitly configured. Separately, `generate_seed` wraps its whole
  body in `except Exception as e: return False, f"Error generating seed: {str(e)}", None`
  (`match_schedule_service.py:245`) with **no log**, and returns raw `str(e)` (which can
  include randomizer HTTP URLs) straight to admins and to the REST 400 detail. During a live
  event a token expiry or rate-limit storm produces only unstructured stdout noise.
- **Fix (small):** Add `logger = logging.getLogger(__name__)` to the three modules and replace
  `print` with `logger.exception`/`logger.warning`; log before `generate_seed`'s return and
  return a generic message. Prerequisite: add `logging.basicConfig(...)` in `main.py` (there
  is **no logging configuration anywhere** today — `info` logs are dropped, warnings have no
  timestamps).
- **Verified:** ✓ all `print()` sites and the swallowing `except` confirmed.

### 🟠 HIGH — Mutating UI handlers call services with no `try/except` → silent no-op

- **Where:** `pages/admin_tabs/admin_volunteers.py:156` (unassign), `:262` (generate_shifts),
  `:298` (auto_fill), `:309` (clear_draft)
- **What:** These mutating handlers call services **bare**, violating the project's own
  `ValueError`/`PermissionError` → `ui.notify` convention. On failure (e.g. a coordinator
  permission check), the Quasar chip has already removed itself client-side, the notify/refresh
  never run, and **the UI shows the volunteer gone while the DB still has the assignment**.
  No `app.on_exception` fallback is registered anywhere. Sibling handlers in the same file wrap
  correctly — the convention is known but inconsistently applied.
- **Fix (small):** Wrap the four handlers in the standard `except (ValueError, PermissionError)`
  pattern + refresh in `finally`; register a NiceGUI-global exception hook as a backstop.
- **Verified:** partially — reviewer AST scan (225 call sites: 85 wrapped, 140 not); the four
  named mutation sites are the actionable core.

### 🟠 HIGH — Hardcoded third-party credential committed to source

- **Where:** `application/services/seedgen_service.py:156`
- **What:** The default Map Rando spoiler token is the literal
  `'SpeedGamingLive2025IsTheBestTournamentEverAndEverLOL'`, committed in source. Anyone with
  repo access can unlock spoiler logs for tournament race seeds — the exact competitive-integrity
  asset this app protects. The project otherwise avoids committed secrets (guardrail hook
  `check_secret_leak.py`); this predates it.
- **Fix (small):** Require `SMMAP_SPOILER_TOKEN` and raise `ValueError` when unset (the pattern
  already used for `OOTR_API_KEY`); **rotate the token** on maprando.com since it is public in
  git history.
- **Verified:** ✓ literal default confirmed.

### 🟠 HIGH — CI: container publish is not gated on tests; no Postgres/migration testing; no lint/type gates

- **Where:** `.github/workflows/publish.yml`, `test.yml`, `tests/conftest.py:27`, `pyproject.toml:30`
- **What:** Three related CI gaps:
  1. `publish.yml` triggers on every push to `main` with **no `needs:`/`workflow_run` gate**,
     so a red test suite still ships `:latest` to GHCR.
  2. Tests run only on **in-memory SQLite** with `generate_schemas()`; production is
     PostgreSQL built by **14 aerich migrations that CI never applies** — a drifted migration
     or dialect difference first surfaces on deploy.
  3. **No ruff/mypy/coverage** anywhere — `CLAUDE.md` mandates "type hints throughout" and layer
     boundaries, but the only mechanical enforcement is the `.claude/` hooks, which run **only
     during Claude Code sessions**; a human PR bypasses every guardrail and CI stays green.
- **Fix (medium):** Gate publish on a pytest job (`needs:`); add a `postgres:16` service
  container that runs `aerich upgrade` from empty + re-runs the suite against Postgres; add
  ruff + mypy + a CI step that runs the sweep-capable `.claude/scripts` guardrails
  (`enforce_import_resolution.py` already has a whole-repo mode) so conventions bind for all
  contributors.
- **Verified:** ✓ workflows are independent; SQLite-only fixture; dev deps confirmed.

### 🟠 HIGH — Untested critical surfaces: web auth gate, presentation layer, Discord handlers

- **Where:** `middleware/auth.py`, `pages/`+`theme/` (~9.9k LOC, 28% of repo), `discordbot/`
- **What:** `AuthMiddleware`, `protected_page`, `_matches_protected_route`, and the OAuth
  state/CSRF validation are the **sole access control** for every page — and **no test imports
  them**. The entire presentation layer (including the two biggest files) and all Discord
  interaction handlers likewise have zero tests, so a page that crashes on render or a dead
  Discord button ships with a green CI.
- **Fix:** `_matches_protected_route` and the role gate are cheap pure-logic unit tests (do
  first). Add a thin NiceGUI smoke tier (`nicegui.testing`) asserting each protected page
  renders for an authorized user and 403s otherwise. Test bot handlers via `SimpleNamespace`
  interactions like `tests/services/conftest.py` already fakes Discord.
- **Verified:** ✓ grep confirms no test references `middleware`(auth), `pages.`, `theme.`, or `discordbot`.

### 🟠 HIGH — `CLAUDE.md` misstates the Role enum (lists 3, code has 7)

- **Where:** `CLAUDE.md:79` vs `models.py:7-14`
- **What:** The always-loaded guide says the Role enum is `STAFF, PROCTOR, STREAM_MANAGER`,
  but the code defines **seven** (adds `TRIFORCE_SUBMITTER, VOLUNTEER_COORDINATOR,
  EQUIPMENT_MANAGER, VOLUNTEER`), and `pages/admin.py` gates tabs on the undocumented roles.
  Contributors/AI designing permission checks from `CLAUDE.md` model a third of the real system.
- **Fix (small):** List all seven (or link to `docs/features/role-based-auth.md` as canonical
  and stop duplicating). Consider a hook that greps the `CLAUDE.md` list against `models.Role`.
- **Verified:** ✓ 7 members confirmed in `models.py`.

---

## 3. Prioritized roadmap

Findings deduped across dimensions and ordered by value/effort.

### Now (this week) — correctness & safety, all small

1. **Fix the CASCADE data-loss path** — `Match.stream_room`/`generated_seed` → `SET_NULL` +
   guard `delete_stream_room`. *(the critical one)*
2. **Fix the attribution/history CASCADEs** — `AuditLog.user`, `granted_by`, `approved_by×2`,
   equipment-loan FKs. One migration pass.
3. **Remove the hardcoded Map Rando token** and rotate it.
4. **Enforce `is_active` on the web login path.**
5. **Put the background failure paths on the logger** + add `logging.basicConfig` in `main.py`
   + stop `generate_seed` leaking `str(e)`.
6. **Fix the 4 silent-failure UI handlers** in `admin_volunteers.py` + register a global
   NiceGUI exception hook.
7. **Fix the dead Challonge dashboard section** and the ~3 background-task slot-context bugs.
8. **Gate `publish.yml` on the test job**; add a `.dockerignore` and `git rm profile.html`
   (5.75 MB Scalene artifact shipped into the image; a stray local `.env` would be baked in too).
9. **Correct `CLAUDE.md`'s Role list** and add the missing `VOLUNTEER_COORDINATOR` to the
   `/admin` gate (`pages/admin.py:60`).

### Next (this month) — hardening & de-duplication

10. **Add DB indexes** on the hot paths (`Match.scheduled_at`, `finished_at`,
    `AuditLog.created_at/user_id`, key FK columns) — one migration; the newer models already
    show the `index=True` pattern.
11. **Add unique constraints** to the older junction tables (dedupe-then-migrate).
12. **Delete the duplicate `MatchService.seat_players`/`finish_match`** and the dead
    `TestModel`/`somethingelse` scaffold (+ decide on `Team`/`UserTeams`/`Announcement`).
13. **Move the finished-match crew-signup guard into the service.**
14. **Encrypt the two `ChallongeConnection` OAuth token columns at rest** (Fernet, key from env).
15. **Harden the API rate limiter** — key by client IP for unauthenticated floods, hash the
    token key, prune empty buckets (unbounded memory today), and set `ENVIRONMENT=production`
    in `start.sh prod` so the fail-closed guards actually engage.
16. **Add a Postgres+migrations CI job** and ruff/mypy.
17. **Centralize configuration** — a lazy `application/config.py` with typed accessors,
    replacing scattered import-time `os.environ` reads across 12+ modules (BASE_URL alone is
    defaulted in three places).

### Then (this quarter) — structural, incremental splits

18. **Split the match god-file trio along the seams the codebase already demonstrates:**
    - `match_service.py` → extract a `match_display_service.py` (row formatting), fold
      `signup_crew`/`undo_crew_signup` into the existing `CrewService`, collapse the three
      near-identical notification blocks into one `MatchScheduleService.notify_*` call, and
      push raw queries down into `MatchRepository`. Target ~450 lines of pure lifecycle.
    - `theme/tables/match.py` → `match_slots.py` (one parameterized Vue template each, not 6
      copies), `match_grid.py`, `match_handlers.py`.
    - **First** convert the positional tuples to small dicts so the split moves the format once.
19. **Define & enforce the `api/`/`discordbot/` layer rule** — may call services and do
    read-only load-or-404 lookups, but not import `application.repositories`. Extend
    `enforce_architecture.py`'s `classify()` to cover them; replace the direct
    `UserRepository`/`.repository` reach-through with service reads.
20. **Move the NiceGUI pages out of `middleware/`** (`challonge_oauth.py`, `mock_auth.py`, the
    `@ui.page` routes in `auth.py`) into `pages/`; keep only actual middleware in `middleware/`.
21. **Invert the `discord_service.py` ↔ `discordbot/` cycle** with a registry
    (mirroring `match_events`), removing ~20 deferred imports.
22. **Write the horizontal-scaling escape plan** into `docs/architecture.md` and **assert
    single-worker at startup** (fail fast if `workers>1`) so the six in-process singletons
    don't silently break a second replica.

---

## 4. Strengths worth preserving

These are doing real work — protect them during refactors.

- **Mechanically-enforced architecture.** `.claude/scripts/enforce_architecture.py`,
  `enforce_no_orm_writes.py`, `enforce_async_safety.py`, `enforce_import_resolution.py`,
  `check_audit_actions.py` run as PreToolUse hooks and *actually hold*: the presentation
  boundary has zero ORM writes and zero repository imports. Get these running in CI too so
  they bind for humans, not just Claude sessions.
- **`application/match_events.py` — the decoupling seam.** A deliberately NiceGUI-free
  in-process pub/sub that services publish to, bridged to the UI by `theme/realtime.py` with
  per-client cleanup on disconnect. Realtime UI with no service→UI dependency. This is the
  template for the Discord-cycle and multi-replica fixes.
- **The API token lifecycle** (`api_token_service.py`): 256-bit secrets, SHA-256 hash + display
  prefix only, shown once, expiry/revocation/last-used, inactive-account rejection, audited.
  Copy this pattern to `ChallongeConnection`.
- **Fail-closed startup gating.** `validate_security_config()` aborts on weak `STORAGE_SECRET`
  or blank prod DB creds; mock modes `raise RuntimeError` in production; Sentry scrubs
  Authorization/Cookie headers with `send_default_pii=False`.
- **Honest, current, indexed docs.** `docs/README.md` is a real coverage map; the reference
  docs verified in sync (86/86 endpoints, 30/30 services, 36/9 models/enums); the docs even
  document their own warts. Rare and valuable.
- **Tests mirror services 1:1** with clean fixtures (function-scoped in-memory DB, autouse
  discord-queue capture, rate-limiter reset). Extend this discipline to the untested layers.
- **`volunteer_reminder`'s idempotent stamp** (`reminder_sent_at` before send) — the exact
  durability pattern the match-notification queue should adopt so restarts resume instead of
  dropping.

---

## 5. Full findings index

94 findings across 10 dimensions. CRITICAL/HIGH are detailed in §2. MEDIUM/LOW/INFO summarized
here (grouped by dimension). "✓" = independently verified this review; "≈" = workflow-verified;
blank = evidenced by the reviewer but not re-verified (verification pass hit a session limit).

### Layer discipline
- **M** ✓ `api/`/`discordbot/` sit outside the enforced architecture and already import
  repositories directly (5 bot handlers import `UserRepository`; 3 routers import repos).
- **M** ✓ OAuth login provisions/mutates `User` with raw ORM in middleware, bypassing
  `UserService` + audit (`middleware/auth.py:192`).
- **M** ✓ Services bypass repositories with direct ORM at ~80 sites (57 reads/23 writes),
  contradicting `docs/refactoring-guide.md:88`.
- **M** Presentation/bot reach through `service.repository.*` (evades the import-based hook).
- **M** Identical raw `MatchPlayers` query copy-pasted into 4 bot handlers.
- **L** API read path duplicates repo prefetch knowledge (`api/_match_view.py` `MATCH_PREFETCH`).
- **L** Legacy `get_query` queryset-factory threads raw ORM through `theme/`.
- **I** View-model assembly in `MatchService`; stale `auth_service.py` NiceGUI allowlist entry.

### Package structure
- **M** ≈ `MatchService` 1181-line god-service (4+ responsibilities).
- **M** ≈ `middleware/` mostly contains NiceGUI pages, not middleware.
- **M** ≈ `discord_service.py` ↔ `discordbot/` bidirectional cycle held together by ~20 deferred imports.
- **M** ≈ Dead schema shipped to prod (`TestModel` + `Team`/`UserTeams`/`Announcement`).
- **M** ≈ `MatchTableView._setup_ui` ~550-line method w/ 16 inline Vue templates; grid slot adds ~325.
- **L** ≈ `match_dialog.py` — cohesive feature, but Admin/User `open()` are 250-line near-parallel monoliths.
- **L** ≈ Inconsistent `__init__.py` presence (8 namespace-package dirs among regular packages).
- **L** ≈ Naming drift (`triforce_texts.py` breaks `admin_` prefix + collides; schema/router mismatches; `test_api_phase5_writes.py`).
- **L** ≈ `ChallongeService` (581 lines) — two splittable halves (connection vs bracket sync).
- **I** ≈ `models.py` still coherent at 699 lines — prune before splitting; split stays cheap (app label unchanged).

### Runtime scalability
- **M** ✓ No indexes on hot-path `Match.scheduled_at`/`finished_at`, `AuditLog.created_at/user_id`, FK cols.
- **M** DB pool at Tortoise default `maxsize=5` for the whole process; no config knob.
- **M** Discord DM pipeline: single sequential worker, uncached `fetch_user` per DM, unbounded queue dropped on restart.
- **M** Architecture hard-pinned to one process (6 singletons); no path to a 2nd replica.
- **L** `GET /api/users` + admin user table return the entire (monotonically growing) user table.
- **L** ✓ API rate-limiter dict grows without bound per unique token/IP.
- **L** ✓ Discord bot started with a bare `loop.create_task`, no reference held (`main.py:57`).

### Growth scalability
- **M** ≈ `theme/tables/match.py`: player/crew Vue templates triplicated per permission variant + again in grid.
- **M** ≈ `match_service.py` mixes CRUD, presentation formatting, notification fan-out, crew signup, repo-bypassing queries.
- **M** Positional-tuple contract between service rows and JS templates → every field add is a shotgun change.
- **M** `DiscordService`: 6 copy-pasted DM-send variants + parallel mock + if/elif interaction router.
- **M** `AdminMatchDialog`/`UserMatchDialog` duplicate the entire submit pipeline despite a shared base.
- **M** Configuration scattered across 12+ modules with import-time reads; no central settings.
- **S** `CLAUDE.md` 5-step feature recipe omits REST layer, audit constants, tests, and 5 append-only registries (equipment already has no REST router as a result).
- **L** ✓ `CLAUDE.md` documents 3 roles, code has 7.
- **L** REST-API test files named by dev phase, not domain (`tests/api/` mirror recommended).
- **I** Single-process state (`match_events._subscribers`, `_seed_locks`, `_hits`) — document + assert single-worker; free the per-match seed lock (grows monotonically).

### NiceGUI / async
- **M** Live-update handlers read the *mutating* user's session storage (`app.storage.user`) — wrong-user watch icons / RuntimeError on bot-initiated changes (`theme/realtime.py:39`).
- **M** ✓ Home Schedule tab's `on_edit` dialog is both unreachable (no id column) and latently slot-broken.
- **M** ✓ Discord bot bare `loop.create_task` (also filed under runtime & error/audit).
- **L** Admin triforce-texts "refreshable" is a shell around manual clear-and-rebuild with a race.
- **L** ✓ Async infra errors reduced to `print()` (also filed under error/audit).
- **I** Synchronous preset-file reads inside async seed generation (sub-ms today; cache at import).

### API / security
- **M** ✓ Rate limiter keyed by attacker-controlled `Authorization` header → bypass for invalid-token floods + unbounded growth.
- **M** ✓ Production hardening opt-in: `start.sh prod`/Docker CMD never set `ENVIRONMENT=production`.
- **M** Session cookie issued without `Secure` flag (Starlette `SessionMiddleware` defaults) — pass `session_middleware_kwargs={'https_only': is_production()}`.
- **L** Page protection is default-open (only `protected_page` routes enforced; a forgotten decorator publishes a page).
- **L** ✓ `/admin` gate omits `VOLUNTEER_COORDINATOR` though it builds tabs for that role (fail-closed, but inconsistent).
- **L** Challonge service-account OAuth tokens stored plaintext (see data-model).
- **I** Unauthenticated public schedule exposes seed URLs + every player's Discord ID.

### Data model
- **M** ✓ (indexes — see runtime).
- **M** `User.challonge_user_id` uniqueness only service-enforced; a duplicate → `MultipleObjectsReturned` aborts bracket sync.
- **M** `ChallongeConnection` access/refresh tokens plaintext (contrast `ApiToken`'s hash+prefix in the same file).
- **L** Dead schema (`TestModel` etc.) — see structure.
- **L** `data-model.md` drifted after migration 13 (VolunteerAssignment check-in fields undocumented; stale `updated_at` claim).
- **I** Migration hygiene: mixed hand-written/generated migrations, non-reversible squashed init, unconditional auto-upgrade at startup.

### Testing / CI
- **H** ✓ (publish not gated; SQLite-only; no lint/type — see §2).
- **H** ✓ (web auth / presentation / bot untested — see §2).
- **M** Flagship service tests mock all repositories & bypass all auth (`object.__new__` + MagicMock; `bypass_auth` fixtures) — a dropped `AuthService.ensure` would still pass.
- **L** No health endpoint / no container `HEALTHCHECK`; move test-only `aiosqlite` to dev deps.

### Error / audit / observability
- **H** ✓ (print-based notification failures; `generate_seed` swallow; silent UI handlers — see §2).
- **M** ✓ No logging configuration anywhere; INFO dropped, WARNING+ has no timestamps.
- **M** ✓ Discord bot bare-task startup failure is silent (also runtime/nicegui).
- **L** ✓ OAuth login auto-creation bypasses the audit log (also layering).
- **L** Seed-DM sends discard the `(success, error)` tuple — failures leave no trace.
- **L** `discordbot/crew_signup.py`/`watch_buttons.py` lack the catch-all the ack handlers have.

### Docs accuracy
- **H** ✓ (`CLAUDE.md` Role list — see §2).
- **M** "Sync All Users" feature undocumented in all 4 docs that claim to cover it.
- **M** `current-state.md` duplicates the env-var table and has drifted from code + `deployment.md` (3 vars disagree).
- **M** Doc-sync hooks are advisory-only and skip `middleware/`, `application/utils/`, `main.py`.
- **L** `data-model.md` shared-timestamp convention wrong for `ApiToken`/`EquipmentLoan`.
- **L** Directory/"100% coverage" maps omit `AGENTS.md`, `SECURITY.md`, `error_handlers.py`
  (note `AGENTS.md` carries a *competing* agent policy no indexed doc reconciles with `CLAUDE.md`).
- **I** `data-model.md` claims User "declares" reverse accessors that are only implicit.

---

## Methodology

This review was produced by a 10-dimension parallel agent workflow: one reviewer per
dimension (layering, structure, runtime scalability, growth scalability, NiceGUI/async,
API/security, data model, testing/CI, error/audit, docs-drift), each required to cite real
`file:line` evidence read from source. Each finding was then handed to an **adversarial
verifier** instructed to refute it. The verification pass was interrupted by a session limit
after 15 findings, so the report author (main session) **independently re-verified the
critical finding and every high-severity finding** against source — the ✓/≈ tags in §5
record verification provenance. MEDIUM/LOW/INFO findings carry the reviewers' cited evidence
but were not all individually re-verified; treat unmarked items as high-quality leads rather
than confirmed defects. The completeness-critic pass (dependency health, licensing, backup
story, upgrade paths) did not run before the limit and is the main gap in coverage — a
follow-up could cover it.
