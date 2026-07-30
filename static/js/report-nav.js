/*
 * Admin reports: keep the operator's place across a filter change.
 *
 * Every filter control in the reports subsystem navigates (see
 * `navigate_with_params` — the reload is a deliberate deferral recorded in
 * docs/current-state.md). A measured filter change costs ~4.4s, a full frame
 * navigation and 28 requests; the part that reads as broken is not the latency
 * but landing back at scrollY 0 on a page up to 3,900px tall.
 *
 * Keyed by report, so a *different* report starts at the top — that is a
 * different page, not a moved position — and two tabs on two reports do not
 * clobber each other.
 */
(function () {
  if (window.__wizReportsInstalled) return;
  window.__wizReportsInstalled = true;

  var PREFIX = 'wiz-report-scroll:';
  // A report body is streamed in over seconds, so the restore has to outlast
  // the render; ~5s at 60fps, then give up silently.
  var RESTORE_FRAME_BUDGET = 300;

  function onReports() {
    return window.location.pathname.indexOf('/admin/reports') !== -1;
  }

  // The report name is already in the URL; nothing has to be threaded from the
  // server to identify the page whose position we are keeping.
  function reportKey() {
    var m = /[?&]report=([^&]*)/.exec(window.location.search);
    return PREFIX + (m ? decodeURIComponent(m[1]) : 'dashboard');
  }

  var SCROLL_KEYS = {
    PageUp: 1, PageDown: 1, Home: 1, End: 1, ' ': 1,
    ArrowUp: 1, ArrowDown: 1, ArrowLeft: 1, ArrowRight: 1,
  };
  var INTENT_WINDOW_MS = 500;
  var lastIntent = 0;

  function markIntent() {
    lastIntent = Date.now();
  }

  function track() {
    var key = reportKey();

    // Only a scroll the *operator* asked for counts. Focusing a date input
    // jumps the page to the top on its own, and without this that jump would
    // overwrite the position a moment before the filter change navigates —
    // recording exactly the value the fix exists to avoid.
    window.addEventListener('wheel', markIntent, { passive: true });
    window.addEventListener('touchmove', markIntent, { passive: true });
    window.addEventListener('keydown', function (e) {
      if (SCROLL_KEYS[e.key]) markIntent();
    }, { passive: true });
    // Scrollbar drags target the root element rather than any content.
    window.addEventListener('mousedown', function (e) {
      if (e.target === document.documentElement || e.target === document.body) markIntent();
    }, { passive: true });

    window.addEventListener(
      'scroll',
      function () {
        // Written as it happens rather than read at navigate time: the filter
        // handler is synchronous and the navigation is immediate, so a
        // round-trip to fetch scrollY would race it.
        if (Date.now() - lastIntent > INTENT_WINDOW_MS) return;
        try {
          window.sessionStorage.setItem(key, String(Math.round(window.scrollY)));
        } catch (e) {
          /* private mode / quota — losing the position is not worth an error */
        }
      },
      { passive: true }
    );
  }

  function restore() {
    var key = reportKey();
    var raw;
    try {
      raw = window.sessionStorage.getItem(key);
    } catch (e) {
      return;
    }
    if (!raw) return;
    var y = parseInt(raw, 10);
    if (!y || y <= 0) return;

    // A report body is built server-side and streamed, so restoring at connect
    // time scrolls a document that is still a fraction of its final height.
    // Retry until the page is tall enough to hold the position.
    var frames = 0;
    (function step() {
      if (document.body && document.body.scrollHeight >= y + window.innerHeight * 0.5) {
        window.scrollTo(0, y);
        return;
      }
      if (++frames > RESTORE_FRAME_BUDGET) return;
      window.requestAnimationFrame(step);
    })();
  }

  if (onReports()) {
    track();
    restore();
  }
})();
