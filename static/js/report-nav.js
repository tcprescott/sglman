/*
 * Admin reports: keep the operator's place across a filter change.
 *
 * A filter change re-renders the report body in place (see
 * `navigate_with_params`) rather than navigating. That is much faster, but the
 * body is still streamed in over a websocket, so the document collapses to a
 * fraction of its height mid-refresh and the browser clamps scrollY — landing
 * the operator back at the top of a page up to 3,900px tall, which is the part
 * that reads as broken.
 *
 * So the position is written continuously as the operator scrolls, and put back
 * once the document is tall enough to hold it again: on page load, and on the
 * `wizReportKeepPlace()` call the server makes alongside each refresh.
 *
 * Keyed by report, so a *different* report starts at its own position — that is
 * a different page, not a moved one — and two tabs on two reports do not
 * clobber each other. The key is read from the URL each time, and
 * `navigate_with_params` replaceStates the new URL before calling in, so a
 * report switch reads the key it is switching *to*.
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
  var restoring = false;

  function markIntent() {
    lastIntent = Date.now();
  }

  function track() {
    // Only a scroll the *operator* asked for counts. Focusing a date input
    // jumps the page to the top on its own, and without this that jump would
    // overwrite the position a moment before the filter change applies —
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
        // Written as it happens rather than read when the filter changes: the
        // handler is synchronous and applies immediately, so a round-trip to
        // fetch scrollY would race it.
        if (restoring) return;
        if (Date.now() - lastIntent > INTENT_WINDOW_MS) return;
        try {
          window.sessionStorage.setItem(reportKey(), String(Math.round(window.scrollY)));
        } catch (e) {
          /* private mode / quota — losing the position is not worth an error */
        }
      },
      { passive: true }
    );
  }

  function restore() {
    var raw;
    try {
      raw = window.sessionStorage.getItem(reportKey());
    } catch (e) {
      return;
    }
    if (!raw) return;
    var y = parseInt(raw, 10);
    if (!y || y <= 0) return;

    // A report body is built server-side and streamed, so restoring immediately
    // scrolls a document that is still a fraction of its final height. Retry
    // until the page is tall enough to hold the position. `restoring` keeps the
    // collapse (and our own scrollTo) from overwriting the stored value on the
    // way past.
    var frames = 0;
    restoring = true;
    (function step() {
      if (document.body && document.body.scrollHeight >= y + window.innerHeight * 0.5) {
        window.scrollTo(0, y);
        restoring = false;
        return;
      }
      if (++frames > RESTORE_FRAME_BUDGET) {
        restoring = false;
        return;
      }
      window.requestAnimationFrame(step);
    })();
  }

  // Called by the server right after it replaceStates the new filter URL and
  // re-renders the body in place.
  window.wizReportKeepPlace = restore;

  if (onReports()) {
    track();
    restore();
  }
})();
