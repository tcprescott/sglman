# Frontend / UI Architecture Reference

_Method-level reference for the presentation layer: [`frontend.py`](../../frontend.py), [`pages/`](../../pages/), [`theme/`](../../theme/), and [`static/`](../../static/). Part of the [documentation index](../README.md)._

The UI is built entirely with NiceGUI (Quasar/Vue under the hood) mounted into the FastAPI app. Pages call the service layer for all writes; see [services.md](services.md) for the service APIs and [../architecture.md](../architecture.md) for the three-layer pattern. Login and route protection are covered in [authentication.md](authentication.md).

## NiceGUI integration (`frontend.py`)

[`frontend.py`](../../frontend.py) wires NiceGUI into FastAPI.

At import time it registers `AuthMiddleware` (from [`middleware/auth.py`](../../middleware/auth.py)) on the NiceGUI `app`. The middleware redirects unauthenticated requests to `/login` for any route registered via `@protected_page` — see [authentication.md](authentication.md).

**`NoCacheStaticFiles`** — a `StaticFiles` subclass. When `ENVIRONMENT` is `development` (the default) it rewrites every HTTP response to add `Cache-Control: no-cache, no-store, must-revalidate`, `Pragma: no-cache`, and `Expires: 0`, so CSS edits show up without a hard refresh. In production it behaves like plain `StaticFiles`.

**`init(fastapi_app)`** — the single entry point, called from `main.py`:

