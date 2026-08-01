"""Client-side connection watch — an action that cannot reach the server says so.

While the socket is down the server can say nothing: ``ui.notify``, a
``refreshable.refresh()`` and a disabled-state update all travel over the very
socket that is gone. So the honest-offline state is built in the browser and
judged by what the operator sees with the network off:

* a **banner** (not a toast — a toast fired while the phone was in a pocket has
  expired by the time anyone looks) in a fixed position, out of the way of the
  mobile bottom nav;
* a ``wiz-offline`` class on ``<body>``, the single hook every other offline rule
  reads;
* a capture-phase click guard that refuses any control marked
  ``wiz-requires-socket`` and explains the refusal through ``Quasar.Notify``,
  which is client-side and therefore still works.

Detection reads two independent signals because neither alone is sufficient: the
window ``offline``/``online`` events fire the moment the link drops, while the
socket's ``disconnect``/``connect`` cover a live link to an unreachable server,
where ``navigator.onLine`` stays ``true``.

The framework's own ``#popup`` ("Connection lost / Trying to reconnect", branded
in ``static/css/styles.css``) is left alone — it carries the later
about-to-reload moment. It is also why this module exists: ``#popup`` only shows
on socket ``disconnect``, which lags a dead network by ``ping_interval +
ping_timeout``, and its ``transition-delay`` adds a further 2 s on top.
"""

import json

from nicegui import ui

__all__ = [
    'BLOCKED_ACTION_TEXT',
    'OFFLINE_BANNER_TEXT',
    'OFFLINE_BODY_CLASS',
    'ONLINE_BANNER_TEXT',
    'REQUIRES_SOCKET_CLASS',
    'connection_watch_script',
    'install_connection_watch',
]

# Copy says what it means for the operator, not what happened to the socket.
OFFLINE_BANNER_TEXT = "No connection — actions won't be saved. Reconnecting…"
ONLINE_BANNER_TEXT = 'Back online.'
BLOCKED_ACTION_TEXT = 'No connection — not sent. Try again when the banner clears.'

#: Set on ``<body>`` while the client believes it cannot reach the server.
OFFLINE_BODY_CLASS = 'wiz-offline'
#: Put on any control whose effect needs a round trip, so the guard can refuse it.
REQUIRES_SOCKET_CLASS = 'wiz-requires-socket'

_BANNER_ID = 'wiz-connection-banner'
_RECONNECTED_MS = 2000
_SOCKET_POLL_MS = 100
_SOCKET_POLL_TRIES = 100


def connection_watch_script() -> str:
    """The ``<script>`` installed by :func:`install_connection_watch`.

    Exposed so its copy and its four event bindings can be asserted without a
    browser.
    """
    return _SCRIPT


def install_connection_watch() -> None:
    """Give the current page a visible, persistent offline state.

    Call at page-build time. ``BaseLayout.render_chrome`` calls it for every
    themed page, which is deliberate: tab panels are built lazily inside an event
    handler, and ``ui.add_body_html`` from there inserts markup with
    ``insertAdjacentHTML``, which never executes a ``<script>``. A tab that
    installed its own watch would silently get nothing.
    """
    ui.add_body_html(_SCRIPT)


_SCRIPT = '''<script>
(function () {
  if (window.__wizConnectionWatch) return;
  window.__wizConnectionWatch = true;

  var OFFLINE_TEXT = %(offline)s;
  var ONLINE_TEXT = %(online)s;
  var BLOCKED_TEXT = %(blocked)s;
  var OFFLINE_CLASS = %(offline_class)s;
  var REQUIRES_SOCKET = %(requires_socket)s;
  var clearTimer = null;

  function banner() {
    var el = document.getElementById(%(banner_id)s);
    if (!el) {
      el = document.createElement('div');
      el.id = %(banner_id)s;
      el.className = 'wiz-connection-banner';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.hidden = true;
      document.body.appendChild(el);
    }
    return el;
  }

  function say(text, transient) {
    var el = banner();
    el.textContent = text;
    el.hidden = false;
    el.classList.toggle('wiz-connection-banner--ok', !!transient);
    if (clearTimer) { clearTimeout(clearTimer); clearTimer = null; }
    if (transient) clearTimer = setTimeout(function () { el.hidden = true; }, %(reconnected_ms)d);
  }

  function down() {
    document.body.classList.add(OFFLINE_CLASS);
    say(OFFLINE_TEXT, false);
  }

  function up() {
    // Only announce a recovery we actually reported, so the socket's first
    // connect on a normal page load does not flash "Reconnected."
    if (!document.body.classList.contains(OFFLINE_CLASS)) return;
    document.body.classList.remove(OFFLINE_CLASS);
    say(ONLINE_TEXT, true);
  }

  window.addEventListener('offline', down);
  window.addEventListener('online', up);

  // window.socket is assigned in nicegui.js's mounted(), which can run after
  // this snippet is parsed — poll for it briefly instead of assuming it exists,
  // and give up quietly rather than throw.
  var tries = 0;
  (function bindSocket() {
    if (window.socket && window.socket.on) {
      window.socket.on('disconnect', down);
      window.socket.on('connect', up);
      return;
    }
    if (tries++ < %(poll_tries)d) setTimeout(bindSocket, %(poll_ms)d);
  })();

  // Refuse in the capture phase, before Vue's own click listener runs, and
  // explain the refusal with Quasar.Notify — ui.notify would need the socket
  // that is down.
  document.addEventListener('click', function (e) {
    if (!document.body.classList.contains(OFFLINE_CLASS)) return;
    var hit = e.target && e.target.closest ? e.target.closest('.' + REQUIRES_SOCKET) : null;
    if (!hit) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if (window.Quasar && Quasar.Notify) {
      Quasar.Notify.create({ message: BLOCKED_TEXT, color: 'warning', position: 'top', timeout: 4000 });
    }
  }, true);
})();
</script>''' % {
    'offline': json.dumps(OFFLINE_BANNER_TEXT),
    'online': json.dumps(ONLINE_BANNER_TEXT),
    'blocked': json.dumps(BLOCKED_ACTION_TEXT),
    'offline_class': json.dumps(OFFLINE_BODY_CLASS),
    'requires_socket': json.dumps(REQUIRES_SOCKET_CLASS),
    'banner_id': json.dumps(_BANNER_ID),
    'reconnected_ms': _RECONNECTED_MS,
    'poll_ms': _SOCKET_POLL_MS,
    'poll_tries': _SOCKET_POLL_TRIES,
}
