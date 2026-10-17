/*
 * Layout-stability gate: a page must hold still when it updates.
 *
 * In the 2026-10-16 demo, buttons moved under people's fingers: the Match
 * Schedule board jumped sideways every time the Needs you list reloaded, and
 * boards reshuffled when someone else checked a match in. Neither is visible to
 * pytest or to a screenshot, because the page looks right before and after; it
 * is wrong only for the frames in between. docs/style-guide.md#hold-still has
 * the rule this enforces.
 *
 * For every target, at desktop and phone width, it loads the page, lets it
 * settle, then asks the server to redraw every live section of the page with
 * the same data (theme/layout_probe.py, installed when the app runs with
 * WIZ_LAYOUT_PROBE=1). Nothing changed, so nothing may move: the browser's own
 * layout-shift entries (the ones behind Core Web Vitals' CLS) are collected
 * across the redraw, and any element that moves more than 2px fails the page.
 * That catches a section that blanks while it reloads (the Needs you bug), a
 * spinner swapped in for content, and a placeholder of the wrong height.
 *
 * Config "live" steps then change real data from a second session, as another
 * staff member would, and fail if what the viewer already sees moves. Each step
 * is a REST call: { "method": "POST", "path": "/api/...", "body": {...} },
 * sent with the seeded bearer token named by "liveToken".
 *
 * Prereqs: the app booted with WIZ_LAYOUT_PROBE=1 and seeded (see the
 * ui-validation skill), Playwright resolvable as for ui_a11y_scan.js.
 *
 * Usage:
 *   node scripts/ui_layout_shift.js scripts/ui_layout_shift_ci.json
 *
 * Config, beyond ui_smoke.js's fields:
 *   "viewports": [ { "name": "desktop", "viewport": {...} }, "Pixel 7" ],
 *   "ignore": [ { "selector": ".some-class", "target": "admin-schedule", "why": "..." } ]
 * An ignore entry matches a moved element by CSS selector (the element or any
 * ancestor); `target` narrows it to one page. Every entry must say why.
 */
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const MOVE_LIMIT = 2;

function findChrome(explicit) {
  if (explicit && fs.existsSync(explicit)) return explicit;
  try {
    const hit = execSync('find /opt/pw-browsers -type f -name chrome 2>/dev/null | head -n1').toString().trim();
    if (hit) return hit;
  } catch (_) {}
  return undefined;
}

function profiles(list) {
  return (list || [{ name: 'desktop', viewport: { width: 1440, height: 900 } }, 'Pixel 7']).map((d) => {
    if (typeof d === 'string') {
      if (!devices[d]) throw new Error(`unknown device ${d}`);
      const { defaultBrowserType, ...profile } = devices[d];
      return { name: d, profile: { isMobile: true, hasTouch: true, ...profile } };
    }
    const { name, ...profile } = d;
    return { name, profile };
  });
}

// Runs in every page before its own scripts.
function startRecording() {
  window.__wizShifts = [];
  window.__wizLastShift = 0;
  window.__wizLastMutation = 0;
  new MutationObserver(() => { window.__wizLastMutation = performance.now(); })
    .observe(document, { subtree: true, childList: true, characterData: true });
  const describe = (node) => {
    if (!node || node.nodeType !== 1) return node && node.parentElement ? describe(node.parentElement) : '(text)';
    const cls = typeof node.className === 'string' ? node.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
    const text = (node.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return `<${node.tagName.toLowerCase()}${cls ? '.' + cls : ''}> "${text}"`;
  };
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      window.__wizLastShift = performance.now();
      for (const s of entry.sources || []) {
        const dx = s.currentRect.x - s.previousRect.x;
        const dy = s.currentRect.y - s.previousRect.y;
        const dh = s.currentRect.height - s.previousRect.height;
        window.__wizShifts.push({ node: s.node, el: describe(s.node), dx, dy, dh, value: entry.value });
      }
    }
  }).observe({ type: 'layout-shift', buffered: false });
}

function collect(ignoreSelectors) {
  const out = [];
  for (const s of window.__wizShifts || []) {
    if (Math.max(Math.abs(s.dx), Math.abs(s.dy)) <= 2) continue;
    const el = s.node && s.node.nodeType === 1 ? s.node : s.node && s.node.parentElement;
    if (el && ignoreSelectors.some((sel) => el.closest(sel))) continue;
    out.push({ el: s.el, dx: Math.round(s.dx), dy: Math.round(s.dy), dh: Math.round(s.dh) });
  }
  window.__wizShifts = [];
  return out;
}

