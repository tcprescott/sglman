---
name: ui-validation
description: >-
  Validate a NiceGUI presentation-layer change (pages/, theme/) by driving the
  real app in a headless browser — the only way to exercise client-side
  Vue/Quasar slot templates that the SQLite pytest suite and nicegui.testing
  cannot reach. Use after editing ui.table slots, dialogs, grids, or any
  @ui.page rendering, or whenever asked to "see it in a browser", screenshot a
  page, or confirm a UI change renders. Spins up Postgres + seeds data + logs in
  via MOCK_DISCORD + screenshots and reads back each page with Playwright.
---

# Browser validation loop

The service layer has 790+ SQLite tests, but `pages/` and `theme/` have **no**
automated coverage and their Vue/Quasar slot templates run **client-side** — a
bad `item.foo` in a `table.add_slot(...)` string renders blank in the browser
and is invisible to Python tests. This skill drives the running app so you can
*see* the result.

## One-time per environment

```bash
bash scripts/setup_env.sh
```

Installs/starts PostgreSQL 16, ensures `tzdata` **and the `US/Eastern` alias**
(the app calls `ZoneInfo('US/Eastern')`, which throws on minimal tzdata images),
creates the `wizzrobe` DB, runs `poetry install`, and writes a dev `.env`
(`MOCK_DISCORD=true`, generated `STORAGE_SECRET`). Idempotent. This is also the
script to paste into the "Setup script" field of a Claude Code cloud environment.

## Each validation run

1. **Boot** (background) and wait for readiness:
   ```bash
   nohup ./start.sh dev > /tmp/app.log 2>&1 &
   # wait until /tmp/app.log shows "Application startup complete"
   ```
   The FastAPI lifespan auto-applies Aerich migrations on first boot.

2. **Seed** baseline fixtures (idempotent — 7 users incl. `staff_user`,
   `proctor_user`, `sm_user`; a tournament; 4 matches across lifecycle states;
   plus crew signups, acknowledgments, watchers, equipment + loans, API tokens,
   feedback, triforce texts, Discord role mappings, player availability, and a
   Challonge bracket mirror):
   ```bash
   poetry run python scripts/seed_dev.py
   ```
   The seed now covers every model at least once. If your change needs a state
   the fixtures don't happen to hit, add rows through the UI or extend
   `scripts/seed_dev.py`.

3. **Drive** with the reusable Playwright harness. Write a small JSON config and
   run it with node's global Playwright (the pre-installed Chromium at
   `/opt/pw-browsers` is auto-detected; **never** run `playwright install`):
   ```bash
   cat > /tmp/smoke.json <<'JSON'
   {
     "loginAs": "staff_user",
     "tenant": "default",
     "outDir": "/tmp/ui-smoke",
     "targets": [
       { "name": "admin-table", "path": "/admin", "tab": "Schedule", "selector": ".match-table" },
       { "name": "home-table",  "path": "/",      "tab": "Schedule", "selector": ".match-table" }
     ]
   }
   JSON
   NODE_PATH=$(npm root -g) node scripts/ui_smoke.js /tmp/smoke.json
   ```
   For the mobile **grid** layout, add a target with `"viewport": {"width":470,"height":1100}`
   (set it at config top-level; the grid renders below Quasar's `lt.md` breakpoint).

4. **Inspect**: the harness prints each page's extracted text + any console/page
   errors and writes `*.png` to `outDir`. Open the screenshots with the Read
   tool. A blank cell where data should be, or a `console.error`, means a broken
   template. (One pre-existing `ui.image ... startsWith` console error is
   unrelated to table/dialog changes.)

## Multitenancy: pages live under `/t/<slug>`

The app is path-mode multitenant: every community's pages are served under
`/t/<slug>/…`. A bare `/admin` **404s** ("only available within a community")
and a bare `/` is the **community picker**, not a tenant home — so unprefixed
targets validate the wrong (or a missing) page. Set **`"tenant": "default"`**
(the dev slug seeded by `seed_dev.py`) at the config top level and the harness
prefixes both the mock login and every target path with `/t/<slug>`. Escape
hatches: a target whose `path` already starts with `/t/` is left as-is, and a
target marked `"platform": true` is never prefixed — use it for the bare `/`
picker or the `/platform` super-admin surface. Omit `tenant` to drive the bare
platform host.

**Multi-step flows the single-tab harness can't reach** (open a dialog → submit
→ assert the row updated; drill into a "Manage" detail → switch sub-tabs → click
an action). The stock harness does login → visit → click one tab → screenshot.
For richer interaction, write a one-off Playwright script in the scratchpad that
reuses the same login flow (`/t/<slug>/login` → click "Log in as") and drives
the buttons/dialogs directly. Note that a NiceGUI `@ui.refreshable` detail view
rebuilds on every mutation and **resets to its default sub-tab**, so re-select
the sub-tab after each action before asserting.

## Login note

`MOCK_DISCORD=true` replaces Discord OAuth with a user picker at `/login`
(tenant-prefixed to `/t/<slug>/login` when `tenant` is set); the harness clicks
"Log in as" in the row matching `loginAs`. The session cookie is browser-wide,
so one login carries across tenant and platform paths. Pick `staff_user` for
admin views, a plain `player_*` for the public/non-admin variants, and
`proctor_user` to exercise the admin-but-not-crud variant.

## Files

- `scripts/setup_env.sh` — environment prep (Postgres, tzdata, deps, `.env`).
- `scripts/ui_smoke.js` — config-driven Playwright harness (login → visit →
  screenshot → extract text → report errors). Honors `tenant` (`/t/<slug>`
  prefix) and per-target `platform: true`.
- `scripts/seed_dev.py` — baseline fixtures.
