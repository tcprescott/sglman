# Frontend Design Audit — July 2026 (round 2)

> **Status: P0 + P1 + most of P2 implemented and browser-verified (see [Implementation results](#implementation-results) at the end).** The findings below are the original audit; the roadmap items marked done have since been built, screenshot-verified in light + dark, and ship with the full suite green (2062 passed).

**Goal:** assess the web UI as a *product design system* — visual consistency, information architecture, component discipline, brand coverage, and the places where the phoenix design language stops applying. The [July mobile UX audit](2026-07-mobile-ux-audit.md) covered phones and shipped its P0–P2; this round is the desktop/system counterpart.

**Method:** the running app (dev boot + `scripts/seed_dev.py` fixtures) was driven with Playwright at 1500×1100 in **light and dark** (`colorScheme` emulation → the app's auto mode), as four personas (anonymous, `player_one`, `staff_user`, and `staff_user`-as-super-admin for `/platform`). All 7 home tabs, all 21 admin tabs, all 7 report pages, the volunteer hub, equipment detail, dialogs (admin match, feedback, request match), login, community picker, 403 and 404 were screenshotted full-page — 63 captures — and suspicious findings were re-verified live (scrolled dark-mode pages, drawer-click tab switching, direct DB queries).

---

## Executive summary

**The design system itself is genuinely good.** `static/css/styles.css` is a real token system — phoenix palette with mode-aware aliases, a warm dark-elevation ramp, semantic status colors, `.wiz-chip` pills, spacing/radius/shadow/motion scales, focus rings, reduced-motion support, and a self-hosted type trio (Fraunces display / Atkinson Hyperlegible body / IBM Plex Mono data). Where the system is applied — the match/user/equipment tables, Profile, Reports dashboard, Features, Qualifiers, the 404 page — the app looks deliberate and distinctive. Dark mode holds up across every re-verified page.

**The problem is adoption, not design.** The audit's findings cluster into five stories:

1. **Broken windows (functional):** the `selected_tab` refresh event that eleven admin tabs listen for is *never emitted* — and the Tournaments table has **no other initial load path, so it renders permanently empty**. The Users table shows **duplicate role chips and leaks cross-tenant role assignments**. A stray hook-test fixture committed as a real migration **broke every fresh dev boot** (removed on this branch).
2. **Off-brand surfaces at the edges:** `/platform`, the bare-host **community picker** (the platform's front door), and the admin permission-denied page have no phoenix styling at all — default Quasar blue/Roboto on white.
3. **Two table systems:** the four styled table families vs. ~10 newer admin tabs on default Quasar tables — different header treatment, alignment, link styling, and density on adjacent tabs.
4. **Micro-consistency drift:** three different renderings of a boolean, two empty-state styles, two section-heading styles, status text vs. status chips, icon-only actions, dialog action-row conventions.
5. **IA strain:** the admin drawer is a flat list of 21 tabs with duplicate icons; the flagship schedule table exceeds a 1500 px desktop and clips its last column.

Everything below has file references; the roadmap at the end is ordered by leverage.

---

## A. Broken windows — functional defects that read as design failures

| # | Finding | Evidence / location |
|---|---|---|
| A1 | **`selected_tab` is a dead event: nothing emits it.** `BaseLayout._handle_tab_change` (`theme/base.py:299`) syncs drawer/bottom-nav highlights and the URL but emits no event, yet **11 files** listen via `ui.on('selected_tab', ...)` (`admin_settings.py:54`, `admin_users.py:80`, `admin_schedule.py:221`, `admin_presets.py:166`, `admin_racetime.py:163`, `admin_speedgaming.py:214`, `admin_discord_events.py:188`, `admin_discord_roles.py:259`, `admin_webhooks.py:288`, `admin_qualifiers.py:493`, plus `wire_tab_refresh` in `theme/tables/admin_crud.py:65`). Repo-wide grep finds no emitter in any commit — the tab-switch refresh contract silently died in a layout refactor. | Verified live: drawer-clicking between tabs never fires the listeners. |
| A2 | **Admin → Tournaments renders permanently empty.** `TournamentTableView` builds with `rows=[]` and refreshes only via the dead A1 event, a manual toolbar click, or `update:pagination` (`theme/tables/tournament.py:27-33,106`; `admin_settings.py:47-54` does **no initial refresh**). Two active tournaments exist in the tenant (verified by direct DB query); the table shows "No data available" on deep link *and* on drawer click. Every other populated tab (Users, Presets, Vol. Roster…) does an initial load at build — Tournaments is the only core table without one. | Screenshots `staff-light--admin-tournaments`, `verify-click-tournaments`. |
| A3 | **Users table: duplicate role chips + cross-tenant leak.** `UserTableView.refresh()` prefetches `roles` unscoped and `_format_user_row` renders every `UserRole` row (`theme/tables/user.py:120-129`), so with two seeded tenants staff shows "Staff, Staff, Volunteer Coordinator, Volunteer Coordinator…" and `proctor_user` shows "Proctor, Proctor". Beyond looking broken, this **displays another tenant's role grants inside this tenant's admin** — the display counterpart of the scoping rule that `AuthService.get_roles` (tenant-filtered, `auth_service.py:50-59`) gets right. Same duplication on the mock-login picker. Chips also overflow the column with no wrap for role-heavy users. | Screenshot `staff-light--admin-users`. |
| A4 | **A stray hook-test fixture at `migrations/models/0_20240101000000_init.py`** (contents: `# unrelated tweak`, committed in 494cfb1) made aerich fail on **every fresh boot** (`AttributeError: module ... has no attribute 'upgrade'`). Removed on this branch — without it, no reviewer or fresh environment can even see the UI. | `git show 494cfb1`. |
| A5 | **Vol. Roster is invisible to review because the seed grants no `VOLUNTEER` role.** `assignable_volunteers` filters on `Role.VOLUNTEER` (`volunteer_profile_service.py:59-64`); `seed_dev.py` creates opt-ins, qualifications, and availability but no volunteer-role users, so the roster legitimately renders "No data available" — a seed-coverage gap under the project's own "a feature the seed never creates is a feature no one can see" rule. (Aside: that service queries `UserRole` without a tenant filter — same class of leak as A3.) | Screenshot `staff-light--admin-vol-roster`; `scripts/seed_dev.py:159-162`. |

**Recommendation:** re-emit `selected_tab` from `_handle_tab_change` (one line restores an app-wide contract), *and* give every table an initial load at build so correctness never depends on the event again — `ServiceTableView.build()` can end with `background_tasks.create(self.refresh())` and `TournamentTableView` can adopt the same pattern. Scope the Users roles display to the current tenant (with `TA(n)`/`CC(n)` unchanged). Seed one volunteer-role user.

## B. Off-brand surfaces — where the phoenix theme stops

| # | Finding | Evidence / location |
|---|---|---|
| B1 | **`/platform` has no brand at all.** No `BaseLayout` chrome (no header, no drawer, no way back), Quasar-blue `NEW TENANT` / `NEW BOT` / `REFRESH NOW` buttons, Roboto headings (`text-2xl font-bold`), default table styling, gray `Unknown` chips — visually a different product. It also leaks internals: raw enum strings ("**BotStatus.CONNECTED** — Connected (mock transport)", `pages/platform.py` health column) and a clipped "RES…" (Reset) action at the card edge. Super-admins are real users too; this is the surface where the platform operator lives. | Screenshot `staff-light--platform` (light + dark identical). |
| B2 | **The community picker is the platform's front door and it's bare.** The bare-host `/` renders an unstyled column: `text-3xl font-bold` title, `text-gray-600` subtitle, default blue links (`pages/home.py:20-38`). First-visit impression on the platform domain is "developer scaffold", one screen before the polished tenant home. A branded card list (tenant name, logo slot, description) is a small page. | Screenshot `anon-light--picker`. |
| B3 | **The admin permission-denied state is a bare red sentence** at the top-left of an empty page (`pages/admin.py:89`), while 404 gets the full branded treatment — error card, serif display status, cat fact, "Back to home" CTA (`theme/error_page.py`). Denial is a *more* common real-world event than 404 for logged-in non-admins; route it through the same `render_error_page` shape. | Screenshots `player-light--forbidden-admin` vs `anon-light--notfound`. |
| B4 | The mock-Discord login picker is default-styled (dev-only, production uses OAuth redirect — acceptable; noted for completeness). It inherits the A3 duplicate-roles display. | Screenshot `anon-light--login`. |

## C. Component consistency

| # | Finding | Evidence / location |
|---|---|---|
| C1 | **Two table systems.** The styled families (`.match-table`, `.user-table`, `.tournament-table`, `.equipment-table` — uppercase gold letterspaced headers on warm zebra, `styles.css:1079-1152`) cover four surfaces; the ~10 newer admin tabs (Presets, Racetime, SpeedGaming, Discord Events, Stream Rooms, Discord Roles, Webhooks, Feedback, Service Health, Vol. Roster) render **default Quasar tables** — mixed-case centered headers, no zebra, different row density — often on the *adjacent* drawer tab. Root cause: `ServiceTableView` defaults `table_classes='w-full'` (`theme/tables/admin_crud.py:109`) and hand-rolled `ui.table`s pass nothing. A shared `.wiz-table` class applied by default in `ServiceTableView` (and added to the hand-rolled tables) converges every admin tab in one pass. | Compare `staff-light--admin-users` with `staff-light--admin-presets` / `admin-stream-rooms` / `admin-speedgaming`. |
| C2 | **A boolean renders three ways on three adjacent tabs:** plain text `yes` (SpeedGaming "Active", Discord Events "Events synced"), green check-circle icon (Stream Rooms "Active"), and `No` text beside a name that *also* says "(inactive)" (Webhooks). Same on the platform tenant table (`yes`). Pick one (the icon or an `.wiz-chip`) and use it everywhere. | Screenshots `admin-speedgaming`, `admin-discord-events`, `admin-stream-rooms`, `admin-webhooks`. |
| C3 | **Status values skip the chip system.** SpeedGaming sync status renders lowercase `ok` as plain text while Service Health ("Healthy" / "Credential warning") and Equipment ("Available" / "Checked out") use proper chips. `.wiz-chip--ok` exists for exactly this. | `admin-speedgaming` vs `admin-service-health`. |
| C4 | **Two section-heading styles.** Profile and Challonge use the house gold-serif card headings ("Personal Information", "Linked tournaments"); Discord Events, Settings, and the reports use plain bold black sans ("Tournaments", "Mirrored events", "Tournament Hours"). The gold-serif treatment (`.section-title`) is the brand; the sans headings read as unstyled defaults. | `staff-light--home-profile` vs `admin-discord-events` / `admin-settings`. |
| C5 | **Icon-only actions dominate row UIs.** The crew signup columns render an unlabeled filled clipboard button per row ×2 columns (Commentators/Trackers) on every schedule row — the single most repeated element in the app, with no visible affordance for what it does; Webhooks rows carry 4 icon-only actions, Vol. Schedule shift cards 3, admin Equipment 5. Tooltips exist but are hover-only. At minimum, give the signup button a compact label ("Sign up"), and prefer text+icon for destructive/irreversible row actions. | `staff-light--home-schedule`, `admin-webhooks`, `admin-vol-schedule`. |
| C6 | **Two-and-a-half empty-state styles.** Quasar's stock "No data available" w/ warning triangle (Player, Tournaments, Vol. Roster) vs. the branded italic + cat-fact treatment (On Air, `theme/empty_state.py`) vs. bare header-only tables. The branded one is charming and already built — adopt it as *the* empty state, with a CTA where one exists ("Create Match", "Add Tournament"). | `staff-light--home-player` vs `staff-light--home-onair`. |
| C7 | **Intro descriptions are new-tab-only.** Presets, Qualifiers, Racetime, SpeedGaming, Discord Events, Webhooks, Features open with a one-paragraph gray explainer — genuinely helpful — while Users, Tournaments, Stream Rooms, Vol. Roster/Schedule, Feedback have none. Backfill the older tabs (one sentence each). | Screenshots throughout. |
| C8 | **Dialog action-row conventions drift.** The match dialog clusters Delete + Cancel + Save together at the left with dead space right (`dialog-admin-match`); the destructive-action convention elsewhere (Vol. Schedule's red "Reset all volunteer data", confirmation dialogs) separates destructive from primary. Within the same dialog the five "Clear …" lifecycle buttons mix red and gray outlines without a rule (Clear Check In/Started red, Clear Finish/Confirmed/Seed gray). | Screenshot `staff-light--dialog-admin-match`. |
| C9 | The Challonge tab renders **operator setup instructions to staff**: "Set CHALLONGE_CLIENT_ID and CHALLONGE_CLIENT_SECRET (or MOCK_CHALLONGE for local dev)…" (`admin_challonge.py:31-33`). Env-var names belong in deploy docs; the tab should say "not configured — contact your platform administrator" (and link the doc). | Screenshot `staff-light--admin-challonge`. |

## D. Layout & information architecture

| # | Finding | Evidence / location |
|---|---|---|
| D1 | **The admin drawer is a flat list of 21 tabs** (`pages/admin.py:111-150`) — it overflows a 1100 px viewport and scrolls, with no grouping. The labels already imply sections: *Operations* (Schedule, Stream Rooms, Users, Tournaments), *Online play* (Presets, Qualifiers, Racetime, SpeedGaming, Challonge), *Community* (Triforce Texts, Vol. Roster/Schedule, Equipment, Feedback), *Integrations* (Discord Events, Discord Roles, Webhooks), *System* (Reports, Service Health, Features, Settings). Quasar's drawer supports plain non-clickable section labels — no routing change needed, just grouped rendering in `_render_drawer`. | Every admin screenshot (drawer cut mid-list). |
| D2 | **Duplicate drawer icons defeat scanning:** `people` = Users *and* Vol. Roster *and* home Profile; `volunteer_activism` = the Volunteer top-item *and* Vol. Schedule; `schedule` = Schedule in two hubs. Icons are the primary visual anchor in a 21-item list — make them unique per destination. | `pages/admin.py:111-150`, `pages/home.py:71-85`. |
| D3 | **The flagship schedule table doesn't fit a 1500 px desktop.** With the Watch column (logged-in), the staff home schedule clips its last column behind horizontal scroll; the admin variant fits only because it drops Watch. The row spends width on low-value columns (Generated Seed is mostly `-`/blank; empty-value markers are inconsistent `-` vs blank). A column budget pass — e.g. fold Seed into the row detail/dialog, give Watch a fixed narrow slot — keeps the primary surface scroll-free. | Screenshot `staff-light--home-schedule` (header "WA…" clipped). |
| D4 | **System Configuration is the weakest-designed page:** underlined inputs stretched to ~1130 px for a 10-char date; "Volunteer Reminder Lead (minutes)" styled like a section heading while sibling fields get small labels; no card grouping (every other admin surface uses cards); date fields show a native picker icon *plus* a floating ✕ clear button mid-field; time fields double up native + Quasar clock icons. A two-column card layout with `max-width` on controls (the `.form-grid` class already exists, `styles.css:597`) transforms it. | Screenshots `staff-light--admin-settings`, `verify-dark-settings-scrolled`. |
| D5 | **Full-width label↔control gaps.** Profile's per-tournament notification selects sit ~900 px right of their labels — at that distance the eye loses the row. Cap the row width or move controls adjacent to labels. | Screenshot `staff-light--home-profile`. |
| D6 | The equipment detail page renders directly on the cream page background with no white content panel, unlike every tab page; its loan history is unstyled text lines. Minor, but it reads as a different layout system. | Screenshot `staff-light--equipment-detail`. |
| D7 | Feedback (and Users) reserve a full-height toolbar row for a lone refresh icon — an awkward empty band between title and table. Fold the refresh icon into the header row. | Screenshot `staff-light--admin-feedback`. |

## E. Content conventions

| # | Finding | Evidence / location |
|---|---|---|
| E1 | **UTC timestamps on Service Health** — `checked_at.strftime('%H:%M:%S UTC')` (`pages/service_health_view.py:47`, used by both the admin tab and `/platform`) violates the app-wide "display US/Eastern" rule (`docs/timezone-handling.md`) on the one page an on-call staffer reads under stress. | Screenshot `staff-light--admin-service-health`. |
| E2 | **Raw enum leakage** on `/platform` health ("BotStatus.CONNECTED", "BotStatus.ERROR") — see B1. | Screenshot `staff-light--platform`. |
| E3 | **Semantic color is underused on the reports dashboard KPIs:** stream-candidate coverage renders 0% in the same gold as healthy numbers (green only ≥80%, `reports/dashboard.py`); an ops dashboard should make "0/8 covered" look like the problem it is (red <50% or similar). | Screenshot `staff-light--admin-reports`. |
| E4 | Inconsistent empty-value markers *within one table*: Generated Seed shows `-` on some rows, blank on others; Users pronouns column mixes `-` and blank. Pick `—` and standardize. | `staff-light--home-schedule`, `admin-users`. |

## F. Dark mode & data-viz

| # | Finding | Evidence / location |
|---|---|---|
| F1 | **Dark mode is a strength — verified good.** The warm elevation ramp, gold headers, chips, tables, dialogs, drawer, and the settings form all hold up in live scrolled checks; no white-card regressions found (the "white band" in full-page captures is a screenshot artifact of the `fixed`-attachment gradient, not real). | `verify-dark-settings-scrolled`, all `staff-dark--*`. |
| F2 | **ECharts ignores the dark theme.** Axis labels, legend text, and gridlines keep default light-theme grays on the near-black surface (low contrast); series colors are fine. Pass a text/axis color set derived from the CSS tokens when building chart options (the chart builders in `reports/capacity.py` / `stream_rooms.py` / `insights.py` already centralize options). | Screenshot `staff-dark--report-capacity`. |
| F3 | Capacity's "Forecast data" table right-aligns the Time column under a centered header and renders an entirely empty Match IDs column for most ranges — minor alignment/columns polish alongside C1. | Screenshot `staff-light--report-capacity`. |

---

## Prioritized roadmap

**P0 — broken windows (small diffs, restore correctness):**
1. Emit `selected_tab` again from `_handle_tab_change` **and** add initial `refresh()` at build to `ServiceTableView` / `TournamentTableView` (A1, A2).
2. Tenant-scope the Users roles column; dedupe chips (A3). Audit `assignable_volunteers` for the same unscoped-`UserRole` pattern (A5 aside).
3. ~~Remove the stray `0_20240101000000_init.py` migration~~ — **done on this branch** (A4).
4. Seed a `VOLUNTEER`-role user so the roster surface is reviewable (A5).

**P1 — one design language everywhere (high leverage, mostly mechanical):**
5. Default `ServiceTableView` to the styled table family and add the class to hand-rolled admin tables (C1); standardize booleans → icon/chip, statuses → `.wiz-chip`, empty markers → `—` (C2, C3, E4).
6. Brand pass on `/platform` (BaseLayout chrome or at minimum palette + typography + humanized statuses + Eastern times) and the community picker; themed permission-denied page (B1–B3, E1, E2).
7. Adopt the branded empty state app-wide with CTAs (C6); normalize section headings to `.section-title` (C4).
8. Group the admin drawer into labeled sections; deduplicate icons (D1, D2).

**P2 — polish:**
9. Settings form redesign on `.form-grid` + cards; cap label↔control gaps on Profile (D4, D5).
10. Schedule-table column budget so the primary surface fits 1440–1500 px without scroll (D3).
11. Label the crew signup buttons; text+icon for destructive row actions (C5); dialog action-row convention (C8).
12. ECharts dark-theme text colors from tokens (F2); KPI semantic thresholds (E3); intro sentences for older admin tabs (C7); Challonge copy without env vars (C9); equipment-detail panel treatment (D6); toolbar band tidy (D7).

---

*Artifacts: 63 full-page screenshots (4 personas × light/dark) plus live-verification captures, generated via the `ui-validation` harness pattern; the sweep script drives `/t/default` plus platform-scoped targets and opens the admin match, feedback, and request-match dialogs. Verified facts in this report (empty tables, dead event, DB contents, dark-mode scroll) were each confirmed by a second method beyond the screenshot.*

---

## Implementation results

Everything in P0 and P1, and most of P2, shipped across a set of file-scoped commits; each surface was re-screenshotted in light **and** dark, `ruff` is clean, and the full pytest suite is green (**2062 passed**).

**P0 — broken windows (all fixed, browser-verified):**
- **`selected_tab` re-emitted** from `theme/base.py:_handle_tab_change`, so the eleven admin tabs that listen for it refresh on tab switch again. Verified by drawer-clicking Users → Tournaments and watching the table populate.
- **Every table loads at build.** `theme/tables/{tournament,user}.py` now do an initial `refresh()` through a tenant-rebinding `_bg` helper (mirroring `MatchTableView`) — the captured request context is re-bound with `tenant_scope`, since a bare `background_tasks.create` runs detached from the client slot and would raise `require_tenant_id()`. Admin → Tournaments now shows its rows.
- **Users roles column scoped + deduped** (`theme/tables/user.py`), plus the dev mock-login picker (`pages/auth.py`): `staff_user` now reads `Staff · Volunteer Coordinator · Equipment Manager · TA(2) · CC(1)` — no `Staff, Staff`, no leaked `SUPER_ADMIN`/other-tenant grants. `assignable_volunteers` tenant-scoped in the service (`volunteer_profile_service.py`).
- **Seed grants VOLUNTEER** to the opted-in/qualified users, so Vol. Roster and the auto-scheduler have a visible pool.
- The stray `0_20240101000000_init.py` migration was already removed on this branch.

**P1 — one design language:**
- **`.wiz-table`** opt-in added to the styled-table rule set and applied to every hand-rolled admin/report table; booleans render as check/cancel icons and sync/health statuses as `.wiz-chip`s (SpeedGaming, Discord Events, Webhooks, Racetime). Also fixed a latent slot-context bug the guardrail flagged (stream-room edit handler `ui.notify` in a background task).
- **`/platform`, the community picker, and the permission-denied page** are branded: phoenix chrome (stylesheet + palette + header/back-link), gold serif titles, styled tables, humanized bot health (`Connected`, never `BotStatus.CONNECTED`) as chips, and a themed 403 error card.
- **Branded table empty state** (`theme/empty_state.no_data_slot`) wired into the Match/User/Tournament views; in-tab section headings normalized to `.section-title`.
- **Admin drawer grouped** into Operations / Online play / Community / Integrations / System with unique per-destination icons (`pages/admin.py` + `theme/base.py`).

**P2 — polish (shipped):**
- Service Health shows **Eastern time** (was UTC); dashboard **coverage KPI is three-tier** (red <50% / amber / green ≥80%); **Challonge copy** no longer leaks env-var names; **form controls width-capped** (`.wiz-form-column`) on System Configuration + Profile; **equipment detail wrapped in a surface panel**; **Feedback toolbar folded** into the header row; **intro sentences** added to Users / Tournaments / Stream Rooms / Vol. Roster / Vol. Schedule / Feedback; **crew signup/withdraw buttons labeled** ("Sign up" / "Withdraw") on the schedule.

**Post-review hardening** (an architecture review of the branch caught a tenant-context regression in the refresh plumbing — confirmed live before fixing):
- The restored `selected_tab` emit re-activated ~11 page-level refresh handlers that run in bare background tasks spawned from a websocket event, which have lost both the tenant contextvar and the client stash. Two effects, both fixed: the **Users roles column re-leaked cross-tenant grants** on any non-initial refresh (filter/toolbar/tab-return) because `refresh()` re-resolved a now-`None` tenant instead of the one captured at build — now uses `self._tenant_id`; and **every tenant-scoped tab's tab-switch refresh raised a swallowed `require_tenant_id()`** — `wire_tab_refresh` now captures the tenant at page build and rebinds it with `tenant_scope`, adopted by the seven closure-based tabs, with Schedule/Tournaments/Users routed through the view's `_bg`.

**P2 — left as-is (with rationale):**
- **ECharts dark theme (F2):** already handled — `reports/shared.py` uses a documented mode-neutral axis/text color (`CHART_TEXT`/`CHART_GRID`) sitting at ~4:1 on both surfaces. Truly per-mode colors need the client's effective theme, which is unknowable server-side under auto mode; not worth the regression risk.
- **Dialog action row (C8):** the match dialog footer already separates destructive (Delete, left) from primary (Cancel/Save, right) via `ui.space()`.
- **Schedule column budget (D3):** Quasar tables scroll horizontally internally, so the Watch column is reachable, not hard-clipped; folding/removing columns risks the crew-signup and watch flows — deferred to a dedicated pass rather than reworked here.
