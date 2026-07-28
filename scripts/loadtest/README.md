# Load-test harness

Reproduces the capacity measurements in
[docs/scaling-roadmap.md](../../docs/scaling-roadmap.md).

`ws_load.py` opens **real NiceGUI websockets** — it performs the same handshake
the bundled `nicegui.js` does (GET the page, scrape the `client_id` that render
minted, then connect socket.io with `implicit_handshake=true`). One virtual
client == one browser tab == one persistent websocket, so the connection count
means the same thing it means in production.

`profile_render.py` cProfiles page renders in-process (via `ASGITransport`, no
network, no new dependencies) to attribute the per-render CPU cost.

## Setup

```bash
bash scripts/setup_env.sh                    # Postgres + dev .env (once)
set -a && . ./.env && set +a
poetry run uvicorn main:app --workers 1 --log-level warning --port 8001 --host 127.0.0.1 &
poetry run python scripts/seed_dev.py
```

Use a **no-reload** server: `./start.sh dev` adds watchfiles overhead, and
`./start.sh prod` forces `ENVIRONMENT=production`, which refuses `MOCK_DISCORD`.

## Getting a session cookie

Login happens over the websocket (the mock picker emits a `login_as` event), so
the cookie has to come from a real browser session. Drive the mock login with
Playwright once, then reuse that cookie for every virtual client — they are
distinct NiceGUI clients regardless of sharing one identity:

```js
const { chromium } = require('playwright');   // NODE_PATH=/opt/node22/lib/node_modules
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await b.newContext(); const p = await ctx.newPage();
await p.goto('http://127.0.0.1:8001/t/default/login');
await p.locator('tr', { hasText: 'staff_user' }).first()
       .locator('button:has-text("Log in as")').click();
console.log((await ctx.cookies()).find(c => c.name === 'session').value);
```

Write it to `cookie.txt` as `session=<value>`.

## Running

```bash
# ramp must exceed the per-render CPU cost or renders queue past NiceGUI's
# 3-second page-response timeout and clients are torn down before connecting
poetry run python scripts/loadtest/ws_load.py \
    --n 500 --ramp 0.3 --hold 60 \
    --base http://127.0.0.1:8001 --prefix /t/default --path /t/default/ \
    --cookie-file cookie.txt

PYTHONPATH=. poetry run python scripts/loadtest/profile_render.py
```

Sample the server alongside a run — RSS, CPU (ticks/s ≈ % of one core), fds, and
`pg_stat_activity` — to separate "CPU-bound" from "waiting on the database".

## Interpreting

- **`Response for / not ready after 3.0 seconds`** in the server log means
  renders are queuing: admission-rate limited, not socket limited.
- **CPU ≈ wall time** over sequential renders means CPU-bound; the DB pool is not
  the constraint (check `pg_active` to confirm).
- Driver and server on one host understate server CPU headroom. Run them apart
  for a clean number.
