/*
 * Reusable browser-validation harness for SGL On Site (MOCK_DISCORD mode).
 *
 * Drives the running app with Playwright: logs in via the mock user picker,
 * visits each target page (optionally clicking a Quasar tab), screenshots it,
 * extracts the text of a selector, and reports any console / page errors — the
 * only way to validate client-side Vue/Quasar slot templates that Python render
 * tests can't reach.
 *
 * Prereqs: `bash scripts/setup_env.sh`, then boot (`./start.sh dev`) and seed
 * (`poetry run python scripts/seed_dev.py`). See the `ui-validation` skill.
 *
 * Usage:
 *   NODE_PATH=$(npm root -g) node scripts/ui_smoke.js config.json
 *
 * config.json (all fields optional except targets):
 *   {
 *     "baseUrl": "http://127.0.0.1:8000",
 *     "loginAs": "staff_user",          // username in the mock picker
 *     "outDir":  "/tmp/ui-smoke",        // screenshots + text dumps land here
 *     "chrome":  "/opt/pw-browsers/.../chrome",  // auto-detected if omitted
 *     "targets": [
 *       { "name": "admin-schedule", "path": "/admin", "tab": "Schedule", "selector": ".match-table" }
 *     ]
 *   }
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function findChrome(explicit) {
  if (explicit && fs.existsSync(explicit)) return explicit;
  try {
    const hit = execSync(
      "find /opt/pw-browsers -type f -name chrome 2>/dev/null | head -n1",
    ).toString().trim();
    if (hit) return hit;
  } catch (_) {}
  return undefined; // let Playwright use its bundled browser
}

async function clickTab(page, name) {
  if (!name) return false;
  for (const s of [`[role="tab"]:has-text("${name}")`, `.q-tab:has-text("${name}")`,
                   `div.q-tab__label:has-text("${name}")`]) {
    const el = page.locator(s).first();
    if (await el.count()) { await el.click().catch(() => {}); return true; }
  }
  return false;
}

(async () => {
  const cfgPath = process.argv[2];
  const cfg = cfgPath ? JSON.parse(fs.readFileSync(cfgPath, 'utf8')) : {};
  const baseUrl = cfg.baseUrl || 'http://127.0.0.1:8000';
  const loginAs = cfg.loginAs || 'staff_user';
  const outDir = cfg.outDir || '/tmp/ui-smoke';
  const targets = cfg.targets || [{ name: 'home', path: '/', selector: 'body' }];
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch({
    executablePath: findChrome(cfg.chrome),
    args: ['--no-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: cfg.viewport || { width: 1500, height: 1100 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE.ERROR: ' + m.text().slice(0, 200)); });

  // Mock login: click "Log in as" in the row for `loginAs`.
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const row = page.locator('tr', { hasText: loginAs }).first();
  await row.getByRole('button', { name: 'Log in as' }).click();
  await page.waitForTimeout(1500);
  console.log(`logged in as ${loginAs} -> ${page.url()}`);

  for (const t of targets) {
    await page.goto(`${baseUrl}${t.path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    if (t.tab) console.log(`  [${t.name}] tab "${t.tab}" clicked: ${await clickTab(page, t.tab)}`);
    await page.waitForTimeout(1500);
    const shot = path.join(outDir, `${t.name}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    const text = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      return el ? el.innerText : `(selector ${sel} not found)`;
    }, t.selector || 'body');
    fs.writeFileSync(path.join(outDir, `${t.name}.txt`), text);
    console.log(`  [${t.name}] screenshot=${shot} textlen=${text.length}`);
    console.log(text.slice(0, 600));
    console.log('  ---');
  }

  console.log('=== console/page errors ===');
  console.log(errors.length ? errors.join('\n') : '(none)');
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
