# Frontend / UI Architecture Reference

_Method-level reference for the presentation layer: [`frontend.py`](../../frontend.py), [`pages/`](../../pages/), [`theme/`](../../theme/), and [`static/`](../../static/). Part of the [documentation index](../README.md)._

The UI is built entirely with NiceGUI (Quasar/Vue under the hood) mounted into the FastAPI app. Pages call the service layer for all writes; see [services.md](services.md) for the service APIs and [../architecture.md](../architecture.md) for the three-layer pattern. Login and route protection are covered in [authentication.md](authentication.md).

## NiceGUI integration (`frontend.py`)

[`frontend.py`](../../frontend.py) wires NiceGUI into FastAPI.

**Middleware.** At import time three middlewares are registered on the NiceGUI `app`: `AuthMiddleware`, `TenantMiddleware`, `TransportPrefixMiddleware`. Starlette runs the last-added outermost, so execution is session → transport-strip → tenant → auth: transport paths (`/t/<slug>/_nicegui`, `/_nicegui_ws`, `/static`, `/sw.js`) are un-prefixed first so NiceGUI's assets and socket.io resolve, then the tenant is resolved and the ASGI path rewritten before `AuthMiddleware` reads it. `TransportPrefixMiddleware` is pure-ASGI, so it also covers the websocket scope that `BaseHTTPMiddleware` skips.

**`@app.on_exception _handle_unhandled_ui_exception`** — the backstop for event handlers that miss the `ValueError`→`ui.notify` wrap. Logs with traceback (so it reaches Sentry) and shows a generic negative notify. Never raises itself.

**`NoCacheStaticFiles`** — a `StaticFiles` subclass. When `ENVIRONMENT` is `development` (the default) it rewrites every HTTP response with `Cache-Control: no-cache, no-store, must-revalidate` so CSS edits show up without a hard refresh. In production it behaves like plain `StaticFiles`.

**`init(fastapi_app)`** — the single entry point, called from `main.py`:

