/*
 * Accessibility and contrast gate for the running app (MOCK_DISCORD mode).
 *
 * Reads the same config as scripts/ui_smoke.js, logs in once per colour scheme,
 * and runs two checks on every target page, in light and in dark:
 *
 *   1. axe-core's WCAG 2.1 A/AA rules, minus `color-contrast`. Badges are
 *      tinted with an inset box-shadow (see `.q-badge` in styles.css) that axe
 *      cannot see, so its contrast rule reports every badge as a failure.
 *   2. A tint-aware contrast check in its place: it composites each text
 *      element's background layers, inset tints included, and fails text under
 *      4.5:1 (3:1 for large text).
 *
 * The 2026-10 style pass and accessibility audit found 59 grey captions at
 * 2.5:1, dark-mode reds at 2.8:1 and 531 unnamed icon buttons, all invisible
 * to the pytest suite. This is what keeps them from coming back.
 * docs/style-guide.md says what to do when it fails.
 *
 * With a "phone" block in the config it then makes a third pass at phone width
 * (390px by default) and fails any page whose layout breaks there: the page
 * scrolls sideways, an element runs past the screen or out of the card that
 * holds it, or text is cut off without an ellipsis. The 2026-10 phone sweep
 * found Settings fields 90px past their card and a whole family of these, none
 * of which a desktop-width scan can see.
 *
 * Prereqs: the app booted and seeded (see the ui-validation skill), Playwright
 * and axe-core resolvable (`npm install --no-save playwright@1.56.1
 * axe-core@4.10.3`, or NODE_PATH pointing at a global install).
 *
 * Usage:
 *   node scripts/ui_a11y_scan.js scripts/ui_smoke_ci.json
 *
 * Config fields it reads beyond ui_smoke.js's:
 *   "a11y": {
 *     "schemes": ["light", "dark"],
 *     "ignore": [ { "rule": "region", "target": "home-player", "why": "..." } ]
 *   }
 * An ignore entry matches an axe rule id or "contrast"; `target` (a target
 * name) narrows it to one page. Every entry must say why.
 *
 *   "phone": {
 *     "viewport": { "width": 390, "height": 844 },
 *     "schemes": ["light"],
 *     "ignore": [ { "selector": ".some-class", "target": "home-player", "why": "..." } ]
 *   }
 * A phone ignore entry matches an offending element by CSS selector (the
 * element or any ancestor); `target` narrows it to one page.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function findChrome(explicit) {
  if (explicit && fs.existsSync(explicit)) return explicit;
  try {
    const hit = execSync('find /opt/pw-browsers -type f -name chrome 2>/dev/null | head -n1').toString().trim();
    if (hit) return hit;
  } catch (_) {}
  return undefined;
}

function axeSource() {
  return fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
}

// Runs in the page. Returns text elements under the WCAG AA minimum.
function contrastCheck() {
  const parse = (s) => {
    let m = s.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    m = s.match(/color\(srgb ([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[ /]+/).filter(Boolean).map(Number);
      return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1];
    }
    return null;
  };
  const over = (top, bot) => [0, 1, 2].map((i) => top[i] * top[3] + bot[i] * (1 - top[3])).concat([1]);
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const ratio = (a, b) => { const x = lum(a); const y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // Background layers from the element outwards, stopping at the first opaque
  // one. A large inset box-shadow is a tint painted over the background.
  const layers = (el) => {
    const out = [];
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      const sh = s.boxShadow.match(/(rgba?\([^)]+\)|color\(srgb[^)]+\))[^,]*inset/);
      if (sh && /\d{3,}px/.test(s.boxShadow)) out.push(parse(sh[1]));
      const b = parse(s.backgroundColor);
      if (b && b[3] > 0) { out.push(b); if (b[3] >= 1) break; }
    }
    return out;
  };
  const bgOf = (el) => { let c = [255, 255, 255, 1]; for (const l of layers(el).reverse()) c = over(l, c); return c; };
  const res = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    if (el.closest('.wiz-sr-only, .wiz-skip-link, [aria-hidden="true"]')) continue;
    const txt = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').trim();
    if (!txt) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || +s.opacity === 0) continue;
    // WCAG 1.4.3 exempts inactive controls.
    if (el.closest('.q-field--disabled, [disabled], .disabled, .q-btn--disabled, [aria-disabled="true"]')) continue;
    const fg = parse(s.color);
    if (!fg) continue;
    const bg = bgOf(el);
    const r = ratio(fg[3] < 1 ? over(fg, bg) : fg, bg);
    const size = parseFloat(s.fontSize);
    const large = size >= 24 || (size >= 18.6 && +s.fontWeight >= 700);
    // An icon font's ligature is a graphic, held to 3:1 (WCAG 1.4.11).
    const icon = el.classList.contains('q-icon') || el.classList.contains('material-icons');
    if (r < (large || icon ? 3 : 4.5)) {
      const cls = typeof el.className === 'string' ? el.className : '';
      const key = cls + '|' + txt.slice(0, 30);
      if (seen.has(key)) continue;
      seen.add(key);
      res.push({ ratio: +r.toFixed(2), text: txt.slice(0, 50), tag: el.tagName.toLowerCase(), cls: cls.slice(0, 90) });
    }
  }
  return res;
}

// Runs in the page at phone width. Returns layout breaks.
function layoutCheck(ignoreSelectors) {
  const vw = window.innerWidth;
  const out = [];
  const seen = new Set();
  const describe = (el) => {
    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 4).join('.') : '';
    return `<${el.tagName.toLowerCase()}${cls ? ' class="' + cls + '"' : ''}>`;
  };
  const text = (el) => (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const report = (kind, el, by) => {
    if (ignoreSelectors.some((sel) => el.closest(sel))) return;
    const key = kind + describe(el) + text(el);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ kind, by: Math.round(by), el: describe(el), text: text(el) });
  };
  if (document.documentElement.scrollWidth > vw + 1) {
    out.push({ kind: 'page scrolls sideways', by: document.documentElement.scrollWidth - vw, el: '<html>', text: '' });
  }
  // A horizontal scroller (a wide table, a tab strip) is allowed to hold wide
  // content; anything else is a box whose content should fit it.
  const scrolls = (e) => /(auto|scroll)/.test(getComputedStyle(e).overflowX);
  const boxed = (e) => {
    if (e.matches('.q-card, .wiz-panel, .q-field__control, .q-btn, .q-item, .q-dialog .q-card')) return true;
    const s = getComputedStyle(e);
    return parseFloat(s.borderRightWidth) > 0 && s.borderRightStyle !== 'none';
  };
  for (const el of document.querySelectorAll('body *')) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    if (el.closest('[aria-hidden="true"], .q-tooltip, .q-menu, .wiz-sr-only, .wiz-skip-link, svg')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const s = getComputedStyle(el);
    // A field scrolls its own text, and Quasar's select keeps an invisible
    // focus input that always measures wider than it is.
    if (!el.matches('input, textarea, select') && /(hidden|clip)/.test(s.overflowX) && s.textOverflow !== 'ellipsis'
        && el.scrollWidth > el.clientWidth + 2 && el.childElementCount <= 1 && text(el)) {
      report('text cut off', el, el.scrollWidth - el.clientWidth);
    }
    let box = null;
    let inScroller = false;
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      if (scrolls(e)) { inScroller = true; break; }
      if (boxed(e)) { box = e; break; }
    }
    if (inScroller) continue;
    const limit = box ? box.getBoundingClientRect().right : vw;
    // Report the outermost element that escapes, not each of its descendants.
    const parentRight = el.parentElement.getBoundingClientRect().right;
    if (r.right > limit + 2 && (parentRight <= limit + 2 || el.parentElement === box)) {
      report(box ? 'runs out of its card' : 'runs off the screen', el, r.right - limit);
    }
  }
  return out;
}

async function runAxe(page, source) {
  if (!(await page.evaluate(() => !!window.axe))) await page.addScriptTag({ content: source });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      rules: { 'color-contrast': { enabled: false } },
      resultTypes: ['violations'],
    });
    return r.violations.map((v) => ({
      rule: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target.join(' '), html: n.html.slice(0, 160) })),
      count: v.nodes.length,
    }));
  });
}

(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const baseUrl = cfg.baseUrl || 'http://127.0.0.1:8000';
  const loginAs = cfg.loginAs || 'staff_user';
  const tprefix = cfg.tenant ? `/t/${cfg.tenant}` : '';
  const withTenant = (p, t) => (!tprefix || (t && t.platform) || p.startsWith('/t/') ? p : tprefix + p);
  const opts = cfg.a11y || {};
  const schemes = opts.schemes || ['light', 'dark'];
  const ignore = opts.ignore || [];
  const ignored = (rule, target) => ignore.some((i) => i.rule === rule && (!i.target || i.target === target));
  const outDir = path.join(cfg.outDir || '/tmp/ui-smoke', 'a11y');
  fs.mkdirSync(outDir, { recursive: true });
  const source = axeSource();

  const browser = await chromium.launch({ executablePath: findChrome(cfg.chrome), args: ['--no-sandbox'] });
  const failures = [];
  const report = {};
  for (const scheme of schemes) {
    const ctx = await browser.newContext({ viewport: cfg.viewport || { width: 1440, height: 900 }, colorScheme: scheme });
    const page = await ctx.newPage();
    await page.goto(`${baseUrl}${withTenant('/login')}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.locator('tr, .wiz-grid-card', { hasText: loginAs }).first().getByRole('button', { name: 'Log in as' }).click();
    await page.waitForTimeout(1500);

    for (const t of cfg.targets || []) {
      const label = `${scheme} ${t.name}`;
      try {
        await page.goto(`${baseUrl}${withTenant(t.path, t)}`, { waitUntil: 'networkidle' });
      } catch (e) {
        failures.push(`[${label}] navigation failed: ${e.message.split('\n')[0]}`);
        continue;
      }
      await page.waitForTimeout(1800);
      const isDark = await page.evaluate(() => document.body.classList.contains('body--dark'));
      if ((scheme === 'dark') !== isDark) {
        failures.push(`[${label}] page did not render in ${scheme} mode`);
        continue;
      }
      const axe = (await runAxe(page, source)).filter((v) => !ignored(v.rule, t.name));
      const contrast = ignored('contrast', t.name) ? [] : await page.evaluate(contrastCheck);
      report[label] = { axe, contrast };
      for (const v of axe) {
        failures.push(`[${label}] axe ${v.rule} (${v.impact}, ${v.count}x): ${v.help}`);
        for (const n of v.nodes) failures.push(`      ${n.target}  ${n.html}`);
      }
      for (const c of contrast) failures.push(`[${label}] contrast ${c.ratio}:1 <${c.tag} class="${c.cls}"> "${c.text}"`);
      console.log(`  [${label}] axe=${axe.length} contrast=${contrast.length}`);
    }
    await ctx.close();
  }

  const phone = cfg.phone;
  if (phone) {
    const viewport = phone.viewport || { width: 390, height: 844 };
    const phoneIgnore = phone.ignore || [];
    for (const scheme of phone.schemes || ['light']) {
      const ctx = await browser.newContext({ viewport, colorScheme: scheme, isMobile: true, hasTouch: true });
      const page = await ctx.newPage();
      await page.goto(`${baseUrl}${withTenant('/login')}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(800);
      await page.locator('tr, .wiz-grid-card', { hasText: loginAs }).first().getByRole('button', { name: 'Log in as' }).click();
      await page.waitForTimeout(1500);
      for (const t of cfg.targets || []) {
        const label = `phone ${scheme} ${t.name}`;
        try {
          await page.goto(`${baseUrl}${withTenant(t.path, t)}`, { waitUntil: 'networkidle' });
        } catch (e) {
          failures.push(`[${label}] navigation failed: ${e.message.split('\n')[0]}`);
          continue;
        }
        await page.waitForTimeout(1800);
        const selectors = phoneIgnore.filter((i) => !i.target || i.target === t.name).map((i) => i.selector);
        const layout = await page.evaluate(layoutCheck, selectors);
        report[label] = { layout };
        for (const l of layout) failures.push(`[${label}] ${l.kind} by ${l.by}px: ${l.el} "${l.text}"`);
        if (layout.length) await page.screenshot({ path: path.join(outDir, `${label.replace(/\s+/g, '-')}.png`), fullPage: true });
        console.log(`  [${label}] layout=${layout.length}`);
      }
      await ctx.close();
    }
  }

  await browser.close();
  fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 1));
  console.log('=== accessibility, contrast and phone layout failures ===');
  console.log(failures.length ? failures.join('\n') : '(none)');
  if (failures.length) {
    console.log('\nSee docs/style-guide.md#checking-your-change for how to fix these.');
    process.exit(1);
  }
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