(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const baseUrl = cfg.baseUrl || 'http://127.0.0.1:8000';
  const loginAs = cfg.loginAs || 'staff_user';
  const tprefix = cfg.tenant ? `/t/${cfg.tenant}` : '';
  const withTenant = (p) => (!tprefix || p.startsWith('/t/') || p.startsWith('/api/') ? p : tprefix + p);
  const ignore = cfg.ignore || [];
  const outDir = path.join(cfg.outDir || '/tmp/ui-smoke', 'layout-shift');
  fs.mkdirSync(outDir, { recursive: true });
  const targets = (cfg.targets || []).filter((t) => !process.env.LAYOUT_ONLY || t.name === process.env.LAYOUT_ONLY);
  const concurrency = Math.max(1, +(process.env.LAYOUT_CONCURRENCY || cfg.concurrency || 4));

  const browser = await chromium.launch({ executablePath: findChrome(cfg.chrome), args: ['--no-sandbox'] });
  const loginCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const loginPage = await loginCtx.newPage();
  await loginPage.goto(`${baseUrl}${withTenant('/login')}`, { waitUntil: 'networkidle' });
  await loginPage.waitForTimeout(800);
  await loginPage.locator('tr, .wiz-grid-card', { hasText: loginAs }).first().getByRole('button', { name: 'Log in as' }).click();
  await loginPage.waitForTimeout(1500);
  const storageState = await loginCtx.storageState();
  await loginCtx.close();

  async function live(step) {
    const res = await fetch(`${baseUrl}${withTenant(step.path)}`, {
      method: step.method || 'POST',
      headers: { Authorization: `Bearer ${cfg.liveToken}`, 'Content-Type': 'application/json' },
      body: step.body ? JSON.stringify(step.body) : undefined,
    });
    if (!res.ok) throw new Error(`${step.method || 'POST'} ${step.path} -> ${res.status} ${(await res.text()).slice(0, 200)}`);
  }

  async function scan(page, vp, t) {
    const label = `${vp.name} ${t.name}`;
    const failures = [];
    const selectors = ignore.filter((i) => !i.target || i.target === t.name).map((i) => i.selector);
    try {
      await page.goto(`${baseUrl}${withTenant(t.path)}`, { waitUntil: 'networkidle' });
    } catch (e) {
      return { label, failures: [`[${label}] navigation failed: ${e.message.split('\n')[0]}`] };
    }
    // Settled means two seconds with nothing moving: a page still filling in
    // its first data would otherwise be blamed on the redraw.
    await page.waitForTimeout(t.settle || 2000);
    try {
      await page.waitForFunction(() => performance.now() - (window.__wizLastShift || 0) > 2000, null, { timeout: 15000, polling: 200 });
      // A board still waiting on its first rows has not moved yet either, so
      // also wait for the DOM to stop changing; a page with a ticking clock
      // never does, which is fine.
      await page.waitForFunction(() => performance.now() - (window.__wizLastMutation || 0) > 1500, null, { timeout: 8000, polling: 200 }).catch(() => {});
    } catch (_) {
      failures.push(`[${label}] never stopped moving after it loaded`);
    }
    if (t.scrollTo) await page.locator(t.scrollTo).first().scrollIntoViewIfNeeded().catch(() => {});
    await page.evaluate(() => { window.__wizShifts = []; });

    const before = await page.evaluate(() => window.__wizProbeDone || 0);
    await page.evaluate((event) => window.emitEvent(event, {}), 'wiz_layout_probe');
    try {
      await page.waitForFunction((n) => (window.__wizProbeDone || 0) > n, before, { timeout: 15000 });
    } catch (_) {
      failures.push(`[${label}] the redraw never finished (is the app running with WIZ_LAYOUT_PROBE=1?)`);
    }
    await page.waitForTimeout(800);
    const redraw = await page.evaluate(collect, selectors);
    for (const s of redraw) failures.push(`[${label}] redraw moved ${s.el} by ${s.dx},${s.dy}px (height ${s.dh >= 0 ? '+' : ''}${s.dh})`);

    for (const step of t.live || []) {
      try {
        await live(step);
      } catch (e) {
        failures.push(`[${label}] live step failed: ${e.message}`);
        break;
      }
      await page.waitForTimeout(1500);
      const moved = await page.evaluate(collect, selectors);
      for (const s of moved) failures.push(`[${label}] "${step.label || step.path}" moved ${s.el} by ${s.dx},${s.dy}px`);
    }
    if (failures.length) await page.screenshot({ path: path.join(outDir, `${label.replace(/\s+/g, '-')}.png`) });
    return { label, failures, summary: `moved=${failures.length}` };
  }

  const vps = profiles(cfg.viewports);
  // Live steps change shared data, so a page with steps runs alone, last.
  const jobs = vps.flatMap((vp) => targets.filter((t) => !t.live).map((t) => ({ vp, t })));
  const serial = vps.flatMap((vp) => targets.filter((t) => t.live).map((t) => ({ vp, t })));
  const results = [];
  let next = 0;
  async function worker(queue) {
    let ctx = null;
    let page = null;
    let key = null;
    try {
      while (next < queue.length) {
        const { vp, t } = queue[next++];
        if (vp.name !== key) {
          if (ctx) await ctx.close();
          ctx = await browser.newContext({ ...vp.profile, storageState });
          await ctx.addInitScript(startRecording);
          page = await ctx.newPage();
          key = vp.name;
        }
        const r = await scan(page, vp, t);
        results.push(r);
        console.log(`  [${r.label}] ${r.summary || 'failed'}`);
      }
    } finally {
      if (ctx) await ctx.close();
    }
  }
  const started = Date.now();
  await Promise.all(Array.from({ length: Math.min(concurrency, jobs.length) }, () => worker(jobs)));
  next = 0;
  if (serial.length) await worker(serial);
  await browser.close();

  const failures = results.flatMap((r) => r.failures);
  console.log(`scanned ${jobs.length + serial.length} page loads in ${Math.round((Date.now() - started) / 1000)}s`);
  console.log('=== layout shifts ===');
  console.log(failures.length ? failures.join('\n') : '(none)');
  if (failures.length) {
    console.log('\nSee docs/style-guide.md#hold-still for how to fix these.');
    process.exit(1);
  }
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
