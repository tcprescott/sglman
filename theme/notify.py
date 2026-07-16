"""Shared error-toast mapper for the presentation layer.

CLAUDE.md documents a single convention for surfacing service errors in the UI:
a user-facing ``ValueError`` (including ``NotFoundError``) becomes an amber
``warning`` toast showing ``str(e)`` with no prefix, while a ``PermissionError``
(a stale/insufficient session) becomes a red ``negative`` toast. Routing every
handler through :func:`notify_error` keeps the wording and colours consistent and
stops the three drifting variants the audit flagged (``§3.1``).
"""

from nicegui import ui

__all__ = ['notify_error']


def notify_error(error: Exception) -> None:
    """Show a service error toast per the documented convention.

    ``PermissionError`` → red (``negative``); any other user-facing error
    (``ValueError`` / ``NotFoundError``) → amber (``warning``). The message is
    ``str(error)`` with no ``Error:`` prefix. Call inside a dialog's slot context
    (e.g. ``with self.dialog:``) when notifying from a dialog handler.
    """
    color = 'negative' if isinstance(error, PermissionError) else 'warning'
    ui.notify(str(error), color=color)
