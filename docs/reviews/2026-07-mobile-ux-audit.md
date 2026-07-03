# Mobile UX Audit — July 2026

> **Status: P0 + P1 implemented and verified (see [Implementation results](#implementation-results-p0--p1) at the end).** The findings below are the original audit; the roadmap items marked P0/P1 have since been built and browser-verified.

**Goal:** make SGL On Site feel like a first-class SaaS product on phones — closer to a native app than a shrunk-down website. Target devices: iOS Safari and Android Chrome.

**Method:** the running app (dev boot + `scripts/seed_dev.py` fixtures) was driven with Playwright at real phone viewports — 390×844 (iPhone 14/15), 360×800 (small Android) — with `isMobile`, touch, and mobile user agents, as three personas (anonymous, `player_one`, `staff_user`). Every page/tab was screenshotted full-page, and each page was programmatically measured for horizontal overflow, tap targets below 44×44 px, and inputs below 16 px font size. Dialogs (match edit, match request, feedback), the drawer, and error pages were exercised by tap.

Reproduce with `scripts/ui_smoke.js` and a config that sets `"viewport": {"width": 390, "height": 844}` (see the `ui-validation` skill).

---

## Executive summary

The app is in **good structural shape for mobile** — far better than most desktop-first admin tools:

- **Zero horizontal overflow on any audited page** at 390 px and 360 px. Nothing requires sideways scrolling.
- All four table families switch to **grid cards below Quasar's `lt.md`** breakpoint; the drawer auto-hides below 600 px behind a burger; dialogs cap at `90vw`.
- Tab deep links (`?tab=`), dark mode with system-follow, realtime match-row updates (`theme/realtime.py`), self-hosted preloaded fonts, `prefers-reduced-motion` support, and visible focus rings are all already in place.

What keeps it feeling like a **website in a phone browser** rather than an app:

1. **It isn't installable** — no manifest, icons, or theme color. "Add to Home Screen" produces a generic bookmark that opens with full browser chrome.
2. **iOS zooms on every input focus** — all inputs render at 14 px; iOS Safari auto-zooms any input under 16 px and stays zoomed. This is the single loudest "not an app" tell.
3. **Nearly every control misses the 44 pt / 48 dp touch minimum** — header buttons are 36 px tall, filter-chip removers 18×18, icon actions 24–32 px, link targets ~17 px tall.
4. **Navigation is drawer-only** — every tab switch costs two taps through a burger menu; native apps put primary destinations in a persistent bottom bar.
5. **Dialogs are floating desktop cards** — action buttons scroll out of view (observed on Submit Match); phones expect full-screen sheets with pinned actions.
6. **The match card (the core mobile surface) is a label/value dump** — it renders every table column, including empty ones, so barely 1.5 matches fit per screen.

All findings below are grouped by theme with evidence and file references, followed by a prioritized roadmap.

---

## A. App shell & installability (the "actual app" gap)

| # | Finding | Evidence / location |
|---|---|---|
| A1 | **No PWA manifest, no app icons, no `theme-color`, no `apple-touch-icon`, no service worker.** The app cannot be installed as a standalone app; the browser toolbar is always present; the task-switcher card and home-screen icon are generic. | No matches for `manifest`/`theme-color`/`touch-icon` anywhere in the repo; `theme/base.py:render_chrome()` injects only fonts + CSS. |
| A2 | **Viewport meta is the bare NiceGUI default** (`width=device-width, initial-scale=1`). No `viewport-fit=cover`, so in standalone mode or landscape on notched iPhones the brand header does not extend into the safe area. | Measured on every page. |
| A3 | **No safe-area handling.** `.sgl-header` (`static/css/styles.css:319`) and the fixed footer use no `env(safe-area-inset-*)` padding — content will collide with the home indicator / notch once A1/A2 land. | `static/css/styles.css:319`, `:1105`. |
| A4 | `background-attachment: fixed` on the body radial gradient (`styles.css:202-210`) is ignored or janky on iOS Safari — the "lit canvas" effect silently degrades. | `static/css/styles.css:202`. |

**Recommendation:** ship a `static/manifest.webmanifest` (name, icons 192/512 + maskable, `display: standalone`, `theme_color` = `--sgl-gold-deep` / `background_color` = `--page-bg`), add `<link rel="manifest">`, `<meta name="theme-color">` (one per light/dark via `media`), `apple-touch-icon`, and extend the viewport meta with `viewport-fit=cover` + `env()` padding on header/footer. A minimal service worker (even network-only) is what makes Android show "Install app" instead of "Add to Home screen". This is a day of work and transforms the perceived product.

## B. Global touch ergonomics

| # | Finding | Evidence |
|---|---|---|
| B1 | **Every text input renders at 14 px → iOS auto-zoom on focus.** Counted per page: 13 on admin Settings, 11 in the match dialog, 8 in Request Match, 5 in Feedback, 3 on every page with filters. | `metrics.json`, all three personas. |
| B2 | **Tap targets below 44×44 everywhere.** Header buttons 56–58×**36**; `Log in as` 73×**32**; filter-chip remove icons **18×18**; report links `Open report →` 90×**21**; match-ID/username links ~**17 px** tall; Vol. Schedule tab has **78** sub-minimum controls (pencil/trash/assign per shift). | `metrics.json` samples; Apple HIG 44 pt, Material 48 dp. |
| B3 | **Icon-only actions rely on hover tooltips that don't exist on touch**: logout, dark-mode toggle, watch eye, refresh, station-assign, shift edit/delete. First-time phone users get no affordance labels. | `theme/base.py:119,132`; `theme/tables/*`; `pages/admin_tabs/admin_volunteers.py`. |
| B4 | **The fixed footer permanently spends ~48 px of a ~660–780 px viewport** on copyright + a Feedback button, on every page. | `theme/base.py:_render_footer()`; visible in every screenshot. |
| B5 | Base body font is 14 px (Quasar default) — small for phone reading distance; 15–16 px reads better. | `metrics.json` `bodyFontSize`. |

**Recommendation:** one mobile CSS block fixes most of B: under `@media (max-width: 600px)` set `.q-field__native, .q-field input, .q-field textarea { font-size: 16px }`, give `.q-btn` a `min-height: 44px` (and `.q-btn--dense` 40 px), enlarge chip-remove icons, and bump body to 15–16 px. Move Feedback into the drawer on mobile and hide the footer (or reduce it to safe-area padding). For B3, prefer labeled buttons or `aria-label` + visible text on mobile grid cards.

## C. Navigation & information architecture

| # | Finding | Evidence |
|---|---|---|
| C1 | **Drawer-only navigation.** All primary destinations (Schedule, On Air, Player, Availability…) hide behind the burger; switching tabs is always ≥2 taps and the current location is invisible while reading a page. Native/SaaS mobile apps put 4–5 top destinations in a **bottom tab bar** in the thumb zone. | `theme/base.py:_render_drawer()`; drawer screenshot. |
| C2 | **Report filters trigger full page reloads** (`navigate_with_params` → `ui.navigate.to`) — every filter change re-renders the whole page; on a phone connection this feels like 2005. (The shareable-URL property is worth keeping — history `replace` + partial refresh would preserve it.) | `pages/admin_tabs/reports/shared.py`. |
| C3 | **No swipe gestures.** Tab panels are programmatically switched; Quasar `q-tab-panels` supports `swipeable` and panels already render eagerly, so horizontal swipe between tabs is nearly free. | `theme/base.py:_render_tab_panels()`. |
| C4 | **No pull-to-refresh**; refreshing is a small icon button inside the filter card (or a floating `.refresh-button` that overlaps the footer's Feedback button on On Air). Realtime updates (matches) reduce the need, but list pages without realtime still need a natural refresh gesture. | `static/css/styles.css:911`; On Air screenshots. |
| C5 | Page titles at `2em` display serif wrap to two lines on 390 px ("Schedule & Crew Signup", "Edit Your Information") and, with the always-open filter card, push **all actual content below the first screen** on the schedule tabs. | home/admin schedule screenshots; `.page-title` `styles.css:442`. |

**Recommendation:** the single biggest native-feel win is a **mobile bottom nav** (Quasar `q-tabs` in a bottom bar, shown `lt.md` only) carrying Schedule / On Air / Player / More, with the drawer demoted to secondary/admin destinations. Add `swipeable` panels, `clamp()`-scale the titles, and collapse filters into a chip row that expands on tap (show active-filter count).

## D. Screen-by-screen findings

### Schedule tabs (home + admin) — the core mobile surface
- **The grid card renders every column as a `label: value` row, including empty ones** ("Commentators: —", "Generated Seed: -", "Watch:") and repeats the tournament name on every card; a card is ~9 rows tall, so ~1.5 matches fit per screen. A purpose-built card (time + players as the headline, state chip top-right, tournament as a caption, one action row, empty fields omitted) would triple information density and look designed rather than generated. `theme/tables/match_grid.py:56-62`.
- The label column is fixed at `col-4` — a third of the card is spent on field names.
- Lifecycle buttons (Check In / Start / Finish), Sign Up buttons, and the watch eye are `size=sm`/dense — below touch minimums (B2).
- Filters: three multi-selects stacked vertically consume most of the first viewport (C5). Filter values *do* persist per user — good.

### On Air
- The header controls wrap awkwardly at 390 px: the previous-day chevron ends up orphaned above the two-line date title, with next/Today below (`pages/home_tabs/stage_timeline.py:31-58`). A compact single row (`‹ Thu, Jul 02 ›` + Today) fits a phone.
- The floating refresh FAB (`.refresh-button`, fixed bottom-right) overlaps the footer's Feedback button.
- The room/match cards themselves read well on mobile — best-in-app mobile surface today.

### Profile
- Autosave ("All changes are saved automatically") is exactly the right mobile pattern — keep it. Note the `beforeunload` guard is unreliable on iOS Safari, so autosave is also the *only* effective protection there (`pages/home_tabs/player_edit_info.py:18-24,181`).
- Display Name / Pronouns render as two cramped columns at 390 px; stack them.

### My Availability
- The effective-availability graph's hour labels wrap ("24:00" lands on its own line) and day bars are small but legible. Window-editor rows (Date/Start/End/Status/delete) will wrap heavily at 390 px once windows exist.

### Volunteer hub / Vol. Schedule (coordinator)
- Functional but dense: 78 sub-44 px controls in the shift grid (edit/delete/assign icon buttons ~24–32 px). Acceptable short-term as a desktop-first coordinator tool; flag for a later pass (larger buttons, or a per-shift action sheet).

### Reports
- Charts render at phone width with dataZoom; usable. Data tables paginate (25/row page) without overflow. The reload-per-filter-change (C2) is the main pain. `control-width` (400 px fixed) on some report selects exceeds a 360 px viewport minus padding — it happens to be contained today but is fragile (`styles.css:884`).

### Login & errors
- Production login is a Discord OAuth redirect — fine on mobile. (The dev-only mock picker's table clips its Discord ID column at 360 px and its "LOG IN AS" buttons are 32 px tall; low priority, dev-only.)
- Themed 404 renders cleanly at phone width with a proper Back-to-home action.

## E. Dialogs & forms

| # | Finding | Evidence |
|---|---|---|
| E1 | **Dialog action buttons scroll out of view.** Dialogs are `min(700px, 90vw)` cards capped at `85vh` with actions at the bottom of the scroll content — on Submit Match at 390×844 the Cancel/Submit row is clipped at the viewport edge; a user filling the form top-down must scroll to discover it. | Screenshot `player-request-match`; `.dialog-card` `styles.css:537-542`. |
| E2 | **Dialogs should be full-screen sheets on phones.** No dialog uses Quasar's `maximized` prop; a floating card with a dimmed backdrop is a desktop idiom. | `grep maximized theme/dialog/` → none. |
| E3 | **Date/time entry is a desktop pattern**: `YYYY-MM-DD` / 24-hour text inputs with popup calendar/clock menus. Phones have superior native pickers; the popup calendar is cramped at 390 px and the text inputs bring up a full text keyboard. | `theme/dialog/match_dialog.py:_render_date_time_inputs()`; also admin Settings (13 such inputs). |
| E4 | **No `inputmode`, `enterkeyhint`, or `autocomplete` attributes anywhere** — numeric fields (durations, quantities, Discord IDs) raise the full text keyboard. | repo-wide grep. |
| E5 | The Feedback dialog is the mobile high-point: short form, visible actions, required-state on the message field. Use it as the template. | Screenshot `player-feedback`. |

**Recommendation:** add a mobile branch to the shared dialog shape: `maximized` below `sm`, header with close on the left + primary action on the right (sheet pattern), and a sticky action bar (`position: sticky; bottom: 0` inside `.dialog-card`). Switch date/time fields to native `<input type="date|time">` on touch devices (NiceGUI `ui.input(...).props('type=date')`) or Quasar's dialog-mode pickers.

## F. Connectivity & performance behavior

- **WebSocket lifecycle:** NiceGUI drops its socket when the phone locks or the app is backgrounded; returning users see the "Connection lost / trying to reconnect" overlay for a beat. Test `reconnect_timeout` tuning on real devices; consider styling the reconnect overlay to match the brand so the moment feels controlled. This is inherent to NiceGUI and worth an explicit device pass.
- **Eager tab rendering:** every tab's content (queries included) builds at page load (`theme/base.py:_render_tab_panels()`). The home page runs up to 7 tabs' worth of service calls before first paint — noticeable on cell networks. Lazy-render on first activation would cut initial payload and DB load.
- **Realtime updates** for match rows are already pushed to connected clients — a genuine app-like strength; extend the pattern to the On Air timeline rather than its manual refresh FAB.
- Fonts are self-hosted, subset, and preloaded — good LCP hygiene. (A2's `background-attachment: fixed` note also lives in this bucket.)

---

## Measurement appendix (390×844, staff persona unless noted)

| Page | Horiz. overflow | Tap targets <44px | Inputs <16px |
|---|---|---|---|
| Home Schedule | 0 | 19 | 3 |
| On Air | 0 | 12 | 1 |
| Profile | 0 | 6 | 3 |
| Player dashboard | 0 | 14 (player) | 3 |
| Request Match dialog | 0 | 18 | 8 |
| My Availability | 0 | 6 | 0 |
| Equipment | 0 | 4 | 0 |
| Admin Schedule | 0 | 24 | 3 |
| Admin match dialog | 0 | 36 | 11 |
| Admin Users | 0 | 13 | 1 |
| Admin Reports / Capacity | 0 | 10 / 19 | 0 / 4 |
| Vol. Schedule | 0 | **78** | 1 |
| Admin Settings | 0 | 7 | **13** |
| Volunteer hub | 0 | 24 | 3 |
| 404 | 0 | 5 | 0 |
| Anonymous home (360×800) | 0 | 15 | 3 |

Viewport meta on all pages: `width=device-width, initial-scale=1`. Body font: 14 px.

---

## Prioritized roadmap

**P0 — the "feels like an app" quartet (small, high-leverage):**
1. Mobile CSS block: 16 px inputs (kills iOS zoom), 44 px minimum button height, 15–16 px body text (B1/B2/B5).
2. PWA shell: manifest + icons + `theme-color` + `apple-touch-icon` + `viewport-fit=cover` + safe-area padding (A1–A3).
3. Bottom tab bar for primary destinations below `md`; drawer becomes secondary nav (C1).
4. Full-screen dialogs on phones with pinned action bar (E1/E2).

**P1 — core-surface redesign:**
5. Purpose-built match card for grid mode: headline time+players, state chip, no empty rows, labeled actions (D-Schedule).
6. Collapse filters into an expandable chip row; scale page titles with `clamp()` (C5).
7. Native date/time inputs + `inputmode` on numeric fields (E3/E4).
8. Move Feedback into the drawer on mobile; drop the fixed footer (B4).
9. Swipeable tab panels (C3).

**P2 — polish & robustness:**
10. Lazy tab rendering (F); realtime for On Air instead of the refresh FAB; pull-to-refresh on list pages (C4).
11. Reports: filter changes without full reload; keep URL state via history replace (C2).
12. On Air header compaction; availability axis-label fix; Vol. Schedule touch pass (D).
13. Branded reconnect overlay + real-device WebSocket lifecycle testing (F).
14. Real-device QA matrix: iPhone SE (375×667, the tightest), iPhone 15, Pixel 8, plus iPad portrait (768 px — sits *above* `sm` and below `md`, so it gets grid cards + hidden drawer; verify it looks intentional).

---

*Audit artifacts (screenshots + per-page metrics) were generated with Playwright against the seeded dev app; regenerate via the `ui-validation` skill with a mobile `viewport` in the smoke config.*

---

## Implementation results (P0 + P1)

The P0 and P1 roadmap items were implemented across six file-disjoint workstreams and browser-verified at 390×844 (light + dark) and 360×800. Each ships as its own commit.

**What shipped**

- **Ergonomics (P0):** all inputs render at 16px on phones (iOS focus-zoom eliminated), buttons meet the 44px touch floor (dense/round included), body text at 15px, page titles `clamp()`-scaled so they no longer wrap. — `static/css/styles.css`
- **PWA shell (P0):** `manifest.webmanifest` (standalone, phoenix theme/background colors), generated triforce icons (192 / 512 / maskable / apple-touch), a cache-free service worker served at root scope, `theme-color`/`apple-touch-icon` head tags, and `viewport-fit=cover` + `env(safe-area-inset-*)` padding. Android now offers "Install"; iOS "Add to Home Screen" launches standalone. — `static/manifest.webmanifest`, `static/icons/*`, `static/sw.js`, `scripts/generate_pwa_icons.py`, `frontend.py`, `theme/base.py`
- **Bottom navigation (P0):** a bottom tab bar (first four tabs + **More**) below 1024px in the thumb zone; the drawer is demoted to secondary nav and now carries Feedback; tab panels are swipeable. Drawer/bottom-tap/swipe all converge on one handler that keeps the `?tab=` URL and active state in sync. — `theme/base.py`
- **Dialog sheets (P0):** every dialog maximizes to a full-screen sheet on phones with a **sticky action bar** (Cancel/Save always reachable — fixes the Submit-Match clip), plus native `type=date`/`type=time` pickers and `inputmode=numeric` on numeric fields. — `theme/dialog/*`
- **Match card (P1):** the mobile grid card was rebuilt — headline time + state chip, players line, tournament caption, detail rows that omit empty fields, one labeled action row — roughly tripling cards-per-screen. Removed a hardcoded white background that broke dark mode. — `theme/tables/match_grid.py`
- **Collapsible filters (P1):** filters collapse behind a toggle with an active-count badge below 1024px; desktop unchanged. — `theme/tables/match.py`

**Verified metrics (390×844, staff/player/anon) — before → after**

| Page | iOS-zoom inputs | Sub-44px tap targets |
|---|---|---|
| Home Schedule | 3 → **0** | 19 → **2** |
| On Air | 1 → **0** | 12 → **0** |
| Admin Schedule | 3 → **0** | 24 → **5** |
| Admin match dialog | 11 → **0** | 36 → **5** |
| Admin Settings | 13 → **0** | 7 → **2** |

Horizontal overflow remained 0 everywhere. The residual sub-44px targets are inline text links (`#id`, "Stage 2") and two icon actions on the admin Settings page — inline text is an accepted exception; the Settings icons are a documented follow-up. Dark mode was re-verified (no white cards, opaque sticky bars). `ruff` clean; full pytest suite green (803 passed).

**Deferred to P2** (unchanged from the roadmap above): admin Settings' remaining date/time inputs, Vol. Schedule touch pass, lazy tab rendering, pull-to-refresh, reports-without-reload, branded reconnect overlay, and the real-device QA matrix (iPhone SE / 15, Pixel 8, iPad portrait).
