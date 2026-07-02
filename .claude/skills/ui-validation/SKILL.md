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
creates the `sglman` DB, runs `poetry install`, and writes a dev `.env`
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
   `proctor_user`, `sm_user`; a tournament; 4 matches across lifecycle states):
   ```bash
   poetry run python scripts/seed_dev.py
   ```
   Seed data has no crew/acknowledgment rows — if your change touches those
   branches, add rows through the UI or a throwaway `Tortoise.init` script
   before driving.

3. **Drive** with the reusable Playwright harness. Write a small JSON config and
   run it with node's global Playwright (the pre-installed Chromium at
   `/opt/pw-browsers` is auto-detected; **never** run `playwright install`):
   ```bash
   cat > /tmp/smoke.json <<'JSON'
   {
     "loginAs": "staff_user",
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

## Login note

`MOCK_DISCORD=true` replaces Discord OAuth with a user picker at `/login`; the
harness clicks "Log in as" in the row matching `loginAs`. Pick `staff_user` for
admin views, a plain `player_*` for the public/non-admin variants, and
`proctor_user` to exercise the admin-but-not-crud variant.

## Files

- `scripts/setup_env.sh` — environment prep (Postgres, tzdata, deps, `.env`).
- `scripts/ui_smoke.js` — config-driven Playwright harness (login → visit →
  screenshot → extract text → report errors).
- `scripts/seed_dev.py` — baseline fixtures.