1. Calls `validate_security_config()` ([`application/utils/environment.py`](../../application/utils/environment.py)) — aborts startup if `STORAGE_SECRET` is empty, and in production also requires `DB_USERNAME` / `DB_PASSWORD`.
2. Mounts `/static` → `NoCacheStaticFiles(directory="static")`.
3. Registers pages in order: `auth.create()` (login/logout/oauth pages from [`pages/auth.py`](../../pages/auth.py), or the mock-Discord user picker — see [../features/mock-discord.md](../features/mock-discord.md)), `challonge_oauth.create()` (Challonge link/connect OAuth routes from [`pages/challonge_oauth.py`](../../pages/challonge_oauth.py)), `twitch_oauth.create()` and `racetime_oauth.create()` (identity-link OAuth routes), then `admin.create()`, `home.create()`, `volunteer.create()`, and `equipment.create()`.
4. Calls `ui.run_with(fastapi_app, storage_secret=...)` with the stripped `STORAGE_SECRET`. No `mount_path` is given, so `@ui.page` routes live at the site root.
5. Calls `register_error_handlers(fastapi_app)` ([`middleware/error_handlers.py`](../../middleware/error_handlers.py)) to install themed 40x/50x pages — see [Error pages](#error-pages-middlewareerror_handlerspy) below.

## Layout system (`theme/base.py`)

[`theme/base.py`](../../theme/base.py) defines **`BaseLayout`**, the shell used by every page.

Constructor: `BaseLayout(copyright_text=..., section=None, base_path=None, tabs=None, user=None, show_admin=False, show_volunteer=False, **_kwargs)`.

- `tabs` is a list of dicts `{'label', 'icon', 'content'}` (optionally `'slug'`). `content` is either a callable (sync or async, detected via `inspect.iscoroutinefunction`) or a tuple `(callable, args, kwargs)` for parameterized tabs — the admin page uses the tuple form to pass `can_crud` and the report query params.
- `section` is the URL **slug** of the initially active tab (e.g. `reports`); it resolves to a label via the auto-derived slug map (`tab_slug()`, or an explicit `'slug'` key). An unknown or missing slug falls back to the first tab.
- `base_path` is the section URL base **including any `/t/<slug>` root_path** (e.g. `/t/foo/admin`); tab switches rewrite the URL to `{base_path}/{slug}`. `None` on tab-less pages, which never touch the URL.
- `show_admin=True` adds an "Admin" entry to the drawer's top menu (Home is always present).
- `show_volunteer=True` adds a "Volunteer" entry (→ `/volunteer`) to the drawer's top menu; every page passes it as `user is not None` so any logged-in user sees the link.
- Callers also pass `page_name=...`; `BaseLayout` absorbs it via `**_kwargs` and does not use it.

`async render()` calls the synchronous `render_chrome()` (palette, header, drawer, footer) and then, if `tabs` were supplied, `await`s `_render_tab_panels()`. The split exists so non-async callers — notably the `on_page_exception` 50x error path, which NiceGUI invokes synchronously — can render the full themed shell via `render_chrome()` without awaiting. The page builds in order:

| Step | Method | Behavior |
|---|---|---|
| Dark mode | `render_chrome()` | Reads `app.storage.user['dark_mode']` into `ui.dark_mode()`, then injects `<link rel="stylesheet" href="/static/css/styles.css">` |
| Header | `_render_header()` | Burger button toggling the drawer; a `ui.space()` flexible spacer pushes the user/login controls to the right edge (so alignment matches desktop even when the name is hidden on phones); when `user` is set: `preferred_name` label (hidden <600px), Discord avatar (from `app.storage.user['avatar']`) or an `account_circle` placeholder glyph when there is no avatar URL (mock-login sessions / Discord default avatars), logout button; otherwise a "Login with Discord" button whose text label is a child element hidden <600px (icon-only on phones — the full-text button still lives in the page body — with a tooltip for accessibility); finally a dark-mode toggle that persists to `app.storage.user['dark_mode']` and swaps its own icon |
| Drawer | `_render_drawer()` | `ui.left_drawer(value=False)` with `breakpoint=1023 show-if-above bordered` (auto-visible ≥1024px, behind the burger below it); contents live in a full-height flex column — top menu items (Home / Admin / Volunteer), one item per tab (active tab carries the Quasar `active` prop), a **Feedback** item for logged-in users, and the copyright caption (`.wiz-drawer-copyright`) pinned to the foot via `ui.space()` |
| Footer | `_render_footer()` | **Only** the mobile app-shell bottom nav (`.wiz-bottom-nav`), and only when there are tabs: the first four tabs plus a **More** button that opens the drawer; hidden ≥1024px, so desktop and tab-less pages render no footer. The wrapping `ui.footer()` (`.footer-dark-override`) supplies the surface + top border. Copyright and Feedback live in the drawer |
| Tabs | `_render_tab_panels()` | A `ui.tab_panels` whose value is switched programmatically; every tab's content renders eagerly at page load |

**Tab deep-linking.** Sections are addressed by **path segment** (`/admin/reports`), not a query param, so URLs read like app routes. Tab switching does not reload the page: `_switch_tab(label)` moves the `active` prop in the drawer, sets the tab-panels value, and — via `_handle_tab_change` — replaces the URL with `{base_path}/{slug}` through `ui.navigate.history.replace` (`replace`, not `push`, so per-tab switches don't stack a Back-button trap). The reverse direction works because each hub is registered under both `/base` and `/base/{section}` (via `protected_tab_page`, or three `ui.page()` calls for the public home page): the page function declares a `section: str = None` parameter — NiceGUI maps the path param onto it — and passes it to `BaseLayout`, which resolves the slug to the active tab. So `/admin/reports` opens directly on the Reports tab. The home hub lives at `/` (default section) with sections at `/home/<slug>`. Report filters (`report`, `start`, `end`, …) remain query params on top of the path (`/admin/reports?report=capacity`).

## Error pages (`middleware/error_handlers.py`)

Branded 40x/50x pages, all rendered through the standard `BaseLayout` chrome by **`render_error_page(...)`** in [`theme/error_page.py`](../../theme/error_page.py). The renderer is **synchronous** because NiceGUI invokes the `on_page_exception` hook without awaiting it; the only async work (loading the user to file a report) happens lazily in a button click handler.

NiceGUI is mounted as a sub-application by `ui.run_with` (`app.mount('/', core.app)`) and ships its own "sad face" 404/500 pages, so `register_error_handlers()` installs the overrides on the NiceGUI `app` (not the host FastAPI app):

| Status | Mechanism | Behavior |
|---|---|---|
| **404** | `@app.exception_handler(404)` override | Keeps NiceGUI's guard that returns JSON for non-page endpoints (the REST API and raised `HTTPException`s); renders a themed "Page not found" for real UI routes |
| **403** | `render_error_page(...)` call in [`middleware/auth.py`](../../middleware/auth.py) | The `@protected_page` denial path renders a themed "Forbidden" instead of a bare label |
| **500** | `app.on_page_exception` | NiceGUI calls this from `create_500_error_page` for exceptions raised inside `@ui.page` builders (where essentially all request handling runs) |

**Traceability.** Every unhandled 500 gets a `uuid4` `error_id` via `log_unhandled_error()`, which logs `UNHANDLED ERROR error_id=<uuid> path=<path>` with `exc_info` (clearly grep-able) and tags `error_id` on the Sentry scope so logs and Sentry events correlate. The error page surfaces the UUID and, for logged-in users, a **"Report this error"** button that opens `FeedbackDialog` prefilled (category `BUG`, message containing `Error reference: <uuid>`) — so the same UUID lands in the feedback row's `message`/`page_url`.

**DEBUG vs production.** Outside production (`is_production()` is false) the 500 page also renders the full traceback for diagnosis; in production it shows only the UUID.

## Pages & routes

| Route | File | Auth |
|---|---|---|
| `/`, `/home/{section}` | [`pages/home.py`](../../pages/home.py) | Public; some tabs degrade to a login prompt. `/` = default section |
| `/admin`, `/admin/{section}` | [`pages/admin.py`](../../pages/admin.py) | Login required (`@protected_tab_page`); content gated by role |
| `/volunteer`, `/volunteer/{section}` | [`pages/volunteer.py`](../../pages/volunteer.py) | Login required (`@protected_tab_page`); volunteer self-service hub |
| `/equipment/{asset_id}` | [`pages/equipment.py`](../../pages/equipment.py) | Login required (`@protected_page`, path-param route); asset detail / QR target |
| `/login`, `/logout`, `/oauth/callback` | [`pages/auth.py`](../../pages/auth.py) | See [authentication.md](authentication.md) |

Each page module exposes a `create()` function that registers its `@ui.page` route; `frontend.init()` calls them.

### Home (`/`, `pages/home.py`)

`home(tab: str = None)` sets the page title, resolves the current user from `app.storage.user['discord_id']`, and renders `BaseLayout`. Four tabs are always present; three more (My Availability, Triforce Texts, Equipment) are appended only when a user is logged in. If a `discord_id` is present but no matching `User` row exists, it shows an error, clears the session, and redirects to `/logout` after 2 seconds.

| Tab | Content function | Login needed? |
|---|---|---|
| Schedule | `home_tabs/schedule.py:schedule` | No (crew signup, watch, and edit require login) |
| On Air | `home_tabs/stage_timeline.py:stage_timeline_tab` | No |
| Profile | `home_tabs/player_edit_info.py:render_edit_info_tab` | Yes (renders a login card otherwise) |
| Player | `home_tabs/player.py:render_player_dashboard` | Yes (renders a login card otherwise) |
| My Availability | `home_tabs/availability.py:availability_tab` | Yes (tab only added when logged in) |
| Triforce Texts | `home_tabs/triforce_texts.py:triforce_texts_tab` | Yes (tab only added when logged in) |
| Equipment | `home_tabs/equipment.py:equipment_tab` | Yes (tab only added when logged in) |

A leading "Home" tab backed by an `announcements_page` is present but commented out in the tab list. `show_admin` is computed via `AuthService.can_view_admin(user)`; `show_volunteer` is `user is not None`.

### Admin dashboard (`/admin`, `pages/admin.py`)

`admin_dashboard_page(...)` is registered with `@protected_page('/admin')` — login is enforced by the middleware, with no route-level role. The function itself resolves the user, loads roles via `AuthService.get_roles` (including `VOLUNTEER_COORDINATOR` and `EQUIPMENT_MANAGER`), and checks Tournament Admin / Crew Coordinator membership via the `admin_tournaments` / `crew_coordinated_tournaments` relations. A user who is none of Staff / Stream Manager / Equipment Manager / Tournament-Admin-of-any / Crew-Coordinator-of-any gets a bare layout and a permission-denied message. Proctors are **not** admitted — their race/schedule workflow lives on the `/volunteer` page.

Tab visibility by role (a user sees the union of all rows they match). "VC" = Volunteer Coordinator, "EM" = Equipment Manager:

| Tab | Staff | Proctor | Stream Manager | Tournament Admin (any) | Crew Coordinator (any) | VC | EM |
|---|---|---|---|---|---|---|---|
| Schedule | yes | — | — | yes | yes | — | — |
| Users | yes | — | — | — | — | — | — |
| Tournaments | yes | — | — | yes | — | — | — |
| Stream Rooms | yes | — | yes | — | — | — | — |
| Triforce Texts | yes | — | — | yes | — | — | — |
| Vol. Roster | yes | — | — | — | — | yes | — |
| Vol. Schedule | yes | — | — | — | — | yes | — |
| Reports | yes | — | — | yes | yes | — | — |
| Challonge | yes | — | — | — | — | — | — |
| Discord Roles | yes | — | — | — | — | — | — |
| Equipment | yes | — | — | — | — | — | yes |
| Feedback | yes | — | — | — | — | — | — |
| Settings | yes | — | — | — | — | — | — |

(Tabs render in this order. The "Settings" tab is the System Configuration page.)

`can_crud = staff or tournament-admin-of-any` is passed into the Schedule tab; crew coordinators get a read-mostly Schedule — lifecycle buttons but no create/edit/stage-assign (see [Admin schedule](#admin-schedule-pagesadmin_tabsadmin_schedulepy)). Proctors reach the same `admin_schedule_page` (with `can_crud=False`) from the `/volunteer` page instead.

**Deep-link query params.** Besides the `section` path segment, the page accepts `report`, `start`, `end`, `tournament_id`, `user_id`, `stream_room_id`, `state`, `approval`, `action`, `focus`, and `page`, all forwarded as a kwargs dict into the Reports tab. Every report filter change navigates to a new `/admin/reports?report=...` URL, so report state is fully URL-driven and shareable.

Triforce texts has no standalone route: player submission lives in the home **Triforce Texts** tab ([`pages/home_tabs/triforce_texts.py`](../../pages/home_tabs/triforce_texts.py)) and admin moderation in the admin **Triforce Texts** tab ([`pages/admin_tabs/triforce_texts.py`](../../pages/admin_tabs/triforce_texts.py)) — behavior doc: [../features/triforce-texts.md](../features/triforce-texts.md).

## Home tabs (`pages/home_tabs/`)

| Module | Tab | Responsibility |
|---|---|---|
| [`schedule.py`](../../pages/home_tabs/schedule.py) | Schedule | Public event schedule with crew signup, watch toggles, notification preferences |
| [`stage_timeline.py`](../../pages/home_tabs/stage_timeline.py) | On Air | Per-day timeline of streamed matches grouped by stream room |
| [`player_edit_info.py`](../../pages/home_tabs/player_edit_info.py) | Profile | Self-service profile, DM preference, tournament opt-in; hosts the device-notification, Challonge-link and API-token sections |
| [`player.py`](../../pages/home_tabs/player.py) | Player | The logged-in player's own match list and match requests; Challonge bracket matches to schedule |
| [`availability.py`](../../pages/home_tabs/availability.py) | My Availability | Self-service availability windows over the event window with a live effective-availability graph |
| [`triforce_texts.py`](../../pages/home_tabs/triforce_texts.py) | Triforce Texts | Pick a supporting tournament, then submit/track triforce-screen text |
| [`equipment.py`](../../pages/home_tabs/equipment.py) | Equipment | Browse the lending inventory and the user's own checkouts |

Several further modules render **inside** the Profile tab rather than as standalone tabs (all called from `player_edit_info.py`):

| Module | Renders | Responsibility |
|---|---|---|
| [`api_tokens_section.py`](../../pages/home_tabs/api_tokens_section.py) | "API Tokens" card in Profile | Create / list / revoke personal REST API tokens via `ApiTokenService`; the plaintext token is shown once at creation |
| [`challonge_link_section.py`](../../pages/home_tabs/challonge_link_section.py) | "Challonge" card in Profile | Verify-link / unlink a Challonge account via `ChallongeService`; hides itself entirely when the integration isn't configured |
| [`twitch_link_section.py`](../../pages/home_tabs/twitch_link_section.py) | "Twitch" card in Profile | Verify-link / unlink a Twitch identity via `TwitchService`; hides itself entirely when the integration isn't configured |
| [`racetime_link_section.py`](../../pages/home_tabs/racetime_link_section.py) | "racetime.gg" card in Profile | Verify-link / unlink a racetime.gg identity via `RacetimeService`; hides itself entirely when the integration isn't configured |
| [`web_push_section.py`](../../pages/home_tabs/web_push_section.py) | "Device Notifications" card in Profile | Enable/disable web push on the current device and manage subscribed devices via `WebPushService`. The enable/disable buttons run [`static/js/web-push.js`](../../static/js/web-push.js) client-side via `js_handler` (permission prompts must stay inside the click gesture) and report back through `emitEvent` → `ui.on`. Hides itself entirely when VAPID keys aren't configured ([../features/web-push.md](../features/web-push.md)) |

### Schedule (`pages/home_tabs/schedule.py`)

The public event schedule with crew signup.

- Header "Schedule & Crew Signup" with a **Login with Discord** button when logged out. (Per-tournament notification preferences are managed on the Profile tab — see [../features/tournament-notifications.md](../features/tournament-notifications.md).)
- A `MatchTableView` with `admin_controls=False`. Columns: ID, Tournament, Scheduled At, State, Players, Stage, Generated Seed, Commentators, Trackers — plus Watch when logged in ([../features/match-watcher.md](../features/match-watcher.md)).
- `extra_slots` supply read-only state cells (per-state icon + timestamp) and a truncating seed-link cell.
- Clicking a match ID (logged-in only) opens `UserMatchDialog` for that match and refreshes the table on submit.
- Services: `MatchService.get_all_matches_for_schedule()` for data; the logged-in `discord_id` is read from `app.storage.user` and passed into `UserMatchDialog`.

### On Air (`pages/home_tabs/stage_timeline.py`)

`stage_timeline_tab()` — a per-day timeline of streamed matches grouped by stream room.

- Header: previous/next-day arrows, a Today button, a date input with calendar popup and Go button, plus a floating refresh button (`.refresh-button`). All handlers dispatch through `background_tasks.create`.
- Data: `MatchService.get_matches_for_date(target_date, exclude_finished=True, require_stream_room=True)`, grouped via `MatchService.group_matches_by_stream_room(matches)`; rooms sorted by name. The current date is tracked in US/Eastern (see [../timezone-handling.md](../timezone-handling.md)).
- Each room renders a card with a header (name, optional "Watch Stream" link, match count) and one `match-card` per match: Eastern time, status badge, tournament name, players ("A vs B"), and approved commentators/trackers. Card borders are color-coded by state (`.border-left-*`).
- Match IDs link to `/admin/schedule` when `AuthService.can_view_admin(user)` is true; otherwise they are plain labels.

### Profile (`pages/home_tabs/player_edit_info.py`)

`render_edit_info_tab()` — self-service profile editing.

- Installs a `beforeunload` JavaScript guard so unsaved edits prompt before navigation; every input's `on_change` calls `mark_dirty()` and a successful save calls `mark_clean()` (both flip a window flag via `ui.run_javascript`).
- Fields: Display Name (placeholder shows the Discord username default), Pronouns, a "Receive Discord DM notifications" checkbox, and one checkbox per active tournament, rendered in two sections: "Staff Administered Tournaments" and "Community Tournaments" (split on `tournament.staff_administered`).
- Challonge-linked tournaments (those with a `challonge_tournament_id`) don't use the manual opt-in: their checkbox is disabled and reflects bracket membership from `ChallongeService.participant_tournament_ids` (whether the player is mirrored as a participant), and the row links out to `challonge_tournament_url` when set. If the player hasn't linked their Challonge account (`user.challonge_user_id` unset) the row shows a "Link Challonge account" call to action instead. These tournaments are excluded from `tournament_checkboxes`; any existing manual enrollment for them is carried through unchanged on save so the registration sync never drops it.
- **Save Changes** calls `UserService.update_user_personal_info` then `UserService.update_user_tournament_registrations`, with the user as their own audit actor.
- Services: `UserService.get_active_tournaments_categorized`, `get_user_tournament_registrations`, `ChallongeService.participant_tournament_ids`, and the two update calls above.

### Player (`pages/home_tabs/player.py`)

`render_player_dashboard()` — "Your Schedule": the logged-in player's own matches.

- A `MatchTableView` (`admin_controls=False`, `player_discord_id` set). Columns: ID, Tournament, Scheduled At, State, Players, Stage, Generated Seed, Watch. Uses the same read-only state/seed `extra_slots` as the Schedule tab.
- A **Request Match** button opens `UserMatchDialog` in create mode.
- When Challonge is configured, an "Upcoming matches to schedule" card lists the player's unscheduled bracket matchups (`ChallongeService.list_unscheduled_matches_for_user`); each links an opponent and a **Schedule** button that opens `ChallongeScheduleDialog` (disabled when the opponent hasn't linked their account).
- Services: `MatchService.get_matches_for_player(discord_id)`, `ChallongeService.list_unscheduled_matches_for_user`.

### My Availability (`pages/home_tabs/availability.py`)

`availability_tab()` — self-service availability windows for any logged-in player.

- Spans the configured event window (`SystemConfigService.get_event_window()`), one Eastern calendar day per row in the graph. Existing windows load from `PlayerAvailabilityService.availability_for(user)`.
- A `@ui.refreshable` `window_rows()` section: one editable row per window (Date / Start / End inputs + a Preferred / Available / Unavailable status select + delete button). **Add window** appends a default row; **Save availability** validates and persists through `PlayerAvailabilityService.set_windows`.
- A second `@ui.refreshable` `effective_graph()` renders a per-day colored bar via `service.effective_segments(...)` — overlap resolves Unavailable > Preferred > Available — refreshed live as any input changes.

### Triforce Texts (`pages/home_tabs/triforce_texts.py`)

`triforce_texts_tab()` — inline tournament selection plus submission.

- A `@ui.refreshable` `content()` switches between an index (cards from `TriforceTextService.list_supporting_tournaments`, each with an Open button) and a per-tournament submission view selected by an in-memory `state['tournament_id']`.
- The submission view gates on `tournament.is_active` + `SeedGenerationService.supports_triforce_texts` and on `AuthService.can_submit_triforce_text`; ineligible players see the tournament's `triforce_access_message` (rendered as plain text to avoid stored XSS) or a paid-option notice.
- Three `maxlength=19` line inputs feed `TriforceTextService.submit`; "Your Submissions" is a `@ui.refreshable` badged Pending/Approved/Rejected list from `list_user_submissions`.

### Equipment (`pages/home_tabs/equipment.py`)

`equipment_tab()` — inventory browsing and the user's own checkouts.

- Two inner Quasar tabs: **Inventory** (all assets via `EquipmentService.list_assets` + `open_loans_by_equipment_id`, status badge, current holder) and **My Checkouts** (`EquipmentService.my_checkouts`).
- Per-row action buttons gated by `AuthService.can_checkout_equipment` / `can_checkin_equipment` (the **Check out** / **Check in** buttons go through `open_checkout` / `quick_checkin`, with `can_manage` from `can_manage_equipment`); a **View asset** button navigates to `/equipment/{id}`.
- Both tables use the `.equipment-table` family and switch to grid cards on small screens.

## Volunteer hub (`/volunteer`, `pages/volunteer.py`)

`volunteer_page(tab: str = None)` is registered with `@protected_page('/volunteer', roles=[Role.VOLUNTEER, Role.PROCTOR, Role.STAFF])`. It resolves the user, loads roles via `AuthService.get_roles`, and builds tabs by role before rendering `BaseLayout` (`show_volunteer=True`, `show_admin` via `AuthService.can_view_admin`). The self-service tabs show for `VOLUNTEER`; the **Proctor Station** tab (the proctor race workflow) shows for `PROCTOR` or `STAFF`.

| Tab | Shown to | Content function | Responsibility |
|---|---|---|---|
| My Availability | volunteer | `volunteer_tabs/availability.py:availability_tab` | Volunteer availability windows |
| My Shifts | volunteer | `volunteer_tabs/my_shifts.py:my_shifts_tab` | The volunteer's upcoming assigned shifts, with acknowledgment |
| Proctor Station | proctor / staff | `admin_tabs/admin_schedule.py:admin_schedule_page` | Race/schedule workflow — lifecycle buttons + seed rolls; `can_crud=is_staff` (proctors get transition-only, no create/edit) |

### My Availability (`pages/volunteer_tabs/availability.py`)

`availability_tab()` — the volunteer counterpart of the home My-Availability tab. Identical window-row + effective-graph UI (login required); persists through `VolunteerAvailabilityService.set_windows`.

### My Shifts (`pages/volunteer_tabs/my_shifts.py`)

`my_shifts_tab()` — a `@ui.refreshable` list of upcoming assignments from `VolunteerScheduleService.assignments_for_user(user, upcoming_after=now)`. Each card shows the position/label, the shift's Eastern start→end, and either an "Acknowledged" badge or an **Acknowledge** button calling `service.acknowledge(assignment_id, user)`.

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
| [`admin_racetime.py`](../../pages/admin_tabs/admin_racetime.py) | Racetime | Reusable race-room profile CRUD (`SYNC_ADMIN`/STAFF) via `RaceRoomProfileService`; the bots themselves are platform-managed on `/platform` |
| [`admin_challonge.py`](../../pages/admin_tabs/admin_challonge.py) | Challonge | Manage the shared Challonge connection and per-tournament bracket sync |
| [`admin_discord_roles.py`](../../pages/admin_tabs/admin_discord_roles.py) | Discord Roles | Map Discord roles to application roles for sign-in role sync |
| [`admin_webhooks.py`](../../pages/admin_tabs/admin_webhooks.py) | Webhooks | Staff-managed outbound webhooks: add/edit (URL, event multiselect, active), regenerate secret, recent deliveries, delete — see [../features/webhooks.md](../features/webhooks.md) |
| [`admin_equipment.py`](../../pages/admin_tabs/admin_equipment.py) | Equipment | Asset CRUD, checkout/checkin, and QR-page links |
| [`admin_feedback.py`](../../pages/admin_tabs/admin_feedback.py) | Feedback | Review queue for user-submitted feedback |
| [`admin_system_config.py`](../../pages/admin_tabs/admin_system_config.py) | Settings | System configuration: event window, concurrency limits, tournament hours, Discord sync guild |

### Admin schedule (`pages/admin_tabs/admin_schedule.py`)

`admin_schedule_page(can_crud: bool = True)` — the operational heart of the app: a `MatchTableView` over `Match.all()` with `admin_controls=True`. Columns: ID, Tournament, Scheduled At, State, Players, Commentators, Trackers, Stage, Seed. All lifecycle handlers call `MatchScheduleService` with the current user as `actor`, catch `PermissionError` (negative notify) and `ValueError` (warning notify), and refresh just the affected row via `table_view.update_row_by_id`.

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

On-site-only controls are hidden for racetime.gg tournaments (`Tournament.is_racetime_enabled`): the display row carries an `is_racetime` flag, and the slot templates replace the **Check In** button with a muted "racetime.gg" note and drop the **Assign stations** button when it is set — the race room drives the lifecycle. The services enforce the same rule (`seat_match` / `assign_stations` raise `ValueError`), so the guard holds for API callers too.

Seed generation suppresses the notification when the service reports a generation "already in progress" (the row refresh clears the button spinner either way) and downgrades "already been generated" to a warning. The tab also registers a `ui.on('selected_tab', ...)` listener that refreshes the table when the event reports `'Schedule'`.

### Admin users (`pages/admin_tabs/admin_users.py`)

`admin_users_page()` (Staff-only by tab visibility) — user management.

- A `UserTableView` with the toolbar suppressed (`show_toolbar=False`); the page renders its own row with **Add User** (opens `AdminUserDialog`) and a refresh button.
- Columns: Username, Display Name, Pronouns, Challonge (linked account, `-` when unlinked), Roles.
- A filter card with a multi-select over the three global `Role` values plus two pseudo-filters, `_tournament_admin` and `_crew_coordinator`. `get_query()` composes the queryset: global roles via `roles__role__in`, the pseudo-filters via `admin_tournaments__isnull=False` / `crew_coordinated_tournaments__isnull=False`, finished with `.distinct()`.
- Username clicks open `AdminUserDialog` for that user (wired inside `UserTableView`).

### Admin settings (`pages/admin_tabs/admin_settings.py`)

Two tab functions live in this module.

**`admin_tournaments_page()`** — `TournamentTableView` over `Tournament.all()`:

- Columns: Name, Description, Seed Generator, Active, Players/Match, Avg Match Duration, Max Match Duration, Staff Administered, Player Count (the ID column is hidden).
- **Add Tournament** renders only when `AuthService.is_staff(actor)` and opens `TournamentDialog`; name clicks edit, player-count clicks open `TournamentPlayersDialog`.
- Listens for `selected_tab == 'Tournaments'` to refresh.

**`admin_stream_rooms_page()`** — a hand-rolled `ui.table` (not a shared table view):

- Rows from `StreamRoomRepository.get_all()`: ID, Name, Stream URL (rendered as a link), Active (icon).
- **Add Stream Room** renders only when `AuthService.can_manage_stream_rooms(actor)`; ID links and the mobile-card edit button emit an `edit` event that opens `StreamRoomEditDialog` (create or edit), refreshing the table on submit.
- Mobile grid mode via `:grid="Quasar.Screen.lt.md"` with a custom `item` card slot (name, active badge, edit button, stream URL).

### Admin triforce texts (`pages/admin_tabs/triforce_texts.py`)

`admin_triforce_texts_page()` — moderation queue for triforce-text submissions.

- Staff see all active tournaments; non-staff see only active tournaments they administer (queried directly via `Tournament.filter(is_active=True, admins__id=actor.id)`); users administering none get an explanatory message instead of the queue.
- Filters: tournament select and status select (Pending / Approved / Rejected / All; default Pending).
- Each submission card shows the monospace text, the author (stored `author` or the submitting user's preferred name), a status badge, **Approve** / **Reject** buttons (disabled when already in that state), and a delete button guarded by `ConfirmationDialog`.
- The list is a `@ui.refreshable` section re-rendered after every moderation action.
- Services: `TriforceTextService.list_for_moderation`, `.moderate(text_id, approved, actor)`, `.delete(text_id, actor)`.

### Admin volunteer roster (`pages/admin_tabs/admin_volunteer_roster.py`)

`admin_volunteer_roster_page()` — the "Vol. Roster" tab (refuses unless `AuthService.can_manage_volunteers(actor)`).

- A `ui.table` (grid-card mode on small screens) of the assignable volunteer pool (`VolunteerProfileService.assignable_volunteers`): Name, Opted In (check/cancel icon from `opted_in_user_ids`), Qualifications (position-name chips from `VolunteerQualificationService.list_all_qualifications`), declared Availability windows (Eastern, from `VolunteerAvailabilityService.availability_map`), and a per-row manage button.
- The manage button emits `manage_volunteer`, opening `VolunteerProfileDialog` (active positions from `VolunteerPositionService.list_active`) to view availability and edit qualifications; the table reloads on submit and via a refresh button.

### Admin volunteers (`pages/admin_tabs/admin_volunteers.py`)

`admin_volunteers_page()` — the "Vol. Schedule" tab, the coordinator scheduling grid (refuses unless `AuthService.can_manage_volunteers(actor)`).

- A controls card: an event-day select, **Auto-fill from availability** (`VolunteerAutoscheduleService.generate_draft`), **Clear draft** (`clear_draft`), **Manage positions** (opens an inline positions dialog wiring `VolunteerPositionDialog`), and a guarded **Reset all volunteer data** dialog (type-to-confirm → `VolunteerScheduleService.reset_all_shifts`).
- A `@ui.refreshable` `grid()` renders one card per active position (`VolunteerPositionService.list_active`), each with **Generate standard shifts** and **Add shift** (→ `VolunteerShiftDialog`) and a shift card per shift (filled/needed badge, edit/delete, and an **Assign** picker dialog).
- The assign picker pulls the opted-in pool (`VolunteerProfileService.assignable_volunteers`) and per-volunteer availability badges (`VolunteerAvailabilityService.availability_map` / `covers`); assigning goes through `VolunteerScheduleService.assign` (surfacing returned warnings); assignment chips remove via `unassign`.

### Admin Challonge (`pages/admin_tabs/admin_challonge.py`)

`admin_challonge_page()` (Staff-only by tab visibility) — manages the shared Wizzrobe Challonge service-account connection.

- A `@ui.refreshable` connection card from `ChallongeService.get_connection_status` (configured / connected state, username, scopes, token expiry, monthly request quota usage) with **Connect** (→ `/challonge/connect`) / **Disconnect** for staff.
- A `@ui.refreshable` "Linked tournaments" list (`Tournament.filter(challonge_tournament_id__isnull=False)`) with last-synced timestamps and a per-tournament **Sync** button (`ChallongeService.sync_bracket(..., force=True)`).

### Admin Discord roles (`pages/admin_tabs/admin_discord_roles.py`)

`admin_discord_roles_page()` (Staff-only by tab visibility) — Discord-role → app-role mappings for sign-in role sync.

- Requires a configured sync guild (`SystemConfigService.get_discord_sync_guild_id`); otherwise points the admin at the Settings tab.
- A hand-rolled `ui.table` of mappings (`DiscordRoleMappingService.list_mappings`), each with a delete button (`remove_mapping`). **Add Mapping** (gated on `AuthService.can_grant_roles`) opens a dialog whose Discord-role select is populated from `DiscordService.list_guild_roles`, persisting via `add_mapping`.
- Registers a `ui.on('selected_tab', ...)` listener that refreshes when the event reports `'Discord Roles'`.

### Admin equipment (`pages/admin_tabs/admin_equipment.py`)

`admin_equipment_page()` — full asset management (Equipment Manager / Staff by tab visibility).

- A `@ui.refreshable` `ui.table` of all assets (`EquipmentService.list_assets` + `open_loans_by_equipment_id`): #, Name, Owner, Status badge, current holder, with grid-card mode on small screens.
- Per-row buttons: **Check out** / **Check in** (`open_checkout` with `can_manage=True` / `quick_checkin`), **Open asset page** (→ `/equipment/{id}`), **Edit** (`EquipmentDialog`), and **Delete** (guarded by `ConfirmationDialog` → `EquipmentService.delete_asset`). **Add Asset** opens `EquipmentDialog` in create mode.

### Admin feedback (`pages/admin_tabs/admin_feedback.py`)

`admin_feedback_page()` (Staff-only by tab visibility) — review queue for user feedback.

- A `@ui.refreshable` `ui.table` of recent submissions (`FeedbackService.list_recent`): submitted time, user, category, message, page URL, and a status badge.
- A **Mark reviewed** button per pending row calls `FeedbackService.mark_reviewed(actor, id)`.

### Admin system configuration (`pages/admin_tabs/admin_system_config.py`)

`admin_system_config_page()` — the "Settings" tab (Staff-only edit; `AuthService.is_staff` gates the Save button).

- Reads/writes via `SystemConfigService` keyed constants: event start/end dates, max concurrent players, max concurrent stages, volunteer reminder lead minutes, per-day tournament hours, and the Discord sync guild id.
- Date fields use a calendar-popup helper; per-day tournament hours render an Open/Close time pair per event day; the Discord-server select is populated from `DiscordService.list_guilds`. **Save** validates and persists each key through `SystemConfigService.set_raw` / `set_tournament_hours`.

## Reports subsystem (`pages/admin_tabs/reports/`)

Behavior doc: [../features/admin-reports.md](../features/admin-reports.md). Data aggregation lives in `ReportsService`, `AuditService`, and `SystemConfigService` (see [services.md](services.md)); the UI layer here is read-only.

### Dispatch (`reports/__init__.py`)

`_REPORT_HANDLERS` maps the `report` query param to a page coroutine; `reports_page(report=None, **params)` is the tab entry point. An unknown or missing `report` renders the dashboard; otherwise the handler receives all forwarded query params (each handler swallows extras via `**_unused`).

| `report=` | Handler | Params consumed |
|---|---|---|
| _(none)_ | `dashboard.dashboard_page` | — |
| `insights` | `insights.insights_page` | `start`, `end`, `bucket`, `tournament_id` |
| `capacity` | `capacity.capacity_page` | `start`, `end`, `tournament_id`, `focus` |
| `match_ops` | `match_ops.match_ops_page` | `start`, `end`, `tournament_id`, `state` |
| `crew` | `crew.crew_page` | `start`, `end`, `tournament_id`, `user_id`, `approval` |
| `stream_rooms` | `stream_rooms.stream_rooms_page` | `start`, `end`, `tournament_id`, `stream_room_id` |
| `volunteers` | `volunteers.volunteers_page` | `start`, `end` |
| `audit` | `audit.audit_page` | `start`, `end`, `user_id`, `action`, `page` |

The `insights` report is the longitudinal counterpart to the point-in-time snapshots: it buckets crew participation, volunteer hours, tournament health, and admin activity by week or month over an arbitrary range (backed by `AnalyticsService`). Its `bucket` param (`week`/`month`) is threaded through `admin.py`'s page signature alongside the other report filters, and it defaults to a trailing 90-day window rather than the event window, since a single event weekend collapses to one bucket.

### URL-driven state and CSV export

Reports hold no client-side state. Every filter widget's change handler calls `navigate_with_params(report=..., **filters)`, which rebuilds an `/admin/reports?...` URL and triggers a full page reload — the back button and shareable links work for free. Date ranges default to the configured event window (`SystemConfigService.get_event_window()`) when not in the URL (the `insights` report defaults to a trailing 90-day window instead).

CSV export (`csv_export_button`) downloads the currently rendered rows using `rows_to_csv_bytes` / `timestamped_filename` from [`application/utils/csv_export.py`](../../application/utils/csv_export.py) — UTF-8 with BOM, formula-injection prefixes escaped, hidden columns skipped.

### Shared helpers (`reports/shared.py`)

| Helper | Purpose |
|---|---|
| `REPORT_KEYS` | Tuple of the five report keys |
| `reports_url(report=None, **params)` | Build `/admin/reports[?report=…]` URLs; drops empty params, ISO-formats dates |
| `parse_date(value)` | Lenient `YYYY-MM-DD` parsing; `None` on garbage |
| `parse_int(value)` | Lenient int parsing; `None` on garbage |
| `eastern_bounds(start_d, end_d)` | Eastern date range → half-open aware datetime bounds (end clamped ≥ start) |
| `default_date_range(start_param, end_param)` | Use the URL dates if both parse, else `SystemConfigService.get_event_window()` |
| `report_page_shell(title, back_to_dashboard=True)` | Context manager: page container, "← Reports" back link, title, separator |
| `date_range_filter(default_start, default_end, on_change)` | Start/End inputs with calendar popups; fires `on_change(start, end)` on either change |
| `tournament_filter(current_id, on_change)` | Tournament select with an "All tournaments" (`0`) option, from `TournamentService.get_all_tournaments()` |
| `csv_export_button(filename_prefix, columns_provider, rows_provider, label='Export CSV')` | Download button; notifies on failure |
| `navigate_with_params(report=None, **params)` | `ui.navigate.to(reports_url(...))` — the reload-based filter mechanism |
| `schedule(coro_fn)` | `background_tasks.create(coro_fn())` shim for sync event handlers |

### Dashboard (`reports/dashboard.py`)

`dashboard_page()` — the landing view, scoped to the configured event window. Gathers `generate_capacity_forecast`, `match_operations`, `crew_coverage`, `stream_room_utilization`, and `SystemConfigService.get_max_concurrent_stages()` concurrently with `asyncio.gather`, then renders:

- Four KPI cards (`_kpi_card`): peak players vs capacity (red when over), peak stages used vs max stages, match counts (total / in flight / finished), and stream-candidate crew coverage percent (green ≥ 80%, with covered/total subtitle).
- One clickable card per entry in the `REPORT_CARDS` list (`_report_card`), each with an "Open report →" link built by `reports_url`.

### Capacity (`reports/capacity.py`)

`capacity_page(start, end, tournament_id, focus)` — concurrent-player forecast from `ReportsService.generate_capacity_forecast`.

- Filter card: date range, tournament select, plus shortcut buttons — "Whole event" and one button per event day.
- An ECharts line chart: active players (filled), on-stream players, and a dashed capacity line, with dataZoom slider and toolbox. A `focus` ISO timestamp (parsed by `_parse_focus`) pre-zooms to a ±2-hour window around that instant.
- "Top 5 peak times" from `ReportsService.peak_times`, each with an **Inspect** link that reloads with `focus` set.
- When focused: a table of matches active at that instant (`ReportsService.matches_active_at`).
- "Forecast data": the raw per-interval table (time, active players, on-stream players, match IDs) with CSV export.

### Match operations (`reports/match_ops.py`)

`match_ops_page(start, end, tournament_id, state)` — operational metrics from `ReportsService.match_operations`.

- Filters: date range, tournament, and a State select (`All` / `Scheduled` / `Checked In` / `In Progress` / `Finished`); the state filter is applied client-side to the detail rows.
- "Per-tournament aggregates" table: matches, started, finished, avg start delay, avg duration, expected duration, on-time %.
- "Matches" detail table: per-match start delay, duration, confirmation lag, stream room, player count — with CSV export.

### Crew (`reports/crew.py`)

`crew_page(start, end, tournament_id, user_id, approval)` — from `ReportsService.crew_coverage`. See [../features/crew-management.md](../features/crew-management.md).

- Filters: date range, tournament, an Approval select (`All` / `Approved only` / `Pending only`, applied client-side), and a "Clear user filter" button when `user_id` is active.
- "Coverage by match" table: approved/total commentators and trackers, stream-candidate flag, and a GAP marker — with CSV export.
- "Contribution by person" table: signups, approvals, percentages (`_ratio_pct`), hours covered — with CSV export. Clicking a row reloads with that person's `user_id`, filtering both tables.

### Stream rooms (`reports/stream_rooms.py`)

`stream_rooms_page(start, end, tournament_id, stream_room_id)` — from `ReportsService.stream_room_utilization`.

- A stacked horizontal ECharts bar of scheduled vs gap hours per room (`_render_utilization_chart`).
- A per-room summary table (matches, scheduled hours, gap hours, back-to-back <15 min count) whose title includes the unplaced-stream-candidate count — with CSV export. Clicking a row drills into that room via `stream_room_id`.
- When drilled in: the room's match list with scheduled time and window start/end.

### Volunteers (`reports/volunteers.py`)

`volunteers_page(start, end)` — volunteer coverage over a date range from `VolunteerScheduleService.coverage`.

- Filters: date range only (navigates with `report='volunteers'`).
- An "Understaffed shifts" summary card (count of understaffed shifts and total open slots), then an "All shifts" table (position, shift label, start, filled/needed, OK/Understaffed status) — with CSV export.

### Audit (`reports/audit.py`)

`audit_page(start, end, user_id, action, page)` — server-side paginated viewer over `AuditService.count_logs` / `list_logs` (`PAGE_SIZE = 50`). See [../features/audit-logging.md](../features/audit-logging.md).

- Filters: date range, an "Action contains" text input (applied on blur/Enter), and a row-click user filter with a clear button.
- `_parse_details(raw)` pretty-prints JSON details and passes legacy plain-text rows through unchanged; the Details cell renders a `q-expansion-item` with the full JSON when present (truncated to 200 chars as the label).
- CSV exports the current page only; Previous/Next pager buttons navigate with the `page` param (enabled state computed from total pages).

## Dialog catalog (`theme/dialog/`)

All dialogs follow the same shape: a `ui.dialog` + `.dialog-card`, a title row with a close button, a body, and an action row; most submit on Enter via a `keydown` handler and report errors with `ui.notify` (`PermissionError` → negative, `ValueError` → warning/negative). [`theme/dialog/__init__.py`](../../theme/dialog/__init__.py) re-exports `ApproveCrewDialog`, `CheckoutDialog` (plus the `open_checkout` / `quick_checkin` helpers), `ConfirmationDialog`, `EquipmentDialog`, `FeedbackDialog`, `MatchResultDialog`, `SendMessageDialog`, `StationAssignmentDialog`, `TournamentDialog`, `UserDialog`, and `AdminUserDialog`; the rest are imported by module path.

| File | Class(es) | Purpose | Opened from |
|---|---|---|---|
| [`match_dialog.py`](../../theme/dialog/match_dialog.py) | `BaseMatchDialog`, `AdminMatchDialog`, `UserMatchDialog` | Create/edit matches | Admin schedule; home Schedule & Player tabs |
| [`confirmation_dialog.py`](../../theme/dialog/confirmation_dialog.py) | `ConfirmationDialog` | Generic confirm/cancel | Start/Confirm actions, crew signup/undo, match/triforce-text/equipment/shift deletes |
| [`approve_crew_dialog.py`](../../theme/dialog/approve_crew_dialog.py) | `ApproveCrewDialog` | Toggle commentator/tracker approval | Crew name click in admin match table |
| [`match_result_dialog.py`](../../theme/dialog/match_result_dialog.py) | `MatchResultDialog` | Record the winner when finishing | Admin schedule Finish button |
| [`station_assignment_dialog.py`](../../theme/dialog/station_assignment_dialog.py) | `StationAssignmentDialog` | Assign stations to players | Admin schedule Check In flow & players-column button |
| [`stream_room_dialog.py`](../../theme/dialog/stream_room_dialog.py) | `StreamRoomDialog` | Assign a match to a stage + stream-candidate flag | Admin schedule Stage column |
| [`stream_room_edit_dialog.py`](../../theme/dialog/stream_room_edit_dialog.py) | `StreamRoomEditDialog` | Create/edit a `StreamRoom` | Admin Stream Rooms tab |
| [`tournament_edit_dialog.py`](../../theme/dialog/tournament_edit_dialog.py) | `TournamentDialog` | Create/edit a tournament | Admin Tournaments tab |
| [`tournament_players_dialog.py`](../../theme/dialog/tournament_players_dialog.py) | `TournamentPlayersDialog` | Read-only enrolled-player list | Player-count link in tournament table |
| [`send_message_dialog.py`](../../theme/dialog/send_message_dialog.py) | `SendMessageDialog` | Send a Discord DM to a user | `AdminUserDialog` "Send Message" |
| [`user_edit_dialog.py`](../../theme/dialog/user_edit_dialog.py) | `BaseUserDialog`, `UserDialog`, `AdminUserDialog` | Profile / full user editing | Admin Users tab; player-name click in match tables |
| [`challonge_schedule_dialog.py`](../../theme/dialog/challonge_schedule_dialog.py) | `ChallongeScheduleDialog` | Schedule a Challonge bracket matchup (date/time only) | Home Player tab "Schedule" button |
| [`volunteer_position_dialog.py`](../../theme/dialog/volunteer_position_dialog.py) | `VolunteerPositionDialog` | Create/edit a `VolunteerPosition` | Admin Volunteers "Manage positions" |
| [`volunteer_shift_dialog.py`](../../theme/dialog/volunteer_shift_dialog.py) | `VolunteerShiftDialog` | Create/edit a `VolunteerShift` | Admin Volunteers Add/Edit shift |
| [`checkout_dialog.py`](../../theme/dialog/checkout_dialog.py) | `CheckoutDialog` (+ `open_checkout` / `quick_checkin` helpers) | Check an asset out (borrower picker for managers) | Equipment tab, admin Equipment tab, asset detail page |
| [`equipment_dialog.py`](../../theme/dialog/equipment_dialog.py) | `EquipmentDialog` | Create (optionally bulk) / edit a lending asset | Admin Equipment tab; asset detail Edit |
| [`feedback_dialog.py`](../../theme/dialog/feedback_dialog.py) | `FeedbackDialog` | Submit feedback, capturing the current page URL | Footer "Feedback" button (any page, logged in) |

The simpler dialogs in brief:

- **`ConfirmationDialog(message, on_confirm, confirm_text, cancel_text)`** — sync `open()`; the confirm button (styled negative) runs the caller's `on_confirm`, which usually closes the dialog itself.
- **`ApproveCrewDialog(crew_member, crew_type, on_approve)`** — shows the crew member's name and an Approved checkbox; saves through `CrewService.update_crew_approval` and invokes `on_approve` (the match table passes a row-refresh).
- **`StreamRoomDialog(match, on_submit)`** — subclasses `BaseMatchDialog` to reuse its service/repository wiring; a Stage select (with a `(None)` option) and a stream-candidate checkbox, saved via `MatchService.assign_stage` and `set_stream_candidate` (the latter only when changed).
- **`StreamRoomEditDialog(stream_room=None, on_submit)`** — Room Name, Stream URL, Active; calls `StreamRoomService.create_stream_room` / `update_stream_room`.
- **`TournamentDialog(tournament=None, on_submit)`** — Name (required; Create/Save button bound to it), Description, Seed Generator (options from `SeedGenerationService.AVAILABLE_RANDOMIZERS` — see [seed-generation.md](seed-generation.md)), Seed Preset, Bracket URL, Rules URL, Tournament Format, Avg/Max Match Duration, Players per Match, Team Size, Staff Administered, Active; calls `TournamentService.create_tournament` / `update_tournament`. When the actor can manage sync (`AuthService.can_manage_sync`), a **Racetime** section appears — Racetime Bot (only categories the tenant is authorized for), Race Room Profile, Default Goal, Open Room (min before), Auto-create rooms, Require racetime link.
- **`TournamentNotificationDialog(user, on_close)`** — one level select per active tournament (None / Streamed only / Streamed & Candidates / All matches); Save upserts each via `TournamentNotificationService.upsert_preference`.
- **`TournamentPlayersDialog(tournament)`** — read-only list from `TournamentRepository.get_enrolled_players` (name + Discord ID).
- **`SendMessageDialog(user, send_callback=None)`** — a required message textarea (Send disabled while blank); default callback sends via `DiscordService.send_dm`.
- **`ChallongeScheduleDialog(challonge_match, actor, opponent_name, on_submit)`** — tournament and both players come from the bracket, so it only collects a Date/Time (pre-filled with a `MatchSuggestionService.suggest_match_time` suggestion); submits via `ChallongeService.schedule_challonge_match`, reusing the match-request + acknowledgment flow.
- **`VolunteerPositionDialog(position=None, on_submit)`** — Name, Description, Display Order, Active, and optional shift-length / stagger-interval minutes; calls `VolunteerPositionService.create` / `update`.
- **`VolunteerShiftDialog(shift=None, position=None, default_day=None, on_submit)`** — Position select, start/end date+time (end date auto-tracks the start until edited), Label, Slots needed, Notes; calls `VolunteerScheduleService.create_shift` / `update_shift`.
- **`CheckoutDialog(actor, equipment_id, on_done)`** — a borrower select (defaulting to the actor) for managers/staff to check an asset out on someone's behalf via `EquipmentService.checkout`. The `open_checkout(actor, equipment_id, can_manage, on_done)` helper shows this dialog when `can_manage`, otherwise self-checks-out immediately; `quick_checkin(...)` checks an asset back in.
- **`EquipmentDialog(actor, equipment=None, on_saved)`** — Name (required), Description, manager-only Private notes, and Owner (Wizzrobe or a user); create mode adds a Quantity field for bulk creation. Calls `EquipmentService.create_asset` / `bulk_create_assets` / `update_asset`.
- **`FeedbackDialog(user)`** — a Category select and required Message textarea; on submit it reads `window.location` via `ui.run_javascript` and records the feedback through `FeedbackService.submit`.

### Match dialogs (`theme/dialog/match_dialog.py`)

**`BaseMatchDialog(match=None, on_submit=None)`** holds shared state and helpers:

- Captures `match.updated_at` at construction for optimistic-concurrency checks on save.
- `_get_default_values()` — tournament/date/time/comment/stage defaults from the match, or "now" in Eastern for create mode.
- `_render_date_time_inputs()` — Date and Time inputs, each with a calendar/clock popup menu bound to the input.
- `_render_clear_buttons()` — five outline buttons (Clear Check In / Started / Finish / Confirmed / Seed) that set `_clear_*` flags consumed by `MatchService.update_match`; each is disabled when the corresponding timestamp (or seed relation) is already empty.
- `_render_watch_switch(user)` — a watch toggle wired to `MatchWatcherService.watch` / `unwatch`, reverting itself on `ValueError` ([../features/match-watcher.md](../features/match-watcher.md)).
- `_confirm_delete` / `_delete_match` — `ConfirmationDialog` guard around `MatchService.delete_match(match_id, actor)`.

**`AdminMatchDialog(match=None, on_submit=None)`** — full create/edit form ("Create Match" / "Edit Match"). Fields:

- Tournament (required), Stage (with `(None)` option).
- Players multi-select — restricted to players enrolled in the selected tournament (via `TournamentRepository.get_enrolled_players_by_tournament_id`) unless the "Choose any players" checkbox is set; options reload whenever the tournament or checkbox changes.
- Commentators and Trackers multi-selects (all users).
- Date / Time (required), Comment textarea, Stream-candidate checkbox.
- Edit mode adds the clear buttons and a read-only Player Acknowledgments list (check/pending icons, timestamps, `(auto)` markers) from `MatchAcknowledgmentRepository.list_for_match` — see [../features/match-acknowledgment.md](../features/match-acknowledgment.md).
- Edit mode also shows a **Racetime Room** section when the match's tournament has a racetime bot: the room's slug + status if one exists, else (for STAFF/`SYNC_ADMIN`) a "Create racetime room" button calling `RaceRoomService.manual_create_room` — a manual open independent of the tournament's auto-open toggle.

On save it validates required fields, runs `MatchService.ensure_players_enrolled`, then:

- *Edit*: re-fetches the match and aborts with a warning if `updated_at` changed since the dialog opened (another admin edited it); otherwise calls `MatchService.update_match(...)` with the clear flags, plus `assign_stage` and/or `set_stream_candidate` only when those values changed.
- *Create*: `MatchService.create_match(...)`, then `assign_stage` if a stage was chosen.

A Delete button appears in edit mode. `on_submit` receives the match (edit) or nothing (create) so callers can refresh a row or the whole table.

**`UserMatchDialog(discord_id, match=None, on_submit=None)`** — the player-facing variant ("Submit Match" / "Edit Match"):

- Tournament options default to the player's enrolled tournaments; a "Show all tournaments" checkbox widens the list, and submitting auto-enrolls the player in the chosen tournament if needed.
- A single required Opponent select lists the other enrolled players of the chosen tournament (the player themself excluded).
- Edit mode adds the watch switch, clear buttons, and Delete; players enrolled in no tournaments get a short-circuit message instead of the form.
- Submission uses the same `updated_at` concurrency check, then `MatchService.update_match` (with empty commentator/tracker lists) or `MatchService.submit_match_request` for new requests, with the player as `actor`.

### User dialogs (`theme/dialog/user_edit_dialog.py`)

**`BaseUserDialog(user=None, on_submit=None)`** captures `user.updated_at` for concurrency checks and provides tournament-enrollment helpers built on `TournamentRepository` and `UserService.update_user_tournament_registrations` / `manage_tournament_enrollments`.

**`UserDialog`** — self-edit ("Edit Profile"): read-only Username, Display Name, Pronouns, and a tournament multi-select; saves via `UserService.update_user_profile` (with `check_concurrency=True` and the captured `initial_updated_at`) plus the enrollment sync. No role editing.

**`AdminUserDialog`** — staff-only: it verifies `AuthService.is_staff(actor)` on open and refuses otherwise. Add/edit form ("Add User" / "Edit User"):

- Username (required and editable only on create; read-only on edit), Display Name, Pronouns, Active checkbox, Discord ID (create only). On edit, when the Challonge integration is configured, the dialog manages the user's Challonge link: a linked user gets an editable "Challonge username" field (with the account id as a hint) saved via `ChallongeService.set_player_username`; an unlinked user gets "Challonge account id" + optional username inputs that Staff can fill to link manually via `ChallongeService.link_player_manually` (the id must be unique across users).
- A Roles multi-select over the global `Role` enum, and three tournament multi-selects: Player enrollments, "Tournament Admin of", "Crew Coordinator of".
- On save it diffs each selection against current state: `UserService.grant_role` / `revoke_role` per added/removed role, and `TournamentService.add_admin` / `remove_admin` and `add_crew_coordinator` / `remove_crew_coordinator` per membership change. Create mode goes through `UserService.create_user` first, then applies the same syncs to the new user.
- Edit mode adds a **Send Message** button opening `SendMessageDialog`. See [../features/role-based-auth.md](../features/role-based-auth.md).

### Station assignment & match result

**`StationAssignmentDialog(match, on_submit)`** — fetches tournament/players, shows one Station text input per player (max 50 chars, pre-filled from `assigned_station`, blank clears), and submits the full `{player_id: station}` mapping to `MatchService.assign_stations(match_id, assignments, actor)`.

**`MatchResultDialog(match, on_submit)`** — shows tournament and scheduled-time context and a required Winner select over the match players (Submit Results disabled until chosen); submits to `MatchService.record_match_result(match_id, winner_id, actor)`, then notifies with the winner's name. Used by the Finish action, whose callback then calls `MatchScheduleService.finish_match`.

## Table views (`theme/tables/`)

All three views share a pattern: the constructor takes `columns` (NiceGUI/Quasar column dicts) and `get_query` (a callable returning a queryset or row provider), builds a `ui.table` with custom cell slots, switches to card-grid rendering on small screens via `:grid="Quasar.Screen.lt.md"` with a hand-built `item` slot, and exposes `refresh()` plus `update_row_by_id()` for single-row updates. Tables start empty; callers trigger the first `refresh()` (usually via `background_tasks.create`). Pagination changes re-trigger a refresh.

### `MatchTableView` (`theme/tables/match.py`)

The largest UI component, used by the home Schedule and Player tabs and the admin Schedule tab.

**Constructor flags**: `admin_controls` (admin slots and lifecycle buttons), `can_crud` (edit/approve affordances within admin mode), `extra_slots` (caller-supplied cell templates), `submit_match_callback` (renders the Create Match / Request Match button), `player_discord_id` (scopes data to one player), and per-action callbacks `on_edit`, `on_generate_seed`, `on_seat`, `on_start`, `on_finish`, `on_confirm`, `on_edit_stream_room`, `on_assign_stations` — slots and event handlers are registered only for callbacks that are provided.

**Filters** — a card with three multi-selects (Tournament, Stage, State) and a refresh button. Tournament/stage options load asynchronously from `MatchDisplayService.get_tournaments_for_filter` / `get_stream_rooms_for_filter` (the view holds a `MatchDisplayService` as `self.display_service`). Filter values persist per user in `app.storage.user` (`tournament_filter`, `stream_room_filter`, `state_filter`); state defaults to Scheduled + Checked In + Started. Admin mode adds an **Auto-refresh** checkbox driving a cancellable 5-second `_auto_refresh_loop` (`background_tasks.create` + `asyncio.sleep`).

**Data flow** — `refresh()` calls `MatchDisplayService.get_matches_for_display(tournament_ids, stream_room_ids, only_upcoming=False, user_discord_id)`, applies the state filter client-side, then merges per-row `_watching` flags from `MatchWatcherService.list_watched_match_ids`. `update_row_by_id(match_id)` re-fetches one row via `MatchDisplayService.get_match_for_display` (deleting the row if the match is gone, preserving `_watching`); `delete_row_by_id` removes a row from the UI only.

**Cell rendering** — the players cell shows acknowledgment icons (green check / orange clock with timestamp tooltips, `(auto)` markers) and bolds the winner; admin mode also shows each player's station in italics. Commentator/tracker cells color names by approval (green approved / orange pending) with the same acknowledgment icons. The admin Seed column shows a Generate button (with client-side `_generating_seed` spinner state) when the tournament has a seed generator and no seed exists; existing seeds render as truncated links. The admin State column renders the next lifecycle action per state — Scheduled → Check In, Checked In → Start, Started → Finish, Finished → Confirm — each with the previous transition's timestamp; Confirmed renders an icon + timestamp. The Stage column shows an Assign button for unassigned matches and an amber "candidate" badge for stream candidates.

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
| `acknowledge_commentator` / `acknowledge_tracker` | Crew member's own Acknowledge button | `CrewService.acknowledge_crew_assignment` (crew id read from the row payload) |
| `toggle_watch` | Watch column button (logged-in) | `MatchWatcherService.watch` / `unwatch`, flips `_watching` locally |
| `update:pagination` | Quasar pagination | full `refresh()` |

Crew signup/undo and acknowledge buttons only render for the logged-in user's own entries; the templates compare row data against the user's `discord_id`, interpolated into the slot HTML at build time. See [../features/crew-management.md](../features/crew-management.md) and [../features/match-acknowledgment.md](../features/match-acknowledgment.md).

**Grid mode** — `render_grid_slot()` generates a label/value card per row from the column list (JS field descriptors built in Python), re-implementing the ID link, acknowledgment icons, crew signup/acknowledge buttons, lifecycle state buttons, seed generation/links, watch toggle, and stage assignment for mobile, with admin/crud behavior baked in via template interpolation.

### `TournamentTableView` (`theme/tables/tournament.py`)

- Toolbar: optional **Add Tournament** button (when `submit_tournament_callback` is provided) plus a refresh button.
- Slots: clickable Name (emits `edit_tournament` → `TournamentDialog`), clickable Player Count (emits `show_players` → `TournamentPlayersDialog`), truncated Description with tooltip, icon rendering for Active (check/cancel) and Staff Administered (badge/person).
- `refresh()` orders by name and builds rows from `get_query().prefetch_related('players')` (player count computed from the prefetched relation); `update_row_by_id` refreshes one row.
- A static mobile `item` slot mirrors all columns. Editing does not auto-refresh the row afterwards.

### `UserTableView` (`theme/tables/user.py`)

- Optional toolbar (`show_toolbar=False` lets the caller render its own, as the admin Users tab does; otherwise an Add User button when `submit_user_callback` is set, plus refresh).
- Slots: clickable Username (emits `edit_user` → `AdminUserDialog`), Active icon, truncated Discord ID, linked Challonge account (`-` when unlinked), and Roles rendered as `q-chip`s split from a comma-separated string.
- `refresh()` orders by username and prefetches `roles`, `admin_tournaments`, `crew_coordinated_tournaments`; `_format_user_row` title-cases role names and appends `TA(n)` / `CC(n)` markers for tournament-scoped roles. Timestamps format through `format_eastern_display`.
- `render_grid_slot()` generates the mobile card from the column list; `update_row_by_id` refreshes a single row.

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

2. **A bespoke `item` slot** with an inline `:grid="Quasar.Screen.lt.md"` prop — reserved for the four purpose-built family tables (match / user / tournament / equipment), whose cards are too custom for the generic helper (see `match_grid.render_grid_slot`).

A table that legitimately must stay a table on mobile (a narrow 2-column reference) opts out with a `# mobile-grid: exempt` comment on the `ui.table` line. The generic card styling is `.wiz-grid-card` (the card counterpart of `.wiz-table`), which carries its surface from a wrapping `<q-card bordered flat>`.

## Static assets & styling (`static/`)

`static/` is served at `/static` (uncached in development — see [NiceGUI integration](#nicegui-integration-frontendpy)). Beyond the stylesheet it holds the PWA assets ([`manifest.webmanifest`](../../static/manifest.webmanifest), `icons/`, `fonts/`), [`sw.js`](../../static/sw.js) (served from the site root `/sw.js`; a no-cache pass-through worker that satisfies Chrome's installability requirement and renders Web Push messages on browsers without Declarative Web Push — see [../features/web-push.md](../features/web-push.md)), and [`js/web-push.js`](../../static/js/web-push.js) (client-side subscribe/unsubscribe helpers for the Profile tab's Device Notifications card).

The main stylesheet, [`static/css/styles.css`](../../static/css/styles.css), is loaded by `BaseLayout.render()`. Pages otherwise style via Quasar utility classes and inline styles in slot templates. The stylesheet is organized into class families rather than per-page rules:

- **Layout containers** — `.page-container` (1400px), `.page-container-narrow` (1200px), `.page-container-wide` (1600px), `.full-width`, `.full-width-column`, and flex/spacing utilities (`.flex-center`, `.flex-1`, `.row-spacing`, `.mb-1`, `.ml-1`).
- **Headers & text** — `.page-title`, `.section-title`, `.subsection-title`, `.large-title`, `.header-row`; semantic text classes (`.text-muted`, `.text-success`, `.text-warning`, `.text-error`, `.text-link`, `.table-link`, `.italic-note`).
- **Cards, forms, dialogs, buttons** — `.card-*` paddings/widths; `.input-full-width`, `.input-label`, `.required-legend`, `.form-grid`; `.dialog-card` (`min(700px, 90vw)`, scrollable, 85vh max) and `.dialog-card-small` with a ≤768px media query; `.button-row`, `.separator-spacing`, icon color helpers, and the fixed-position `.refresh-button`.
- **Timeline (On Air)** — `.timeline-*`, `.room-*`, `.match-card` / `.match-time` / `.match-badge` and friends, `.empty-state`, and the status border classes `.border-left-green/orange/gray/blue`.
- **Tables** — parallel `.match-table*`, `.user-table*`, `.tournament-table*`, and `.equipment-table*` families: bordered cells, centered headers, zebra striping, a `.wrap` inner-cell class for wrapping long name lists, and `*-table-container` width fixes. `.match-filters-card` and `.match-filter-*` style the filter strip.
- **Dark mode** — explicit overrides under both `.body--dark` and `.q-dark` for the table families, the `*-grid-card` mobile cards, `.match-filters-card`, and `.footer-dark-override` (light-mode cell backgrounds are hard-coded, so each themed component carries a dark counterpart).
- **Reports** — `.chart-container`, `.chart-height`, `.control-width` size the ECharts panels and filter selects.

## NiceGUI patterns

The canonical rules live in [`CLAUDE.md`](../../CLAUDE.md) ("NiceGUI Patterns") — in short: spawn async work from sync handlers with `background_tasks.create()` (never `asyncio.create_task`), capture `context.client` (not the nonexistent `Client.current`) before a background task that calls `ui.notify` and re-enter it with the client context manager (see `MatchTableView`'s acknowledge handlers), use `@ui.refreshable` for dynamic sections (the triforce-text lists), never block the shared event loop, and keep per-user state in `app.storage.user` rather than module-level variables (the match table's filter persistence is the worked example).
