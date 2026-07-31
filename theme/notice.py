"""A toast that survives a redirect.

``ui.notify`` enqueues a message on *this* client's outbox. A handler that
notifies and then calls ``ui.navigate.to`` unloads the document the toast would
have rendered in, so the message is written and never seen — the shape behind
nine unreachable failure strings across the OAuth link pages. ``ui.notify``
*during page build* is fine (the outbox buffers it until the websocket
connects), which is what makes the stash/drain pair below work: the message is
emitted while the **next** page is being built.

Use :func:`stash_notice` **only** for a notify that precedes a navigation. Where
a handler notifies and keeps rendering the same page — a table action that calls
``.refresh()`` — ``ui.notify`` is correct and this module is the wrong tool.

Three drain points, which is the honest cost of NiceGUI's page model here:
:meth:`theme.base.BaseLayout.render` (every ``/home/*``, ``/admin/*``,
``/volunteer/*`` page), :func:`theme.error_page.render_error_page` (a notice must
still show on the 403/404 a bad return path lands on), and ``/login``. There is
no single universal hook — ``protected_page``'s wrapper is not one, because
``/home`` is a bare ``@ui.page``.
"""

from nicegui import app, ui

__all__ = ['drain_notice', 'stash_notice']

# One key, one slot, last write wins. A queue would let two notices pile up
# across an aborted redirect chain and surface a stale one on a later page.
_KEY = 'pending_notice'


def stash_notice(message: str, *, color: str = 'warning') -> None:
    """Queue a toast for the next page this browser loads.

    For the notify-then-redirect case only: ``ui.notify`` followed by
    ``ui.navigate.to`` loses the toast with the document it was queued against.
    """
    if not message:
        return
    app.storage.user[_KEY] = {'message': message, 'color': color}


def drain_notice() -> None:
    """Show and consume a notice stashed before a redirect. Idempotent.

    Pops before notifying, so a re-render cannot replay a message the user has
    already been shown.
    """
    try:
        notice = app.storage.user.pop(_KEY, None)
    except Exception:
        return
    if not isinstance(notice, dict):
        return
    message = notice.get('message')
    if not message:
        return
    ui.notify(message, color=notice.get('color') or 'warning')