1. `validate_security_config()` ([`application/utils/environment.py`](../../application/utils/environment.py)) — aborts startup if `STORAGE_SECRET` is empty, and in production also requires `DB_USERNAME` / `DB_PASSWORD`.
2. Mounts `/static` → `NoCacheStaticFiles(directory="static")`.
3. `_register_root_routes(fastapi_app)` — the two routes that cannot live under `/static`: **`/robots.txt`** (a blanket `Disallow: /` — signed-out surfaces are shareable by link, not published to search engines) and **`/sw.js`** (a worker served from `/static/` could only control `/static/*` clients, so root scope is required for PWA install).
4. Registers pages in source order: `auth.create()` (login/logout/OAuth, or the mock-Discord user picker — see [../features/discord.md](../features/discord.md)), `challonge_oauth.create()`, `twitch_oauth.create()`, `racetime_oauth.create()`, `mcp_consent.create()`, `register_link_handoff_pages()`, `admin.create()`, `home.create()`, `volunteer.create()`, `equipment_labels.create()`, `equipment.create()`, `brackets.create()`, `platform.create()`, `qualifiers.create()`. Two orderings are load-bearing: the link-handoff routes come after the OAuth providers so their handoff configs are registered, and the static `/equipment/qr-labels` route comes before the dynamic `/equipment/{asset_id}`.
5. `ui.run_with(fastapi_app, …)` with the stripped `STORAGE_SECRET`, `viewport='…viewport-fit=cover'` (so the header/footer bleed into the iOS safe-area insets when installed), the PWA favicon, and `session_middleware_kwargs={'https_only': is_production(), 'same_site': 'lax'}` — the signed auth cookie is `Secure` in production, plain in local development. No `mount_path`, so `@ui.page` routes live at the site root.
6. `register_error_handlers(fastapi_app)` ([`middleware/error_handlers.py`](../../middleware/error_handlers.py)) — installs the themed 40x/50x pages; see [Error pages](#error-pages-middlewareerror_handlerspy).

## Layout system (`theme/base.py`)

[`theme/base.py`](../../theme/base.py) defines **`BaseLayout`**, the shell used by every page.

Constructor: `BaseLayout(copyright_text=…, section=None, base_path=None, tabs=None, user=None, show_admin=False, show_volunteer=None, wordmark=None, **_kwargs)`.

- `tabs` is a list of dicts `{'label', 'icon', 'content'}`, optionally `'slug'` and `'group'`. `content` is either a callable (sync or async, detected via `inspect.iscoroutinefunction`) or a tuple `(callable, args, kwargs)` for parameterized tabs — the admin page uses the tuple form to pass `can_crud` and the report query params. A `'group'` turns the drawer's flat tab list into labeled sections.
- `section` is the URL **slug** of the initially active tab (e.g. `reports`); it resolves to a label via the auto-derived slug map (`tab_slug()`, or an explicit `'slug'`). An unknown or missing slug falls back to the first tab.
- `base_path` is the section URL base **including any `/t/<slug>` root_path** (e.g. `/t/foo/admin`); tab switches rewrite the URL to `{base_path}/{slug}`. `None` on tab-less pages, which never touch the URL.
- `show_admin=True` adds an "Admin" entry to the drawer's top menu (Home is always present).
- `show_volunteer` is **tri-state**. `None` — the default, and what every page but `/volunteer` uses — resolves it in `render()` via `AuthService.can_view_volunteer(user)`, so the link is never offered where the `VOLUNTEERS` flag or the role gate would reject it and dead-end on a 404/403. An explicit bool is honoured as-is, which keeps the synchronous error path working without a DB round-trip.
- `wordmark` is the header brand text; `None` resolves to the in-scope community's own name via `TenantService.current_community_name()`, falling back to `Wizzrobe`.
- Callers also pass `page_name=…`; `BaseLayout` absorbs it via `**_kwargs` and does not use it.

`async render()` resolves the wordmark and Volunteer visibility, `await`s `_load_theme_colors()` (the tenant's brand palette via `TenantThemeService.get_current_theme()`), calls the synchronous `render_chrome()`, then `await`s `_render_tab_panels()` if tabs were supplied.

**Why the split.** `render_chrome()` is separate so non-async callers — notably the `on_page_exception` 50x path, which NiceGUI invokes synchronously — can draw the full themed shell without awaiting. That path skips the async palette load and falls back to the shipped defaults.

| Step | Method | Behavior |
|---|---|---|
| Dark mode | `render_chrome()` | `app.storage.user['dark_mode']` into `ui.dark_mode()` (`None` ⇒ follow the client's system theme), font preloads, `styles.css`, the `noindex` meta, and the PWA manifest / theme-color metas / `/sw.js` registration |
| Palette | `render_chrome()` | `colors = self._theme_colors or DEFAULT_THEME` → `ui.colors(primary/secondary/accent=…)` (status colours stay fixed) plus an injected `<style>` re-pointing the `--wiz-*` brand vars. See [Per-tenant theme colours](#per-tenant-theme-colours) |
| Header | `_render_header()` | Burger, wordmark (the community name), `ui.space()` spacer, then either the user's name + Discord avatar (or an `account_circle` placeholder) + logout, or an icon-only-on-phones "Login with Discord" button; finally the dark-mode toggle |
| Drawer | `_render_drawer()` | `ui.left_drawer` at `breakpoint=1023 show-if-above bordered` (pinned ≥1024px, behind the burger below). Top menu (Home / Volunteer / Admin), one item per tab with a `.wiz-drawer-group` header per `'group'`, a **Feedback** item for logged-in users, and a GitHub link + copyright caption pinned to the foot via `ui.space()` |
| Footer | `_render_footer()` | **Only** the mobile app-shell bottom nav (`.wiz-bottom-nav`), and only when there are tabs: the first four tabs plus a **More** button opening the drawer. Hidden ≥1024px, so desktop and tab-less pages render no footer |
| Tabs | `_render_tab_panels()` | Panel *containers* are all created up front; each tab's **content is built on first show** — see below |

**Lazy tab rendering.** Every `ui.tab_panel` container exists from page load (so panel switching, deep-linked sections, and swipe all work), but a tab's content is built the first time it is shown, by `_build_tab`. Unbuilt tabs sit in `_pending_tabs`; a label leaves it exactly once. A deferred build gets a spinner, is wrapped in `tenant_scope(self._tenant_id)` — the tenant captured at page-build time, because the deferred build runs in a websocket handler where the contextvar is unset — and falls back to an inline error label if the content raises. This is why the home hub is cheap: eager rendering spent roughly half of the page's render CPU on panels nobody looked at.

**Tab deep-linking.** Sections are addressed by **path segment** (`/admin/reports`), not a query param. Tab switching does not reload: `_switch_tab(label)` moves the drawer's `active` prop and the tab-panels value, and `_handle_tab_change` replaces the URL with `{base_path}/{slug}` via `ui.navigate.history.replace` (`replace`, not `push`, so per-tab switches don't stack a Back-button trap). The reverse direction works because each hub is registered under both `/base` and `/base/{section}` (via `protected_tab_page`, or three `ui.page()` calls for the public home page): the page function declares a `section: str = None` parameter that NiceGUI maps the path param onto. The home hub lives at `/` with sections at `/home/<slug>`. Report filters (`report`, `start`, `end`, …) remain query params on top of the path.

### Per-tenant theme colours

The shipped "Phoenix" palette (gold/ember) is overridable per tenant on **Admin → Appearance**. Storage, validation, presets and the contrast checks belong to [`TenantThemeService`](services.md#tenant_theme_servicepy--tenantthemeservice); this section covers only how the palette is *applied*.

`render_chrome()` applies it in two places, because `ui.colors()` alone recolours Quasar's palette and never reaches the header bar, links, or section titles: `ui.colors(primary/secondary/accent=…)`, plus an injected `<style>` re-pointing `--wiz-gold-deep` / `--wiz-gold` / `--wiz-ember*` / `--wiz-header-bg` and the light-mode PWA `theme-color` meta. It is injected after `styles.css`, so it wins; the dark-mode `--wiz-header-bg` override in `styles.css` keeps the header charcoal in dark mode. Reads are fresh per page load, so a save shows on the next navigation (the Appearance form reloads the page).

`--wiz-*` is declared on `:root`; the bracket renderer's `--bracket-*` properties are declared on **`body`** instead, because `ui.colors()` writes the tenant `--q-primary` onto `body` — a `:root` declaration there would resolve `var(--q-primary)` against Quasar's stock blue.

Custom colours apply only inside a tenant: the platform surfaces (community picker at `/`, `/platform`) and the synchronous error page keep the shipped palette.

## Tenant-less chrome (`theme/chrome.py`)

Two surfaces run on the bare platform host with **no tenant in scope** and so cannot use `BaseLayout` — its drawer links into tenant routes and its palette is resolved from the in-scope tenant:

| Surface | Subtitle | Extra header content |
|---|---|---|
| `/platform` ([`pages/platform.py`](../../pages/platform.py)) | `Platform` | "Communities" link back to the picker at `/` |
| `/oauth/mcp/consent` ([`pages/mcp_consent.py`](../../pages/mcp_consent.py)) | `Authorize` | the signed-in user's name — the same identity the consent card names |

**`render_platform_chrome(subtitle=None, *, right=None)`** is the subset they share: font preloads, `styles.css`, the `noindex` meta, the shipped phoenix palette (never a tenant override — these surfaces belong to the platform, and an MCP grant is not scoped to one community), and the `wiz-header` bar with its ember→gold strip, the "Wizzrobe · *subtitle*" wordmark, an optional `right` callable, and the dark-mode toggle.

**`dark_mode_button(dark)`** is shared with `BaseLayout._render_header` so the toggle behaves identically everywhere: `brightness_auto` until the user picks a side, then a sticky `app.storage.user['dark_mode']`. The consent screen's card uses the `.consent-*` family, deliberately sharing the error page's proportions so the two chrome-light screens read as one family.

## Error pages (`middleware/error_handlers.py`)

Branded 40x/50x pages, all rendered through the standard `BaseLayout` chrome by **`render_error_page(...)`** in [`theme/error_page.py`](../../theme/error_page.py). The renderer is **synchronous** because NiceGUI invokes the `on_page_exception` hook without awaiting it; the only async work (loading the user to file a report) happens lazily in a button click handler.

NiceGUI is mounted as a sub-application by `ui.run_with` (`app.mount('/', core.app)`) and ships its own "sad face" 404/500 pages, so `register_error_handlers()` installs the overrides on the NiceGUI `app`, not the host FastAPI app:

| Status | Mechanism | Behavior |
|---|---|---|
| **404** | `@app.exception_handler(404)` override | Keeps NiceGUI's guard that returns JSON for non-page endpoints (the REST API and raised `HTTPException`s); renders a themed "Page not found" for real UI routes |
| **403** | `render_error_page(...)` call in [`middleware/auth.py`](../../middleware/auth.py) | The `@protected_page` denial path renders a themed "Forbidden" instead of a bare label |
| **500** | `app.on_page_exception` | NiceGUI calls this from `create_500_error_page` for exceptions raised inside `@ui.page` builders (where essentially all request handling runs) |

**Traceability.** Every unhandled 500 gets a `uuid4` `error_id` via `log_unhandled_error()`, which logs `UNHANDLED ERROR error_id=<uuid> path=<path>` with `exc_info` and tags `error_id` on the Sentry scope so logs and Sentry events correlate. The error page surfaces the UUID and, for logged-in users, a **"Report this error"** button that opens `FeedbackDialog` prefilled (category `BUG`, message containing `Error reference: <uuid>`).

**DEBUG vs production.** Outside production the 500 page also renders the full traceback; in production it shows only the UUID.

## Pages & routes

| Route | File | Auth |
|---|---|---|
| `/`, `/home/{section}` | [`pages/home.py`](../../pages/home.py) | Public; some tabs degrade to a login prompt. `/` = default section |
| `/admin`, `/admin/{section}` | [`pages/admin.py`](../../pages/admin.py) | Login required (`@protected_tab_page`); content gated by role |
| `/volunteer`, `/volunteer/{section}` | [`pages/volunteer.py`](../../pages/volunteer.py) | Login required (`@protected_tab_page`, roles Volunteer/Proctor/Staff, `VOLUNTEERS` flag) |
| `/equipment/qr-labels` | [`pages/equipment_labels.py`](../../pages/equipment_labels.py) | Staff / Equipment Manager (`EQUIPMENT` flag); printable QR-label sheet (`?ids=…&template=…&cols=…&paper=…&show=…`). `template` is `plain` (free grid, Letter/A4) or an Avery preset (`avery5160`/`5163`/`5162`) laid out on exact die-cut inches; `show` opts in owner/community/description lines. Registered **before** `/equipment/{asset_id}` so the static path wins |
| `/equipment/{asset_id}` | [`pages/equipment.py`](../../pages/equipment.py) | Login required (`@protected_page`, path-param route); asset detail / QR target |
| `/qualifiers`, `/qualifiers/{id}` | [`pages/qualifiers.py`](../../pages/qualifiers.py) | Login required (`ASYNC_QUALIFIERS` flag); player async-qualifier pages (draw, timer, submit, leaderboard) |
| `/tournament/{tournament_id}/brackets`, `/brackets/{bracket_id}` | [`pages/brackets.py`](../../pages/brackets.py) | **No login** — `@public_page(feature=FeatureFlag.BRACKETS)`; read-only bracket index + per-stage detail |
| `/platform` | [`pages/platform.py`](../../pages/platform.py) | Super-admin only, **no tenant context**; tenant + racetime-bot CRUD (see [multitenancy.md](../features/multitenancy.md)) |
| `/login`, `/logout`, `/oauth/callback` | [`pages/auth.py`](../../pages/auth.py) | See [authentication.md](authentication.md) |
| Identity-link OAuth callbacks | [`challonge_oauth.py`](../../pages/challonge_oauth.py), [`twitch_oauth.py`](../../pages/twitch_oauth.py), [`racetime_oauth.py`](../../pages/racetime_oauth.py) | Login required; one-time verified-identity linking on the global `User` |

Each page module exposes a `create()` function that registers its `@ui.page` route; `frontend.init()` calls them.

### Home (`/`, `pages/home.py`)

`home(section=None, request=None)` — on the bare platform host (no tenant) it renders the community picker instead; otherwise it stashes the tenant + host mode onto the connection (so websocket handlers resolve them), sets the page title, resolves the current user, and renders `BaseLayout`. If a `discord_id` is present but no matching active `User` exists, it shows an error, clears the session, and redirects to `/logout` after 2 seconds.

The flag set is resolved **before** the tab list is assembled rather than inside the signed-in branch, because Brackets is flag-gated but anonymous-readable.

| Tab | Content function | Shown when |
|---|---|---|
| Schedule | `home_tabs/schedule.py:schedule` | Always (crew signup, watch, and edit require login) |
| On Air | `home_tabs/stage_timeline.py:stage_timeline_tab` | Always |
| Brackets | `home_tabs/brackets.py:brackets_tab` | `BRACKETS` flag live (signed in or not); inserted third |
| Profile | `home_tabs/player_edit_info.py:render_edit_info_tab` | Always (renders a login card when signed out) |
| Player | `home_tabs/player.py:render_player_dashboard` | Always (renders a login card when signed out) |
| My Availability | `home_tabs/availability.py:availability_tab` | Logged in — deliberately ungated, since availability feeds crew signup too |
| Triforce Texts | `home_tabs/triforce_texts.py:triforce_texts_tab` | Logged in **and** `TRIFORCE_TEXTS` flag live |
| Equipment | `home_tabs/equipment.py:equipment_tab` | Logged in **and** `EQUIPMENT` flag live |

A leading "Home" tab backed by an `announcements_page` is present but commented out. `show_admin` is computed via `AuthService.can_view_admin(user)`; `show_volunteer` is left unset so `BaseLayout` resolves it.

## Home tabs (`pages/home_tabs/`)

| Module | Tab | Responsibility |
|---|---|---|
| [`schedule.py`](../../pages/home_tabs/schedule.py) | Schedule | Public event schedule with crew signup, watch toggles |
| [`stage_timeline.py`](../../pages/home_tabs/stage_timeline.py) | On Air | Per-day timeline of streamed matches grouped by stream room |
| [`brackets.py`](../../pages/home_tabs/brackets.py) | Brackets | Anonymous browse path into the public bracket pages: one card per tournament with stages. `group_by_tournament` is pure (unit-tested); the single read is `BracketService.list_all_brackets` |
| [`player_edit_info.py`](../../pages/home_tabs/player_edit_info.py) | Profile | Self-service profile, DM preference, tournament opt-in; hosts the device-notification, identity-link and API-token sections |
| [`player.py`](../../pages/home_tabs/player.py) | Player | The logged-in player's own match list and match requests; bracket matches to schedule |
| [`availability.py`](../../pages/home_tabs/availability.py) | My Availability | Self-service availability windows with a live effective-availability graph |
| [`triforce_texts.py`](../../pages/home_tabs/triforce_texts.py) | Triforce Texts | Pick a supporting tournament, then submit/track triforce-screen text |
| [`equipment.py`](../../pages/home_tabs/equipment.py) | Equipment | Browse the lending inventory and the user's own checkouts |

Several further modules render **inside** the Profile tab rather than as standalone tabs (all called from `player_edit_info.py`):

| Module | Renders | Responsibility |
|---|---|---|
| [`api_tokens_section.py`](../../pages/home_tabs/api_tokens_section.py) | "API tokens & AI clients" card | Create / list / revoke personal REST API tokens via `ApiTokenService`; the plaintext token is shown once at creation. Also lists connected MCP clients and carries the copyable **MCP server URL** callout — an MCP connection is started from the client, so the URL is all this page can usefully offer |
| [`_link_section.py`](../../pages/home_tabs/_link_section.py) | the three identity cards | The shared engine (`render_connected_accounts_section`) behind the Challonge / Twitch / racetime.gg rows |
| [`challonge_link_section.py`](../../pages/home_tabs/challonge_link_section.py) | "Challonge" card | Verify-link / unlink via `ChallongeService`; hides itself when the integration isn't configured |
| [`twitch_link_section.py`](../../pages/home_tabs/twitch_link_section.py) | "Twitch" card | Verify-link / unlink via `TwitchService`; hides itself when unconfigured |
| [`racetime_link_section.py`](../../pages/home_tabs/racetime_link_section.py) | "racetime.gg" card | Verify-link / unlink via `RacetimeService`; hides itself when unconfigured |
| [`web_push_section.py`](../../pages/home_tabs/web_push_section.py) | "Device Notifications" card | Enable/disable web push on the current device via `WebPushService`. The buttons run [`static/js/web-push.js`](../../static/js/web-push.js) client-side via `js_handler` (permission prompts must stay inside the click gesture) and report back through `emitEvent` → `ui.on`. Hides itself when VAPID keys aren't configured ([../features/web-push.md](../features/web-push.md)) |

[`pages/mcp_consent.py`](../../pages/mcp_consent.py) registers `/oauth/mcp/consent`, the OAuth approval screen for MCP clients. It is a bespoke `@ui.page`, **not** `@protected_page`: every protected page is a tenant page and 404s without a tenant, but an MCP grant is platform-wide. It adds itself to `protected_routes` directly to get the sign-in redirect, and styles through [`render_platform_chrome`](#tenant-less-chrome-themechromepy). See [features/mcp-server.md](../features/mcp-server.md).

### Schedule (`pages/home_tabs/schedule.py`)

The public event schedule with crew signup.

- Header "Schedule & Crew Signup" with a **Login with Discord** button when logged out. Per-tournament notification preferences are managed on the Profile tab — see [../features/discord.md](../features/discord.md#tournament-notification-preferences).
- A `MatchTableView` with `admin_controls=False`. Columns: ID, Tournament, Scheduled At, State, Players, Stage, Generated Seed, Commentators, Trackers — plus Watch when logged in.
- A match scheduled by a bracket shows a "<stage> · Game 2 of 3 · 1-0" link under the tournament name (`MatchDisplayService._bracket_ref`, rendered by `match_slots.py` / `match_grid.py`, handled by `_handle_open_bracket`). The series context comes off games the repository already prefetched, so it costs no extra query per row; the round *name* is deliberately absent, since naming a round needs the stage's whole graph. It emits `open_bracket` rather than carrying an `href`, so `ui.navigate.to` prepends the tenant `root_path`. Shared by every `MatchTableView`.
- `extra_slots` supply read-only state cells (per-state icon + timestamp) and a truncating seed-link cell.
- Clicking a match ID (logged-in only) opens `UserMatchDialog` and refreshes the table on submit.
- Services: `MatchService.get_all_matches_for_schedule()`; the logged-in `discord_id` is read from `app.storage.user` and passed into `UserMatchDialog`.

### On Air (`pages/home_tabs/stage_timeline.py`)

`stage_timeline_tab()` — a per-day timeline of streamed matches grouped by stream room.

- Header: previous/next-day arrows, a Today button, a date input with calendar popup and Go button, plus a floating refresh button (`.refresh-button`). All handlers dispatch through `background_tasks.create`.
- Data: `MatchService.get_matches_for_date(target_date, exclude_finished=True, require_stream_room=True)`, grouped via `MatchService.group_matches_by_stream_room(matches)`; rooms sorted by name. The current date is tracked in US/Eastern (see [../timezone-handling.md](../timezone-handling.md)).
- Each room renders a card (name, optional "Watch Stream" link, match count) and one `match-card` per match: Eastern time, status badge, tournament, players, approved commentators/trackers. Card borders are colour-coded by state (`.border-left-*`).
- Match IDs link to `/admin/schedule` when `AuthService.can_view_admin(user)`; otherwise they are plain labels.

### Profile (`pages/home_tabs/player_edit_info.py`)

`render_edit_info_tab()` — self-service profile editing.

- Installs a `beforeunload` JavaScript guard so unsaved edits prompt before navigation; every input's `on_change` calls `mark_dirty()` and a successful save calls `mark_clean()`.
- Fields: Display Name (placeholder shows the Discord username default), Pronouns, a "Receive Discord DM notifications" checkbox, and one checkbox per active tournament split into "Staff Administered Tournaments" and "Community Tournaments" (on `tournament.staff_administered`).
- Challonge-linked tournaments don't use the manual opt-in: their checkbox is disabled and reflects bracket membership from `ChallongeService.participant_tournament_ids`, and the row links out to `challonge_tournament_url`. An unlinked player sees a "Link Challonge account" call to action instead. These tournaments are excluded from `tournament_checkboxes`; any existing manual enrollment is carried through unchanged on save so the registration sync never drops it.
- **Save Changes** calls `UserService.update_user_personal_info` then `update_user_tournament_registrations`, with the user as their own audit actor.

### Player (`pages/home_tabs/player.py`)

`render_player_dashboard()` — "Your Schedule": the logged-in player's own matches.

- A `MatchTableView` (`admin_controls=False`, `player_discord_id` set). Columns: ID, Tournament, Scheduled At, State, Players, Stage, Generated Seed, Watch, using the same read-only state/seed `extra_slots` as the Schedule tab.
- A **Request Match** button opens `UserMatchDialog` in create mode.
- When Challonge is configured, an "Upcoming matches to schedule" card lists the player's unscheduled bracket matchups (`ChallongeService.list_unscheduled_matches_for_user`); each links an opponent and a **Schedule** button opening `ChallongeScheduleDialog` (disabled when the opponent hasn't linked their account).
- When `FeatureFlag.BRACKETS` is live, a matching card lists pending **native** bracket matchups (`BracketService.list_open_matches_for_user`) with opponent, round, and a **Schedule game N** button opening [`BracketScheduleDialog`](../../theme/dialog/bracket_schedule_dialog.py). In a bracket-run tournament this is the player's *only* scheduling route.

### Triforce Texts (`pages/home_tabs/triforce_texts.py`)

`triforce_texts_tab()` — inline tournament selection plus submission.

- A `@ui.refreshable` `content()` switches between an index (cards from `TriforceTextService.list_supporting_tournaments`) and a per-tournament submission view selected by an in-memory `state['tournament_id']`.
- The submission view gates on `tournament.is_active` + `SeedGenerationService.supports_triforce_texts` and on `AuthService.can_submit_triforce_text`; ineligible players see the tournament's `triforce_access_message` (rendered as plain text to avoid stored XSS) or a paid-option notice.
- Three `maxlength=19` line inputs feed `TriforceTextService.submit`; "Your Submissions" is a `@ui.refreshable` badged Pending/Approved/Rejected list from `list_user_submissions`.

### Equipment (`pages/home_tabs/equipment.py`)

`equipment_tab()` — inventory browsing and the user's own checkouts.

- Two inner Quasar tabs: **Inventory** (all assets via `EquipmentService.list_assets` + `open_loans_by_equipment_id`, status badge, current holder) and **My Checkouts** (`EquipmentService.my_checkouts`).
- Per-row action buttons gated by `AuthService.can_checkout_equipment` / `can_checkin_equipment` (going through `open_checkout` / `quick_checkin`, with `can_manage` from `can_manage_equipment`); a **View asset** button navigates to `/equipment/{id}`.
- Both tables use the `.equipment-table` family and switch to grid cards on small screens.

## Volunteer hub (`/volunteer`, `pages/volunteer.py`)

`volunteer_page(section=None, request=None)` is registered with `@protected_tab_page('/volunteer', roles=[Role.VOLUNTEER, Role.PROCTOR, Role.STAFF], feature=FeatureFlag.VOLUNTEERS)` — the whole hub 404s for a tenant without the `VOLUNTEERS` flag. It resolves the user, loads roles via `AuthService.get_roles`, and builds tabs by role before rendering `BaseLayout` (`show_volunteer=True`, `show_admin` via `AuthService.can_view_admin`).

| Tab | Shown to | Content function | Responsibility |
|---|---|---|---|
| My Availability | volunteer or staff | `volunteer_tabs/availability.py:availability_tab` | Volunteer availability windows, persisted via `VolunteerAvailabilityService.set_windows` |
| My Shifts | volunteer or staff | `volunteer_tabs/my_shifts.py:my_shifts_tab` | Upcoming assigned shifts, with acknowledgment |
| Proctor Station | proctor or staff | `volunteer_tabs/proctor_station.py:proctor_station_tab` | The on-site room board — check in, seat, roll the seed, start, record the winner. Always `can_crud=False` |

The two self-service tabs read the *signed-in* user's own data, so they are safe (and empty) for someone who volunteers for nothing; saving availability still requires a volunteer opt-in, which the service enforces.

`proctor_station_tab()` is a purpose-built board, **deliberately diverged** from the admin Schedule tab it used to render: same `MatchTableView` and the same lifecycle dialogs (both build their callbacks from `theme/tables/match_lifecycle.py:MatchLifecycleHandlers`, so the two cannot drift), but six columns instead of nine — Time, Next step, Players & stations, Seed, Tournament, `#` — with no Commentators/Trackers/Stage and no create/edit/confirm controls. It also passes three board-shaping options the admin table does not: `exclude_racetime=True` (a racetime.gg match has no on-site proctor), `row_sort=proctor_row_order` (overdue → checked in → started → scheduled → finished, earliest first within a bucket) and `actions_first=True` (the mobile card's lifecycle button sits under the player names). A `@ui.refreshable` chip strip above the table — driven by the view's `on_rows_changed` — counts to-check-in / to-start / in-play / overdue. The tab slug stays `proctor-station`, so existing deep links keep working.

`my_shifts_tab()` is a `@ui.refreshable` list of `VolunteerScheduleService.assignments_for_user(user, upcoming_after=now)`. Each card shows the position/label, the shift's Eastern start→end, and either an "Acknowledged" badge or an **Acknowledge** button calling `service.acknowledge(assignment_id, user)`.

## Admin dashboard (`/admin`, `pages/admin.py`)

`admin_dashboard_page(...)` is registered with `@protected_tab_page('/admin')` — login is enforced by the middleware, with no route-level role. The function resolves the user, loads roles via `AuthService.get_roles` (Stream Manager, Volunteer Coordinator, Equipment Manager, Preset Manager, Sync Admin, Qualifier Admin), checks Tournament-Admin / Crew-Coordinator / Qualifier-Admin membership **tenant-filtered** (those reverse relations hang off the global `User`, so unfiltered they would admit an admin of one community into every other), and loads the live flag set once for all tabs. A user matching none of them gets a themed 403 through `render_error_page`. Proctors are **not** admitted — their race/schedule workflow lives on `/volunteer`.

`is_staff` throughout is `AuthService.is_staff` (staff-*equivalence*), so a platform super-admin has full authority in any tenant.

Tab visibility — a user sees the union of every row they match. "(any)" means membership in at least one tenant-scoped tournament / qualifier:

| Tab | Group | Visible to | Flag |
|---|---|---|---|
| Schedule | Operations | Staff, Tournament Admin (any), Crew Coordinator (any) | — |
| Users | Operations | Staff | — |
| Tournaments | Operations | Staff, Tournament Admin (any) | — |
| Stream Rooms | Operations | Staff, Stream Manager | — |
| Presets | Online play | Staff, Preset Manager | — |
| Randomizer Keys | Online play | Staff, Preset Manager | — |
| Qualifiers | Online play | Staff, Qualifier Admin, qualifier admin (any) | `ASYNC_QUALIFIERS` |
| Racetime | Online play | Staff, Sync Admin | `RACETIME_ROOMS` |
| SpeedGaming | Online play | Staff, Sync Admin | `SPEEDGAMING_ETL` |
| Challonge | Online play | Staff | `CHALLONGE` |
| Brackets | Online play | Staff | `BRACKETS` |
| Triforce Texts | Community | Staff, Tournament Admin (any) | `TRIFORCE_TEXTS` |
| Vol. Roster | Community | Staff, Volunteer Coordinator | `VOLUNTEERS` |
| Vol. Schedule | Community | Staff, Volunteer Coordinator | `VOLUNTEERS` |
| Equipment | Community | Staff, Equipment Manager | `EQUIPMENT` |
| Feedback | Community | Staff | — |
| Discord Events | Integrations | Staff, Sync Admin | — |
| Discord Roles | Integrations | Staff | — |
| Webhooks | Integrations | Staff | — |
| Reports | System | Staff, Tournament Admin (any), Crew Coordinator (any) | — |
| Service Health | System | Staff | — |
| Features | System | Staff | — |
| Settings | System | Staff (System Configuration) | — |
| Appearance | System | Staff | — |

Tabs are appended in role order, then **stable-sorted by `_ADMIN_GROUP_ORDER`** (Operations → Online play → Community → Integrations → System), which the drawer renders as labeled sections.

`can_crud = staff or tournament-admin-of-any` is passed into the Schedule tab; crew coordinators get a read-mostly Schedule — lifecycle buttons but no create/edit/stage-assign (see [Admin schedule](#admin-schedule-pagesadmin_tabsadmin_schedulepy)). Proctors do **not** reach this tab at all: they get their own [Proctor Station](#volunteer-hub-volunteer-pagesvolunteerpy) board on `/volunteer`, which shares the lifecycle handlers but not the frame.

**Deep-link query params.** Besides the `section` path segment, the page accepts `report`, `start`, `end`, `bucket`, `tournament_id`, `user_id`, `stream_room_id`, `state`, `approval`, `action`, `focus`, `category`, and `page`, all forwarded as a kwargs dict into the Reports tab. Every report filter change navigates to a new `/admin/reports?report=...` URL, so report state is fully URL-driven and shareable.

Triforce texts has no standalone route: player submission lives in the home **Triforce Texts** tab and admin moderation in the admin **Triforce Texts** tab — behavior doc: [../features/triforce-texts.md](../features/triforce-texts.md).

## Admin tabs (`pages/admin_tabs/`)

| Module | Tab(s) | Responsibility |
|---|---|---|
| [`admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py) | Schedule | Match CRUD and the full lifecycle (seed / seat / start / finish / confirm) |
| [`admin_users.py`](../../pages/admin_tabs/admin_users.py) | Users | User management with role filtering |
| [`admin_settings.py`](../../pages/admin_tabs/admin_settings.py) | Tournaments, Stream Rooms | Tournament CRUD; stream room CRUD |
| [`triforce_texts.py`](../../pages/admin_tabs/triforce_texts.py) | Triforce Texts | Moderation queue for triforce-text submissions |
| [`admin_volunteer_roster.py`](../../pages/admin_tabs/admin_volunteer_roster.py) | Vol. Roster | Coordinator volunteer roster |
| [`admin_volunteers.py`](../../pages/admin_tabs/admin_volunteers.py) | Vol. Schedule | Coordinator shift grid: positions, shifts, assignment & auto-scheduling |
| [`reports/`](../../pages/admin_tabs/reports/__init__.py) | Reports | Read-only analytics — see [Reports subsystem](#reports-subsystem-pagesadmin_tabsreports) |
| [`admin_presets.py`](../../pages/admin_tabs/admin_presets.py) | Presets | Seed-rolling preset CRUD (`PRESET_MANAGER`/STAFF) + import of built-in `presets/` files — see [seed-generation.md](seed-generation.md#presets-db-backed) |
| [`admin_randomizer_keys.py`](../../pages/admin_tabs/admin_randomizer_keys.py) | Randomizer Keys | This community's own randomizer API credentials (`PRESET_MANAGER`/STAFF). One card per declared credential with a **write-only** password input — the stored value is never rendered back, and a blank submit is rejected (clearing is an explicit button). Cards, not a `ui.table`, so the per-credential help text fits — see [seed-generation.md](seed-generation.md#per-tenant-credentials) |
| [`admin_racetime.py`](../../pages/admin_tabs/admin_racetime.py) | Racetime | Reusable race-room profile CRUD (`SYNC_ADMIN`/STAFF) via `RaceRoomProfileService`; the bots themselves are platform-managed on `/platform` |
| [`admin_speedgaming.py`](../../pages/admin_tabs/admin_speedgaming.py) | SpeedGaming | SG→app schedule ETL: event-link CRUD + "Sync now" (`SYNC_ADMIN`) — see [online-tournaments.md](../features/online-tournaments.md) |
| [`admin_discord_events.py`](../../pages/admin_tabs/admin_discord_events.py) | Discord Events | Per-tournament Discord Scheduled Events opt-in + "Sync now" (`SYNC_ADMIN`) |
| [`admin_qualifiers.py`](../../pages/admin_tabs/admin_qualifiers.py) | Qualifiers | Async-qualifier authoring (pools/permalinks), the reviewer queue, and a Live Races sub-tab (`QUALIFIER_ADMIN`) — see [online-tournaments.md](../features/online-tournaments.md#async-qualifiers) |
| [`admin_service_health.py`](../../pages/admin_tabs/admin_service_health.py) | Service Health | Read-only subset of the platform health board for the tenant's own services (STAFF) |
| [`admin_features.py`](../../pages/admin_tabs/admin_features.py) | Features | Per-tenant feature-flag enable/disable (STAFF) — see [feature-flags.md](../features/feature-flags.md) |
| [`admin_theme.py`](../../pages/admin_tabs/admin_theme.py) | Appearance | Per-tenant brand colours (STAFF); see [per-tenant theme](#per-tenant-theme-colours) |
| [`admin_challonge.py`](../../pages/admin_tabs/admin_challonge.py) | Challonge | Manage the shared Challonge connection and per-tournament bracket sync |
| [`admin_brackets/`](../../pages/admin_tabs/admin_brackets/) | Brackets | Native bracket authoring, roster/seeding, start, results/overrides, complete & advance (STAFF, `BRACKETS` flag) — see [Admin brackets](#admin-brackets-pagesadmin_tabsadmin_bracketspy) |
| [`admin_discord_roles.py`](../../pages/admin_tabs/admin_discord_roles.py) | Discord Roles | Map Discord roles to application roles for sign-in role sync |
| [`admin_webhooks.py`](../../pages/admin_tabs/admin_webhooks.py) | Webhooks | Staff-managed outbound webhooks: add/edit (URL, event multiselect, active), regenerate secret, recent deliveries, delete — see [../features/webhooks.md](../features/webhooks.md) |
| [`admin_equipment.py`](../../pages/admin_tabs/admin_equipment.py) | Equipment | Asset CRUD, checkout/checkin, and QR-page links |
| [`admin_feedback.py`](../../pages/admin_tabs/admin_feedback.py) | Feedback | Review queue for user-submitted feedback |
| [`admin_system_config.py`](../../pages/admin_tabs/admin_system_config.py) | Settings | System configuration: event window, concurrency limits, tournament hours, Discord sync guild |

### Admin schedule (`pages/admin_tabs/admin_schedule.py`)

`admin_schedule_page(can_crud: bool = True)` — the operational heart of the app: a `MatchTableView` over `Match.all()` with `admin_controls=True`. Columns: ID, Tournament, Scheduled At, State, Players, Commentators, Trackers, Stage, Seed. The lifecycle handlers themselves live in `theme/tables/match_lifecycle.py:MatchLifecycleHandlers` (shared with the volunteer Proctor Station board, so the two surfaces cannot diverge on lifecycle behaviour); the page keeps only `submit_admin_match`, since creating a match is a scheduling action rather than a lifecycle one. Every handler calls `MatchScheduleService` with the current user as `actor`, catches `PermissionError` (negative notify) and `ValueError` (warning notify) through `notify_error`, and refreshes just the affected row via `table_view.update_row_by_id`. Construction is two-phase — `MatchLifecycleHandlers(page_container, can_crud=...)`, then `MatchTableView(..., **handlers.callbacks())`, then `handlers.table_view = table_view` — because the view needs the callbacks and the callbacks need the view. `callbacks()` *omits* `on_edit` / `on_confirm` / `on_edit_stream_room` when `can_crud` is false rather than passing `None`, since `MatchTableView` keys its slot registration off callback presence.

| Action | Trigger | Dialog | Service call |
|---|---|---|---|
| Create match | "Create Match" button (`can_crud` only) | `AdminMatchDialog` | `MatchService.create_match` (via dialog) |
| Edit match | Match-ID link (`can_crud` only) | `AdminMatchDialog` | `MatchService.update_match` (via dialog) |
| Generate seed | "Generate" button in Seed column | — | `MatchScheduleService.generate_seed` |
| Check In (seat) | "Check In" button in State column | `StationAssignmentDialog`, then confirm | `MatchScheduleService.seat_match` |
| Start | "Start" button | `ConfirmationDialog` | `MatchScheduleService.start_match` |
| Finish | "Finish" button | `MatchResultDialog` | `MatchScheduleService.finish_match` |
| Confirm | "Confirm" button | `ConfirmationDialog` | `MatchScheduleService.confirm_match` |
| Assign stage | "Assign" button in Stage column (`can_crud` only) | `StreamRoomDialog` | `MatchService.assign_stage` (via dialog) |
| Assign stations | Button next to players | `StationAssignmentDialog` | `MatchService.assign_stations` (via dialog) |

On-site-only controls are hidden for racetime.gg tournaments (`Tournament.is_racetime_enabled`): the display row carries an `is_racetime` flag, and the slot templates replace **Check In** with a muted "racetime.gg" note and drop **Assign stations** — the race room drives the lifecycle. The services enforce the same rule (`seat_match` / `assign_stations` raise `ValueError`), so the guard holds for API callers too.

Seed generation suppresses the notification when the service reports a generation "already in progress" (the row refresh clears the button spinner either way) and downgrades "already been generated" to a warning. The tab registers a `ui.on('selected_tab', …)` listener that refreshes on `'Schedule'`.

### Admin users (`pages/admin_tabs/admin_users.py`)

`admin_users_page()` — user management.

- A `UserTableView` with the toolbar suppressed (`show_toolbar=False`); the page renders its own row with **Add User** (opens `AdminUserDialog`) and a refresh button.
- Columns: Username, Display Name, Pronouns, Challonge (linked account, `-` when unlinked), Roles.
- A filter card with a multi-select over the `Role` enum (see [authentication.md § Roles](authentication.md#roles)) plus two pseudo-filters, `_tournament_admin` and `_crew_coordinator`. `get_query()` composes the queryset: roles via `roles__role__in`, the pseudo-filters via `admin_tournaments__isnull=False` / `crew_coordinated_tournaments__isnull=False`, finished with `.distinct()`.
- Username clicks open `AdminUserDialog` for that user (wired inside `UserTableView`).

### Admin settings (`pages/admin_tabs/admin_settings.py`)

Two tab functions live in this module.

**`admin_tournaments_page()`** — `TournamentTableView` over `Tournament.all()`. Columns: Name, Description, Seed Generator, Active, Players/Match, Avg Match Duration, Max Match Duration, Staff Administered, Player Count (the ID column is hidden). **Add Tournament** renders only when `AuthService.is_staff(actor)` and opens `TournamentDialog`; name clicks edit, player-count clicks open `TournamentPlayersDialog`. Listens for `selected_tab == 'Tournaments'` to refresh.

**`admin_stream_rooms_page()`** — a hand-rolled `ui.table` (not a shared table view). Rows from `StreamRoomRepository.get_all()`: ID, Name, Stream URL (as a link), Active (icon). **Add Stream Room** renders only when `AuthService.can_manage_stream_rooms(actor)`; ID links and the mobile-card edit button emit an `edit` event opening `StreamRoomEditDialog`. Mobile grid mode via `:grid="Quasar.Screen.lt.md"` with a custom `item` card slot.

### Admin triforce texts (`pages/admin_tabs/triforce_texts.py`)

`admin_triforce_texts_page()` — moderation queue for triforce-text submissions.

- Staff see all active tournaments; non-staff see only active tournaments they administer (`Tournament.filter(is_active=True, admins__id=actor.id)`); users administering none get an explanatory message instead of the queue.
- Filters: tournament select and status select (Pending / Approved / Rejected / All; default Pending).
- Each submission card shows the monospace text, the author, a status badge, **Approve** / **Reject** buttons (disabled when already in that state), and a delete button guarded by `ConfirmationDialog`. The list is a `@ui.refreshable` section re-rendered after every action.
- Services: `TriforceTextService.list_for_moderation`, `.moderate(text_id, approved, actor)`, `.delete(text_id, actor)`.

### Admin volunteer roster (`pages/admin_tabs/admin_volunteer_roster.py`)

`admin_volunteer_roster_page()` — the "Vol. Roster" tab (refuses unless `AuthService.can_manage_volunteers(actor)`).

- A `ui.table` (grid-card mode on small screens) of the assignable pool (`VolunteerProfileService.assignable_volunteers`): Name, Opted In, Qualifications (position-name chips from `VolunteerQualificationService.list_all_qualifications`), declared Availability windows (Eastern, from `VolunteerAvailabilityService.availability_map`), and a per-row manage button.
- The manage button emits `manage_volunteer`, opening `VolunteerProfileDialog` (active positions from `VolunteerPositionService.list_active`) to view availability and edit qualifications; the table reloads on submit and via a refresh button.
- An **Export data** button opens `VolunteerExportDialog`; the same button sits on the Vol. Schedule tab, since the coordinator may start from either.

### Admin volunteers (`pages/admin_tabs/admin_volunteers.py`)

`admin_volunteers_page()` — the "Vol. Schedule" tab, the coordinator scheduling grid (refuses unless `AuthService.can_manage_volunteers(actor)`).

- A controls card: an event-day select, **Auto-fill from availability** (`VolunteerAutoscheduleService.generate_draft`), **Clear draft**, **Manage positions** (an inline dialog wiring `VolunteerPositionDialog`), and a guarded **Reset all volunteer data** dialog (type-to-confirm → `VolunteerScheduleService.reset_all_shifts`).
- A `@ui.refreshable` `grid()` renders one card per active position, each with **Generate standard shifts** and **Add shift** (→ `VolunteerShiftDialog`) and a shift card per shift (filled/needed badge, edit/delete, and an **Assign** picker dialog).
- The assign picker pulls the opted-in pool and per-volunteer availability badges (`VolunteerAvailabilityService.availability_map` / `covers`); assigning goes through `VolunteerScheduleService.assign` (surfacing returned warnings); assignment chips remove via `unassign`.

### Volunteer data export (`theme/dialog/volunteer_export_dialog.py`)

`VolunteerExportDialog` — a start/end date pair (defaulting to `SystemConfigService.get_event_window()`, end inclusive) drives `VolunteerExportService.build`, and `bundle_to_zip_bytes` renders the bundle as `README.txt` plus one CSV per sheet (`volunteers`, `availability`, `positions`, `shifts`, `assignments`, `schedule`), downloaded as one ZIP via `ui.download`. The point is to hand the coordinator every input needed to draft a schedule in a spreadsheet — including each volunteer's opt-in note and the *open* slots, which the normalized assignment table cannot show. `ValueError`/`PermissionError` surface through `notify_error`.

### Admin Challonge (`pages/admin_tabs/admin_challonge.py`)

`admin_challonge_page()` — manages the shared Challonge service-account connection.

- A `@ui.refreshable` connection card from `ChallongeService.get_connection_status` (configured/connected state, username, scopes, token expiry, monthly request quota) with **Connect** (→ `/challonge/connect`) / **Disconnect** for staff.
- A `@ui.refreshable` "Linked tournaments" list (`Tournament.filter(challonge_tournament_id__isnull=False)`) with last-synced timestamps and a per-tournament **Sync** button (`ChallongeService.sync_bracket(..., force=True)`).

### Admin brackets (`pages/admin_tabs/admin_brackets/`)

`admin_brackets_page()` — the staff surface over `BracketService`, a package: `page.py` (selector, table, row dispatch), `stage_form.py` (create/edit/delete), `manage.py`, `results.py` and `shared.py`. A tournament selector drives a `ui.table` of that tournament's stages (Stage, Name, Format, State) with a `body-cell-actions` slot + `enable_mobile_grid`. Because row-action handlers fire from detached client events that have lost the tenant contextvar, every scoped call is wrapped in `tenant_scope(tenant_id)` captured while the request context was live, and `context.client` is captured and re-entered for each dialog. All dialogs use the house chrome (`form_dialog` + `dialog_actions`) so their actions stay reachable on a phone. `wire_tab_refresh('Brackets', …)` refreshes the table on tab entry; handlers catch service `ValueError`/`PermissionError` and surface them via `notify_error`.

The selector lists only tournaments with no Challonge link (a native bracket cannot coexist with one, so the rest could only ever answer "Create bracket" with an error), sorts inactive ones last with an `(inactive)` suffix, and auto-selects when there is exactly one.

Each row shows **one primary button — the step that stage is actually up to** — plus its readiness under the state badge ("2 enrolled", "7/15 matches reported", "Won by Alice", "Abandoned"), with every other legal action in an overflow menu. Each entry is `v-if`-gated on the row's own state, so the table never offers a transition the service would refuse; `can_advance` checks every guard the advance itself enforces (a successor that exists, is DRAFT, is unseeded and carries a rule). A `Setup` column renders `config_summary`, so a stage's rules are readable without opening anything. The selected tournament is remembered in `app.storage.user`.

| Row action | Shown when | Dialog | Service calls |
|---|---|---|---|
| **Create stage** | always (toolbar) | name, format, stage order (defaulting to `max + 1`, with the 1-based label it will be shown under) + an options panel **bound to the format select**: default best-of everywhere; Swiss rounds on Swiss; groups on round robin; grand-final reset on double elim; scoring + tiebreaker order on the two points-ranked formats; and an advancement block only when `stage_order > 0` | `create_bracket` |
| **Edit stage** | DRAFT | the same form, prefilled — including the **format**, which a DRAFT stage can still change because it has no match graph. Config keys the form does not own (round chrome) are carried through untouched | `update_bracket` |
| **Cancel stage** | ACTIVE | `ConfirmationDialog` naming what survives (the played results) and what does not (any ranking, any champion, any advance out of it) | `cancel_stage` |
| **Delete stage** | DRAFT / CANCELLED | `ConfirmationDialog` | `delete_bracket` |
| **Entrants & seeding** (`tune`) | DRAFT / ACTIVE | roster / enroll / seed / start, the per-round best-of + scheduled-time editor, and — while DRAFT — the **draw preview**: the real bracket rendered from `preview_draw`, plus a seeding toolbar (Number 1..N, Reverse, Shuffle, Clear, From qualifier). **Import roster** creates a linked entrant per enrolled player; a per-entrant `link`/`link_off` button picks the user by preferred name (never a raw id); the roster filters and hides retired entrants; an entry can be un-enrolled while DRAFT and retired once running; **Start** confirms, naming the publish, the DM count and any unlinked entrants | `preview_draw`, `import_entrants_from_roster`, `add_entrant`, `set_entrant_user`, `enroll`, `unenroll`, `retire_entry`, `drop_entrant`, `set_seeds`, `set_round_metadata`, `start_bracket` |
| **Results** (`scoreboard`) | ACTIVE / COMPLETE / CANCELLED | the embedded bracket for elimination formats, **standings** for the points-ranked ones (with the advancement cut line, a tie warning and per-entry rank inputs feeding `tie_breaks`), and match lists where **every** row opens the shared `build_match_dialog` — which is what finally gives Swiss and round robin score and forfeit entry | `standings`, `complete_stage(tie_breaks)`, `report_result`, `override_result` |
| **Complete stage** (`flag`) | ACTIVE, non-elimination | quick confirm; the tie-resolving path is in Results next to the standings it rules on | `complete_stage` |
| **Advance into next stage** (`fast_forward`) | COMPLETE, successor DRAFT + unseeded + carrying a rule | `advancement_plan` renders `Seed N — Name (was #rank, Group G)` under both stage names; an already-seeded chain is shown as information rather than discovered as an error | `advancement_plan`, then `advance_stage` |
| **Open public bracket** | not DRAFT | — | navigates to `/brackets/{id}` |

Dialog chrome detail: [brackets.md → Admin dialogs](../features/brackets.md#admin-dialogs).

### Public bracket view (`pages/brackets.py`)

Two read-only `@public_page(..., feature=FeatureFlag.BRACKETS)` routes rendering through `BaseLayout` and `BracketService` (with a load-or-404 `Tournament` lookup). **Public here means anonymous** — a bracket is the spectator-facing artefact of a tournament, so neither route joins `protected_routes` and a link to one works signed out (see [`public_page`](authentication.md#public_page)). The feature and tenant gates still apply, and every staff affordance sits behind `is_staff`, which is `False` for an anonymous visitor. The browse path in is the home **Brackets** tab.

- **`/tournament/{tournament_id}/brackets`** (`bracket_index`) — a card per stage with a **View** button into the detail route.
- **`/brackets/{bracket_id}`** (`bracket_detail`) — a `@ui.refreshable` body that renders **by format** through the shared [`theme/brackets/`](#bracket-renderer-themebrackets) renderer, with a match-detail dialog on click (staff get inline report/override) and live refresh from the event bus.

DRAFT visibility (staff-only, via `theme/brackets/visibility.py`), the mobile List/Bracket toggle, the derived live-status pills, and the standings/crosstable presentation are all covered in [brackets.md](../features/brackets.md#presentation--the-redesigned-bracket-view).

#### Bracket renderer (`theme/brackets/`)

One in-house renderer, consumed by both the public page and the admin Results dialog.

| Module | Role |
|---|---|
| `layout.py` | Pure, ORM-free layout walker: winner-link tree → absolute pixel placements + elbow connectors, robust to byes and the double-elim losers bracket. Unit-tested in [`tests/theme/`](../../tests/theme/) |
| `cards.py` | Absolute-positioned match cards + sticky round headers |
| `tables.py` | Swiss/group data tables (standings with tiebreaker columns + advancement tint, pairings, crosstable) as **NiceGUI elements, never `ui.html`** — entrant names are user-controlled |
| `visibility.py` | The pure staff-only-DRAFT rule, shared by the public pages and the browse tab |
| `labels.py` | Format/state chrome shared by those surfaces and the admin format select |
| `render.py` | Whole-bracket helpers (`render_elimination`, mobile accordion, `build_context`, `detect_finals`) |
| `dialog.py` | The shared match report/override dialog |
| `live.py` | Bridges `BRACKET_*` and `MATCH_*` bus events to a refresh |

All colour/size routes through `--bracket-*` custom properties in [`static/css/brackets.css`](../../static/css/brackets.css), linked per page via `add_head_html`.

### Admin Discord roles (`pages/admin_tabs/admin_discord_roles.py`)

`admin_discord_roles_page()` — Discord-role → app-role mappings for sign-in role sync.

- Requires the tenant to have a connected Discord server (`Tenant.discord_guild_id`); otherwise the tab offers the "Connect Discord server" flow instead of the mapping table.
- A hand-rolled `ui.table` of mappings (`DiscordRoleMappingService.list_mappings`), each with a delete button (`remove_mapping`). **Add Mapping** (gated on `AuthService.can_grant_roles`) opens a dialog whose Discord-role select is populated from `DiscordService.list_guild_roles`, persisting via `add_mapping`.
- Refreshes on tab entry via `wire_tab_refresh('Discord Roles', …)`.

### Admin equipment (`pages/admin_tabs/admin_equipment.py`)

`admin_equipment_page()` — full asset management.

- A `@ui.refreshable` `ui.table` of all assets (`EquipmentService.list_assets` + `open_loans_by_equipment_id`): #, Name, Owner, Status badge, current holder, with grid-card mode on small screens.
- Per-row buttons: **Check out** / **Check in** (`open_checkout` with `can_manage=True` / `quick_checkin`), **Open asset page**, **Edit** (`EquipmentDialog`), **Delete** (guarded by `ConfirmationDialog` → `EquipmentService.delete_asset`). **Add Asset** opens `EquipmentDialog` in create mode.
- **Print QR labels** opens `QrLabelDialog` — a checklist of assets (all pre-selected), quick-select filters, a template picker (plain grid with Letter/A4 + column count, or an Avery peel-off preset), and "Also show" toggles. It opens [`/equipment/qr-labels`](../../pages/equipment_labels.py) in a new tab (a bare path, so `ui.navigate.to` re-adds the tenant `root_path`) with the chosen `ids`/`template`/`show`. The single-asset page also has a manager-only **Print label** button for one asset.

### Admin feedback (`pages/admin_tabs/admin_feedback.py`)

`admin_feedback_page()` — a `@ui.refreshable` `ui.table` of recent submissions (`FeedbackService.list_recent`): submitted time, user, category, message, page URL, status badge. A **Mark reviewed** button per pending row calls `FeedbackService.mark_reviewed(actor, id)`.

### Admin system configuration (`pages/admin_tabs/admin_system_config.py`)

`admin_system_config_page()` — the "Settings" tab (`AuthService.is_staff` gates the Save button).

- Reads/writes `SystemConfigService` keyed constants: event start/end dates, max concurrent players, max concurrent stages, volunteer reminder lead minutes, per-day tournament hours, and the Discord sync guild id.
- Date fields use a calendar-popup helper; per-day tournament hours render an Open/Close time pair per event day; the Discord-server select is populated from `DiscordService.list_guilds`. **Save** validates and persists each key through `SystemConfigService.set_raw` / `set_tournament_hours`.

## Reports subsystem (`pages/admin_tabs/reports/`)

Behavior doc: [../features/admin-reports.md](../features/admin-reports.md). Data aggregation lives in `ReportsService`, `AnalyticsService`, `TelemetryService`, `AuditService`, and `SystemConfigService` (see [services.md](services.md)); the UI layer here is read-only.

`_REPORT_HANDLERS` maps the `report` query param to a page coroutine; `reports_page(report=None, **params)` is the tab entry point. An unknown or missing `report` renders the dashboard; otherwise the handler receives all forwarded query params (each swallows extras via `**_unused`) and an interaction row is tracked fire-and-forget.

| `report=` | Handler | Params consumed | Panels |
|---|---|---|---|
| _(none)_ | `dashboard.dashboard_page` | — | Four KPI cards (peak players vs capacity, peak stages vs max, match counts, stream-candidate crew coverage) + one clickable card per `REPORT_CARDS` entry |
| `insights` | `insights.insights_page` | `start`, `end`, `bucket`, `tournament_id` | KPI strip + crew / volunteer-hours / tournament-health / admin-activity sections, each bucketed by week or month |
| `capacity` | `capacity.capacity_page` | `start`, `end`, `tournament_id`, `focus` | ECharts line chart (active + on-stream players, dashed capacity line, dataZoom); "Top 5 peak times" with **Inspect** links; matches-active-at table when focused; raw per-interval forecast table |
| `match_ops` | `match_ops.match_ops_page` | `start`, `end`, `tournament_id`, `state` | Per-tournament aggregates (matches, started, finished, avg start delay, avg/expected duration, on-time %) + per-match detail (start delay, duration, confirmation lag, room, player count) |
| `crew` | `crew.crew_page` | `start`, `end`, `tournament_id`, `user_id`, `approval` | Coverage by match (approved/total commentators + trackers, stream-candidate flag, GAP marker) + contribution by person (signups, approvals, percentages, hours); a row click filters both tables by `user_id` |
| `stream_rooms` | `stream_rooms.stream_rooms_page` | `start`, `end`, `tournament_id`, `stream_room_id` | Stacked horizontal bar of scheduled vs gap hours + per-room summary (matches, hours, back-to-back <15 min); a row click drills into that room's match list |
| `volunteers` | `volunteers.volunteers_page` | `start`, `end` | Understaffed-shift summary card + all-shifts table (position, label, start, filled/needed, status) |
| `audit` | `audit.audit_page` | `start`, `end`, `user_id`, `action`, `page` | Server-side paginated log viewer over `AuditService.count_logs` / `list_logs`; an "Action contains" filter and a row-click user filter |
| `telemetry` | `telemetry.telemetry_page` | `start`, `end`, `user_id`, `action`, `category`, `page` | Staff-only engagement view over `TelemetryService`: leaderboards plus the same paginated event log |

Every panel above carries a CSV export unless noted. Three behaviours are not derivable from the table:

- **Capacity `focus`** is an ISO timestamp that pre-zooms the chart to a ±2-hour window and reveals the matches-active-at-that-instant table.
- **Insights** defaults to a trailing 90-day window rather than the event window, because a single event weekend collapses to one bucket.
- **Audit and telemetry** paginate server-side at `PAGE_SIZE = 50`, and their CSV export covers the **current page only**.

### URL-driven state and CSV export

Reports hold no client-side state. Every filter widget's change handler calls `navigate_with_params(report=..., **filters)`, which rebuilds an `/admin/reports?...` URL and triggers a full page reload — the back button and shareable links work for free. Date ranges default to the configured event window (`SystemConfigService.get_event_window()`) when not in the URL.

CSV export (`csv_export_button`) downloads the currently rendered rows using `rows_to_csv_bytes` / `timestamped_filename` from [`application/utils/csv_export.py`](../../application/utils/csv_export.py) — UTF-8 with BOM, formula-injection prefixes escaped, hidden columns skipped.

### Shared helpers (`reports/shared.py`)

| Helper | Purpose |
|---|---|
| `REPORT_KEYS` | Tuple of report keys — currently unreferenced; the dashboard cards are driven by `dashboard.REPORT_CARDS` |
| `CHART_GOLD` / `CHART_TEAL` / `CHART_RED` / `CHART_NEUTRAL` / `CHART_TEXT` / `CHART_GRID` | The chart palette. Fixed mid-tone steps chosen to clear 3:1 on **both** the light and dark card surfaces; colours are assigned **by role** (primary series, secondary series, threshold, idle), never per chart |
| `themed_chart_option(option)` | Overlay the mode-neutral chrome colours onto an ECharts option without clobbering what the chart already sets |
| `reports_url(report=None, **params)` | Build `/admin/reports[?report=…]` URLs; drops empty params, ISO-formats dates |
| `parse_date(value)` / `parse_int(value)` | Lenient parsing; `None` on garbage |
| `eastern_bounds(start_d, end_d)` | Eastern date range → half-open aware datetime bounds (end clamped ≥ start) |
| `async default_date_range(start_param, end_param)` | The URL dates if both parse, else `SystemConfigService.get_event_window()` |
| `report_page_shell(title, back_to_dashboard=True)` | Context manager: page container, "← Reports" back link, title, separator |
| `date_range_filter(default_start, default_end, on_change)` | Start/End inputs with calendar popups; fires `on_change(start, end)` on either change |
| `async tournament_filter(current_id, on_change)` | Tournament select with an "All tournaments" (`0`) option |
| `kpi_card(title, value, subtitle, color, min_width)` | One flex KPI tile for report strips (dashboard and insights) |
| `parse_details(raw)` | `(parsed_json_or_none, display_text)` for an audit/telemetry blob; legacy plain-text rows pass through unchanged |
| `clicked_row(e)` | Extract the row dict from a NiceGUI `row-click` event |
| `paginated_event_log(...)` | The shared server-side-paginated log table (audit + telemetry): columns, CSV, count label, pager |
| `csv_export_button(filename_prefix, columns_provider, rows_provider, label='Export CSV')` | Download button; notifies on failure |
| `navigate_with_params(report=None, **params)` | `ui.navigate.to(reports_url(...))` — the reload-based filter mechanism |

## Dialog catalog (`theme/dialog/`)

All dialogs follow the same shape: a `ui.dialog` + `.dialog-card`, a title row with a close button, a body, and an action row; most submit on Enter via a `keydown` handler and report errors with `ui.notify` (`PermissionError` → negative, `ValueError` → warning/negative). [`theme/dialog/__init__.py`](../../theme/dialog/__init__.py) re-exports `ApproveCrewDialog`, `CatFactDialog`, `CheckoutDialog` (plus `open_checkout` / `quick_checkin`), `ConfirmationDialog`, `EquipmentDialog`, `FeedbackDialog`, `MatchResultDialog`, `QrLabelDialog`, `SendMessageDialog`, `StationAssignmentDialog`, `TournamentDialog`, `UserDialog`, and `AdminUserDialog`; the rest are imported by module path.

| File | Class(es) | Purpose | Opened from |
|---|---|---|---|
| [`_helpers.py`](../../theme/dialog/_helpers.py) | `form_dialog`, `dialog_header`, `dialog_actions`, `mobile_sheet`, `native_date_input`, `native_time_input`, `submit_on_enter` | The house dialog chrome every dialog builds on — keeps actions reachable on a phone | (imported) |
| [`match_dialog.py`](../../theme/dialog/match_dialog.py) | `BaseMatchDialog`, `AdminMatchDialog`, `UserMatchDialog` | Create/edit matches | Admin schedule; home Schedule & Player tabs |
| [`_match_bracket_link.py`](../../theme/dialog/_match_bracket_link.py) | `render_select`, `render_matchup_panel`, `apply_link`, `matchup_label`, `linked_matchup_id` | The admin editor's bracket-matchup panel + picker | `AdminMatchDialog` |
| [`bracket_schedule_dialog.py`](../../theme/dialog/bracket_schedule_dialog.py) | `BracketScheduleDialog` | Schedule one game of a native-bracket matchup | Home Player tab (player mode); bracket match dialog (staff mode) |
| [`confirmation_dialog.py`](../../theme/dialog/confirmation_dialog.py) | `ConfirmationDialog` | Generic confirm/cancel; the negative-styled confirm button runs the caller's `on_confirm` | Start/Confirm actions, crew signup/undo, match/triforce-text/equipment/shift deletes |
| [`approve_crew_dialog.py`](../../theme/dialog/approve_crew_dialog.py) | `ApproveCrewDialog` | Toggle commentator/tracker approval via `CrewService.update_crew_approval` | Crew name click in admin match table |
| [`match_result_dialog.py`](../../theme/dialog/match_result_dialog.py) | `MatchResultDialog` | Required Winner select over the match players → `MatchService.record_match_result`; the Finish callback then calls `MatchScheduleService.finish_match` | Admin schedule Finish button |
| [`station_assignment_dialog.py`](../../theme/dialog/station_assignment_dialog.py) | `StationAssignmentDialog` | One Station input per player (≤50 chars, blank clears); submits the full `{player_id: station}` map to `MatchService.assign_stations` | Admin schedule Check In flow & players-column button |
| [`stream_room_dialog.py`](../../theme/dialog/stream_room_dialog.py) | `StreamRoomDialog` | Assign a match to a stage + stream-candidate flag; subclasses `BaseMatchDialog` to reuse its wiring | Admin schedule Stage column |
| [`stream_room_edit_dialog.py`](../../theme/dialog/stream_room_edit_dialog.py) | `StreamRoomEditDialog` | Create/edit a `StreamRoom` | Admin Stream Rooms tab |
| [`tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py) | `TournamentDialog` | Create/edit a tournament. Seed-generator options come from `SeedGenerationService.AVAILABLE_RANDOMIZERS` ([seed-generation.md](seed-generation.md)); a **Racetime** section appears only when the actor passes `AuthService.can_manage_sync`, and its bot select offers only categories the tenant is authorized for | Admin Tournaments tab |
| [`tournament_players_dialog.py`](../../theme/dialog/tournament_players_dialog.py) | `TournamentPlayersDialog` | Read-only enrolled-player list | Player-count link in tournament table |
| [`send_message_dialog.py`](../../theme/dialog/send_message_dialog.py) | `SendMessageDialog` | Send a Discord DM (required textarea; default callback is `DiscordService.send_dm`) | `AdminUserDialog` "Send Message" |
| [`user_edit_dialog.py`](../../theme/dialog/user_edit_dialog.py) | `BaseUserDialog`, `UserDialog`, `AdminUserDialog` | Profile / full user editing | Admin Users tab; player-name click in match tables |
| [`challonge_schedule_dialog.py`](../../theme/dialog/challonge_schedule_dialog.py) | `ChallongeScheduleDialog` | Date/Time only — tournament and both players come from the bracket; pre-filled from `MatchSuggestionService.suggest_match_time`, submitted via `ChallongeService.schedule_challonge_match` | Home Player tab "Schedule" button |
| [`volunteer_position_dialog.py`](../../theme/dialog/volunteer_position_dialog.py) | `VolunteerPositionDialog` | Create/edit a `VolunteerPosition` | Admin Volunteers "Manage positions" |
| [`volunteer_shift_dialog.py`](../../theme/dialog/volunteer_shift_dialog.py) | `VolunteerShiftDialog` | Create/edit a `VolunteerShift` (end date auto-tracks the start until edited) | Admin Volunteers Add/Edit shift |
| [`volunteer_profile_dialog.py`](../../theme/dialog/volunteer_profile_dialog.py) | `VolunteerProfileDialog` | View a volunteer's availability, edit their qualifications | Vol. Roster manage button |
| [`volunteer_export_dialog.py`](../../theme/dialog/volunteer_export_dialog.py) | `VolunteerExportDialog` | Date-ranged ZIP export of the volunteer bundle | Both volunteer admin tabs |
| [`checkout_dialog.py`](../../theme/dialog/checkout_dialog.py) | `CheckoutDialog` (+ `open_checkout` / `quick_checkin`) | Check an asset out. `open_checkout` shows the borrower picker only when `can_manage`; otherwise it self-checks-out immediately | Equipment tab, admin Equipment tab, asset detail page |
| [`equipment_dialog.py`](../../theme/dialog/equipment_dialog.py) | `EquipmentDialog` | Create / edit a lending asset; create mode adds a Quantity field for bulk creation (`bulk_create_assets`) | Admin Equipment tab; asset detail Edit |
| [`qr_label_dialog.py`](../../theme/dialog/qr_label_dialog.py) | `QrLabelDialog` | Pick/filter assets, choose a template (plain or Avery) + content, then open the printable sheet in a new tab | Admin Equipment tab "Print QR labels" |
| [`feedback_dialog.py`](../../theme/dialog/feedback_dialog.py) | `FeedbackDialog` | Submit feedback, capturing `window.location` via `ui.run_javascript` | Drawer "Feedback" item (any page, logged in); the 500 error page |
| [`cat_fact_dialog.py`](../../theme/dialog/cat_fact_dialog.py) | `CatFactDialog` | Easter egg — five taps on the header wordmark, or the Konami code | `BaseLayout._render_header` |

### Match dialogs (`theme/dialog/match_dialog.py`)

**`BaseMatchDialog(match=None, on_submit=None)`** holds shared state and helpers: it captures `match.updated_at` at construction for optimistic-concurrency checks, supplies the tournament/date/time/comment/stage defaults, the date+time inputs with popup pickers, the five **Clear** buttons (Check In / Started / Finish / Confirmed / Seed — each disabled when the corresponding timestamp or seed relation is already empty, setting `_clear_*` flags that `MatchService.update_match` consumes), the watch toggle (`MatchWatcherService.watch` / `unwatch`, reverting itself on `ValueError`), and the `ConfirmationDialog`-guarded delete.

**`AdminMatchDialog`** — the full create/edit form. Beyond the obvious fields:

- The Players multi-select is restricted to players enrolled in the selected tournament unless "Choose any players" is set; options reload whenever the tournament or checkbox changes.
- **Bracket matchup** (optional, only when `FeatureFlag.BRACKETS` is live) — when the match already backs a game, a read-only matchup panel sits above the picker (`render_matchup_panel` → `BracketService.matchup_summary`) showing stage · round, series position and score, both entrants with seeds, and a button into the bracket view, so staff editing a game can see *what it is for*. The picker below lists the tournament's OPEN matchups with a free game slot (`BracketService.list_linkable_matches`); in edit mode the current link is preselected by hand (a linked matchup is no longer "linkable") and `(None)` unlinks. Lives in [`_match_bracket_link.py`](../../theme/dialog/_match_bracket_link.py).
- **Edit mode only** adds the clear buttons, a read-only Player Acknowledgments list from `MatchAcknowledgmentRepository.list_for_match` (see [../features/match-participation.md](../features/match-participation.md#acknowledgment)), a **Racetime Room** section when the tournament has a racetime bot (slug + status, or a STAFF/`SYNC_ADMIN` "Create racetime room" button calling `RaceRoomService.manual_create_room` — a manual open independent of the auto-open toggle), and Delete.

On save it validates required fields, runs `MatchService.ensure_players_enrolled`, then:

- *Edit*: re-fetches the match and aborts with a warning if `updated_at` changed since the dialog opened (another admin edited it); otherwise `MatchService.update_match(...)` with the clear flags, plus `assign_stage` / `set_stream_candidate` only when those changed.
- *Create*: `MatchService.create_match(...)`, then `assign_stage` if a stage was chosen.
- Either way, a changed bracket-matchup selection is reconciled by `BracketService.unlink_match` and/or `link_match_to_bracket_match` **after** the match write — the `Match` has to exist before it can be linked.

**`UserMatchDialog(discord_id, match=None, on_submit=None)`** — the player-facing variant. Tournament options default to the player's enrolled tournaments; a "Show all tournaments" checkbox widens the list, and submitting auto-enrolls if needed. Both lists come from `TournamentService.list_player_requestable`, which excludes bracket-run tournaments (see [Who may schedule](../features/brackets.md#who-may-schedule-and-the-manual-request-lockout)). A single required Opponent select lists the other enrolled players. With no selectable tournament the form short-circuits with a message — "opt into a tournament", or a pointer to Your Schedule when every one of their tournaments runs on a bracket. Submission uses the same `updated_at` concurrency check, then `update_match` (with empty crew lists) or `submit_match_request`, with the player as `actor`.

### User dialogs (`theme/dialog/user_edit_dialog.py`)

**`BaseUserDialog`** captures `user.updated_at` for concurrency checks and provides tournament-enrollment helpers built on `TournamentRepository` and `UserService.update_user_tournament_registrations` / `manage_tournament_enrollments`.

**`UserDialog`** — self-edit: read-only Username, Display Name, Pronouns, and a tournament multi-select; saves via `UserService.update_user_profile` (with `check_concurrency=True` and the captured `initial_updated_at`) plus the enrollment sync. No role editing.

**`AdminUserDialog`** — verifies `AuthService.is_staff(actor)` on open and refuses otherwise.

- Username is required and editable only on create (read-only on edit); Discord ID is create-only. On edit, when Challonge is configured, the dialog manages the user's link: a linked user gets an editable "Challonge username" saved via `ChallongeService.set_player_username`; an unlinked user gets "Challonge account id" + optional username inputs Staff can fill to link manually via `link_player_manually` (the id must be unique across users).
- A Roles multi-select over the `Role` enum, and three tournament multi-selects: Player enrollments, "Tournament Admin of", "Crew Coordinator of".
- On save it diffs each selection against current state: `UserService.grant_role` / `revoke_role` per added/removed role, and `TournamentService.add_admin` / `remove_admin` and `add_crew_coordinator` / `remove_crew_coordinator` per membership change. Create mode goes through `UserService.create_user` first, then applies the same syncs. See [authentication.md § Roles](authentication.md#roles).
- Edit mode adds a **Send Message** button opening `SendMessageDialog`.

## Shared presentation components (`theme/`)

| Module | Purpose |
|---|---|
| [`availability_editor.py`](../../theme/availability_editor.py) | `render_availability_editor(service, *, help_text)` — the window-row + effective-graph UI behind **both** My Availability tabs. A `@ui.refreshable` row per window (Date / Start / End + a Preferred / Available / Unavailable select + delete), **Add window**, and **Save availability** through the injected service's `set_windows`; plus a second `@ui.refreshable` per-day coloured bar from `effective_segments(...)` (overlap resolves Unavailable > Preferred > Available), refreshed live as any input changes. The home tab injects `PlayerAvailabilityService`, the volunteer tab `VolunteerAvailabilityService`; both span the configured event window (`SystemConfigService.get_event_window()`), one Eastern calendar day per graph row |
| [`realtime.py`](../../theme/realtime.py) | `register_view(on_change)` subscribes a view to [`application/events/match_live`](../features/event-system.md) and installs the client-disconnect cleanup |
| [`empty_state.py`](../../theme/empty_state.py) | `empty_state(message)` and the `no_data_slot(...)` Quasar template, used by the table views and the On Air tab |
| [`notify.py`](../../theme/notify.py) | `notify_error(exc)` — the one place service `ValueError`/`PermissionError` map to a coloured toast |
| [`chrome.py`](../../theme/chrome.py) | See [Tenant-less chrome](#tenant-less-chrome-themechromepy) |

## Table views (`theme/tables/`)

Three view classes — `MatchTableView`, `TournamentTableView`, `UserTableView` — share a pattern: the constructor takes `columns` (NiceGUI/Quasar column dicts) and `get_query` (a callable returning a queryset or row provider), builds a `ui.table` with custom cell slots, switches to card-grid rendering on small screens via `:grid="Quasar.Screen.lt.md"` with a hand-built `item` slot, and exposes `refresh()` plus `update_row_by_id()` for single-row updates. Tables start empty; the view owns its first load. Pagination changes re-trigger a refresh. The fourth **family table**, equipment, has no view class: each equipment surface builds its own `ui.table` with a bespoke `item` slot.

### `MatchTableView` (`theme/tables/match.py`)

The largest UI component, used by the home Schedule and Player tabs and the admin Schedule tab. Split across `match.py` (view), `match_slots.py` (Vue templates), `match_grid.py` (cards), and `match_handlers.py`.

**Constructor flags**: `admin_controls` (admin slots and lifecycle buttons), `can_crud` (edit/approve affordances within admin mode), `extra_slots` (caller-supplied cell templates), `submit_match_callback` (renders the Create Match / Request Match button), `player_discord_id` (scopes data to one player), and per-action callbacks `on_edit`, `on_generate_seed`, `on_seat`, `on_start`, `on_finish`, `on_confirm`, `on_edit_stream_room`, `on_assign_stations` — slots and event handlers are registered only for callbacks that are provided. Four **board-shaping** options exist for surfaces that need a different frame around the same rows (only the Proctor Station board uses them today): `row_sort` (a `list[dict] -> list[dict]` applied just before the rows reach the table), `exclude_racetime` (threaded down to `MatchRepository.get_all`, dropping matches whose tournament runs on racetime.gg), `on_rows_changed` (called with the visible rows after every `refresh()` and `update_row_by_id()`, for a summary strip), and `actions_first` (mobile card renders its actions row directly under the players).

**Filters** — a card with three multi-selects (Tournament, Stage, State) and a refresh button; options load asynchronously from `MatchDisplayService.get_tournaments_for_filter` / `get_stream_rooms_for_filter`. Values persist **per user per tenant** through `tenant_session_get` / `tenant_session_set` ([`application/utils/tenant_session.py`](../../application/utils/tenant_session.py)), which key under `app.storage.user['by_tenant'][<tenant_id>]` — a filter is meaningful only within its own community. State defaults to `DEFAULT_STATE_FILTER` (Scheduled + Checked In + Started). Below 1024px the filter card collapses behind a toggle with an active-filter count badge.

**Live updates are push, not polled.** `register_view(self._on_remote_change)` subscribes the view through [`theme/realtime.py`](../../theme/realtime.py): a remote `'changed'` / `'deleted'` updates that one row (with a flash), `CREATED` refreshes the table, since a new match has no row yet.

**Data flow** — `refresh()` calls `MatchDisplayService.get_matches_for_display(tournament_ids, stream_room_ids, only_upcoming=False, user_discord_id, exclude_racetime)`, applies the state filter client-side, merges per-row `_watching` flags from `MatchWatcherService.list_watched_match_ids`, then applies `row_sort` (if given) and notifies `on_rows_changed`. `update_row_by_id(match_id)` re-fetches one row via `get_match_for_display` (deleting the row if the match is gone, preserving `_watching`); `delete_row_by_id` removes a row from the UI only.

**Cell rendering** — the players cell shows acknowledgment icons (green check / orange clock with timestamp tooltips, `(auto)` markers) and bolds the winner; admin mode also shows each player's station in italics. Commentator/tracker cells colour names by approval. The admin Seed column shows a Generate button (with client-side `_generating_seed` spinner state) when the tournament has a seed generator and no seed exists; existing seeds render as truncated links. The admin State column renders the next lifecycle action per state — Scheduled → Check In, Checked In → Start, Started → Finish, Finished → Confirm — each with the previous transition's timestamp; Confirmed renders an icon + timestamp. The Stage column shows an Assign button for unassigned matches and an amber "candidate" badge for stream candidates.

**Event wiring** (table and grid templates emit the same events; `_event_match_id` normalizes the `{key}` / `{row}` payload shapes):

| Event | Emitted by | Handled by |
|---|---|---|
| `edit_match` | Match-ID link | `on_edit(match_id)` callback |
| `roll` | Generate button (Seed column) | `on_generate_seed(match_id)` |
| `seat` / `start` / `finish` / `confirm` | State-column lifecycle buttons | matching `on_*(match_id)` callback |
| `edit-stream-room` | Stage Assign button | `on_edit_stream_room(match_id)` |
| `assign_stations` | Players-column button (admin + crud) | `on_assign_stations(match_id)` |
| `edit_player` | Player name link | opens `UserDialog` for that player |
| `edit_commentator` / `edit_tracker` | Crew name link (admin + crud) | opens `ApproveCrewDialog`, row refresh on approve |
| `signup_commentator` / `signup_tracker` | Sign Up button (non-admin) | `ConfirmationDialog` → `CrewService.signup_crew` |
| `undo_commentator` / `undo_tracker` | Undo button (non-admin) | `ConfirmationDialog` → `CrewService.undo_crew_signup` |
| `acknowledge_match` | Player's own Acknowledge button | `MatchService.acknowledge_match` (client captured via `context.client`, restored with `with client:`) |
| `acknowledge_commentator` / `acknowledge_tracker` | Crew member's own Acknowledge button | `CrewService.acknowledge_crew_assignment` |
| `toggle_watch` | Watch column button (logged-in) | `MatchWatcherService.watch` / `unwatch`, flips `_watching` locally |
| `open_bracket` | Bracket-ref link under the tournament name | `ui.navigate.to` the bracket view |
| `update:pagination` | Quasar pagination | full `refresh()` |

Crew signup/undo and acknowledge buttons only render for the logged-in user's own entries; the templates compare row data against the user's `discord_id`, interpolated into the slot HTML at build time. See [../features/match-participation.md](../features/match-participation.md).

**Grid mode** — `match_grid.render_grid_slot()` generates a label/value card per row from the column list (JS field descriptors built in Python), re-implementing the ID link, acknowledgment icons, crew signup/acknowledge buttons, lifecycle state buttons, seed generation/links, watch toggle, and stage assignment for mobile, with admin/crud behavior baked in via template interpolation (`__IA__`, `__CC__`, `__DID__`, `__WATCH__`, `__ACTCLS__`). Card order is headline → players → caption → details → actions; with `actions_first=True` it becomes headline → players → actions → caption → details, and the actions row gains `mgc-actions--first`, which moves its divider from top to bottom.

**Overdue rows** — `MatchDisplayService` puts `is_overdue` (scheduled time passed, not checked in, not finished) and `scheduled_ts` (an epoch sort key; the formatted `scheduled_at` string does not sort) on every row. The desktop `scheduled_at` cell and the mobile card headline tint the time amber and add a clock icon when it is set; `scheduled_ts` is what `row_sort` implementations order within a bucket.

### `TournamentTableView` (`theme/tables/tournament.py`)

- Toolbar: optional **Add Tournament** button (when `submit_tournament_callback` is provided) plus a refresh button.
- Slots: clickable Name (emits `edit_tournament` → `TournamentDialog`), clickable Player Count (emits `show_players` → `TournamentPlayersDialog`), truncated Description with tooltip, icon rendering for Active and Staff Administered.
- `refresh()` orders by name and builds rows from `get_query().prefetch_related('players')` (player count computed from the prefetched relation); `update_row_by_id` refreshes one row. Editing does not auto-refresh the row afterwards.

### `UserTableView` (`theme/tables/user.py`)

- Optional toolbar (`show_toolbar=False` lets the caller render its own, as the admin Users tab does).
- Slots: clickable Username (emits `edit_user` → `AdminUserDialog`), Active icon, truncated Discord ID, linked Challonge account, and Roles rendered as `q-chip`s.
- `refresh()` orders by username and prefetches `roles`, `admin_tournaments`, `crew_coordinated_tournaments`; `_format_user_row` title-cases role names and appends `TA(n)` / `CC(n)` markers for tournament-scoped roles. Timestamps format through `format_eastern_display`.

### Shared kit (`admin_crud.py`)

Two helpers every service-backed admin tab uses:

- **`wire_tab_refresh(tab_name, refresh)`** — the piece with a correctness reason to exist. It captures the tenant during the page build and rebinds it around the refresh, because `selected_tab` is a client event whose handler runs in a detached background task that has lost the contextvar; without the rebind a scoped read raises `require_tenant_id()` (swallowed) and the tab never repaints.
- **`current_actor()`** — the logged-in `User`, or `None`.

The module previously also carried a `ServiceTableView` generic plus page-container, toolbar and actions-slot helpers, and a sibling `equipment.py` kit. Both were extracted in anticipation of adoption that never happened — after two audits recommending it, neither had a single importer — so they were deleted rather than left as an optional style choice. Recover them from git history if a genuine second caller appears.

### Responsive tables — the mobile grid rule

**Every `ui.table` must have a mobile card view.** A bare HTML `<table>` overflows a phone: its columns and (worse) its row-action buttons scroll off the right edge. Quasar's *grid mode* fixes this — below a breakpoint the table renders an `item` slot per row instead of `<tr>`s. The mechanical guardrail [`check_table_grid.py`](../../.claude/scripts/check_table_grid.py) (PostToolUse) flags any presentation-layer `ui.table` that lacks it.

Two sanctioned ways to comply:

1. **`enable_mobile_grid(table, columns, …)`** ([`theme/tables/mobile_grid.py`](../../theme/tables/mobile_grid.py)) — the default for every admin / report / player table. It's column-driven: it adds `:grid="Quasar.Screen.lt.md"` and generates a `.wiz-grid-card` `item` slot from the same `columns` the desktop table uses (skipping `hidden` columns and the `actions` column). Pass `actions=` the **same** row-action button HTML used in the `body-cell-actions` slot (hoist it into one constant — don't duplicate), `field_slots={'status': '<q-badge …>'}` for any badge/chip/icon column (the snippet reads `props.row.<field>`, not the desktop cell's `props.value`), and `row_click_event='row-click'` to keep a whole-row drill-down tappable on mobile.

   ```python
   from theme.tables.mobile_grid import enable_mobile_grid

   table = ui.table(columns=_COLUMNS, rows=rows, row_key='id').classes('w-full wiz-table')
   table.add_slot('body-cell-status', f'<q-td :props="props">{_STATUS_BADGE}</q-td>')
   table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
   enable_mobile_grid(table, _COLUMNS, actions=_ROW_ACTIONS, field_slots={'status': _STATUS_BADGE})
   ```

2. **A bespoke `item` slot** with an inline `:grid="Quasar.Screen.lt.md"` prop — reserved for the four purpose-built family tables (match / user / tournament / equipment), whose cards are too custom for the generic helper.

A table that legitimately must stay a table on mobile (a narrow 2-column reference) opts out with a `# mobile-grid: exempt` comment on the `ui.table` line. The generic card styling is `.wiz-grid-card` (the card counterpart of `.wiz-table`).

## Static assets & styling (`static/`)

`static/` is served at `/static` (uncached in development — see [NiceGUI integration](#nicegui-integration-frontendpy)). It holds the two stylesheets, the PWA assets ([`manifest.webmanifest`](../../static/manifest.webmanifest), `icons/`, `fonts/`), [`sw.js`](../../static/sw.js) (served from the site root `/sw.js`; a no-cache pass-through worker that satisfies Chrome's installability requirement and renders Web Push messages on browsers without Declarative Web Push — see [../features/web-push.md](../features/web-push.md)), [`js/web-push.js`](../../static/js/web-push.js), and `triforce.svg`.

- [`css/styles.css`](../../static/css/styles.css) — the app stylesheet, loaded by `BaseLayout.render_chrome()` and `render_platform_chrome()`. Organized into class families (layout containers, headers/text, cards/forms/dialogs/buttons, the On Air timeline, the four table families + their grid cards, dark-mode overrides, report chart sizing, the OAuth consent card) with section comments; grep the family prefix rather than a per-page rule.
- [`css/brackets.css`](../../static/css/brackets.css) — the bracket renderer's geometry and colour, linked per page by `theme/brackets/`. Its pixel constants mirror `theme/brackets/layout.py`; change one, change both.

The one non-obvious rule: `--bracket-*` is declared on **`body`**, not `:root`, because `ui.colors()` writes the tenant `--q-primary` onto `body` while Quasar's stock blue sits on `:root`.

## NiceGUI patterns

Canonical rules: [`CLAUDE.md`](../../CLAUDE.md) § NiceGUI patterns. Worked examples here: `MatchTableView._bg` (background tasks), `theme/realtime.py` (client capture), `BaseLayout._build_tab` and `admin_crud.wire_tab_refresh` (deferred work rebinding the tenant), `theme/tables/match.py` (`tenant_session_get`/`set` for per-user-per-tenant state), the triforce-text lists (`@ui.refreshable`).
