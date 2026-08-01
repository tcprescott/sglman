/* Drag-to-resize column widths on the app's desktop tables.
 *
 * Quasar's QTable has no built-in column resizing, so this is ours. Three
 * decisions in here are load-bearing and easy to undo by accident:
 *
 * 1. **One delegated pointerdown listener on `document`. No injected handles.**
 *    These tables re-render on every row refresh (the match board does so
 *    constantly), and any node this file inserted would be destroyed by Vue the
 *    moment that happens. A delegated listener plus a CSS `::after` affordance
 *    survives all of it for free.
 * 2. **Pointer capture, not a document-level mousemove.** A fast drag that
 *    leaves the window otherwise strands the table mid-resize.
 * 3. **The width is emitted on pointerup only.** Nothing goes to the server
 *    during the drag; the browser has already painted the new width, and the
 *    round trip is only recording it.
 *
 * A table opts in by carrying `data-wiz-table-key` (set by
 * theme/tables/preferences.customize_table), and each header cell carries a
 * `wiz-col-<name>` class from the same place — nothing else identifies which
 * table a `<th>` belongs to, or which column it is.
 */
(function () {
  if (window.__wizTableColumns) return;
  window.__wizTableColumns = true;

  var RESIZE_ZONE = 6;      // px from the right edge that starts a drag
  var MIN_WIDTH = 40;       // must match TablePreferenceService.MIN_WIDTH
  var MAX_WIDTH = 1200;     // must match TablePreferenceService.MAX_WIDTH
  var DESKTOP = '(min-width: 1024px)';
  var OFFLINE_CLASS = 'wiz-offline';

  var drag = null;

  function isDesktop() {
    return window.matchMedia && window.matchMedia(DESKTOP).matches;
  }

  function isOffline() {
    return document.body.classList.contains(OFFLINE_CLASS);
  }

  function columnName(th) {
    var match = /(?:^|\s)wiz-col-([A-Za-z0-9_-]+)/.exec(th.className || '');
    return match ? match[1] : null;
  }

  function target(event) {
    if (!event.target || !event.target.closest) return null;
    var th = event.target.closest('thead th');
    if (!th) return null;
    var root = th.closest('[data-wiz-table-key]');
    if (!root) return null;
    var name = columnName(th);
    if (!name) return null;
    return { th: th, root: root, key: root.getAttribute('data-wiz-table-key'), column: name };
  }

  function inResizeZone(event, th) {
    return th.getBoundingClientRect().right - event.clientX <= RESIZE_ZONE;
  }

  function emit(key, column, width) {
    if (typeof emitEvent !== 'function') return;
    emitEvent('wiz_table_width', { key: key, column: column, width: width });
  }

  document.addEventListener('pointerdown', function (event) {
    if (event.button !== 0 || !isDesktop() || isOffline()) return;
    var hit = target(event);
    if (!hit || !inResizeZone(event, hit.th)) return;

    var startWidth = hit.th.getBoundingClientRect().width;
    drag = {
      th: hit.th, root: hit.root, key: hit.key, column: hit.column,
      startX: event.clientX, startWidth: startWidth, width: Math.round(startWidth),
    };
    // A table only switches to fixed layout once it has a width; do it now so
    // the drag is visible before anything is stored.
    hit.root.classList.add('wiz-table--sized');
    document.body.classList.add('wiz-resizing');
    try { hit.th.setPointerCapture(event.pointerId); } catch (e) { /* not capturable */ }
    event.preventDefault();
  }, true);

  document.addEventListener('pointermove', function (event) {
    if (!drag) return;
    var width = Math.round(drag.startWidth + (event.clientX - drag.startX));
    width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width));
    drag.width = width;
    drag.th.style.width = width + 'px';
    drag.th.style.minWidth = width + 'px';
    drag.th.style.maxWidth = width + 'px';
  });

  function finish(store) {
    if (!drag) return;
    var current = drag;
    drag = null;
    document.body.classList.remove('wiz-resizing');
    if (store) emit(current.key, current.column, current.width);
  }

  document.addEventListener('pointerup', function () { finish(true); });
  document.addEventListener('pointercancel', function () { finish(false); });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || !drag) return;
    drag.th.style.width = '';
    drag.th.style.minWidth = '';
    drag.th.style.maxWidth = '';
    finish(false);
  });

  // Double-clicking the divider auto-fits: the stored width is cleared and the
  // column goes back to content-driven sizing.
  document.addEventListener('dblclick', function (event) {
    if (!isDesktop() || isOffline()) return;
    var hit = target(event);
    if (!hit || !inResizeZone(event, hit.th)) return;
    hit.th.style.width = '';
    hit.th.style.minWidth = '';
    hit.th.style.maxWidth = '';
    emit(hit.key, hit.column, null);
    event.preventDefault();
  }, true);
})();
