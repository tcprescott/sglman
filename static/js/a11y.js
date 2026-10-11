/*
 * Two dialog repairs Quasar leaves to the app (WCAG 2.4.3, 4.1.2):
 *
 * - A dialog needs a name. Most of ours open on a title (.text-h6 in the
 *   shared dialog_header, or a heading); point aria-labelledby at it.
 * - Closing a dialog should hand focus back to whatever opened it. Our
 *   dialogs are built server-side and torn down on close, so Quasar's own
 *   refocus often finds nothing and focus fell to <body>, sending a keyboard
 *   user back to the top of the page.
 */
(function () {
  if (window.__wizA11y) return;
  window.__wizA11y = true;

  var lastOutside = null;
  var lastKey = null;
  var seq = 0;
  var dialogWasOpen = false;

  // A table slot re-renders its rows when the dialog it opened saves or
  // closes, replacing the very button that had focus. Remember how to find its
  // replacement: same id, or the same position among same-named controls.
  function keyFor(el) {
    if (!el.getAttribute('aria-label') && !/^(BUTTON|A)$/.test(el.tagName)) return { id: el.id };
    var name = el.getAttribute('aria-label') || (el.textContent || '').trim();
    var sel = el.tagName.toLowerCase() + (el.getAttribute('aria-label') ? '[aria-label]' : '');
    var peers = Array.prototype.filter.call(document.querySelectorAll(sel), function (p) {
      return (p.getAttribute('aria-label') || (p.textContent || '').trim()) === name;
    });
    return { id: el.id, sel: sel, name: name, index: peers.indexOf(el) };
  }

  function find(key) {
    if (!key) return null;
    if (key.id) {
      var byId = document.getElementById(key.id);
      if (byId) return byId;
    }
    if (!key.sel) return null;
    var peers = Array.prototype.filter.call(document.querySelectorAll(key.sel), function (p) {
      return (p.getAttribute('aria-label') || (p.textContent || '').trim()) === key.name;
    });
    return peers[key.index] || null;
  }

  document.addEventListener('focusin', function (e) {
    var t = e.target;
    if (t === document.body || (t.closest && t.closest('.q-dialog, .q-menu'))) return;
    lastOutside = t;
    lastKey = keyFor(t);
  });

  function nameDialog(dialog) {
    if (dialog.hasAttribute('aria-label') || dialog.hasAttribute('aria-labelledby')) return;
    var title = dialog.querySelector('h1, h2, h3, .dialog-header .text-h6, .text-h6, .section-title');
    if (!title) return;
    if (!title.id) title.id = 'wiz-dialog-title-' + (++seq);
    dialog.setAttribute('aria-labelledby', title.id);
  }

  function refocus() {
    if (!dialogWasOpen || document.querySelector('.q-dialog')) return;
    dialogWasOpen = false;
    var active = document.activeElement;
    if (active && active !== document.body) return;
    var target = lastOutside && lastOutside.isConnected ? lastOutside : find(lastKey);
    if (target && target.offsetParent !== null) target.focus();
  }

  new MutationObserver(function (records) {
    var removed = false;
    records.forEach(function (r) {
      r.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        var d = n.matches && n.matches('[role=dialog]') ? n : n.querySelector && n.querySelector('[role=dialog]');
        if (d) {
          dialogWasOpen = true;
          setTimeout(function () { nameDialog(d); }, 0);
        }
      });
      if (r.removedNodes.length) removed = true;
    });
    if (removed) setTimeout(refocus, 50);
  }).observe(document.body, { childList: true, subtree: true });
})();
