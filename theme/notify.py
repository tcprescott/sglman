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


# A message past this length is one a five-second single-line toast truncates
# into uselessness — the config validators produce several of them.
_LONG_MESSAGE = 90


def notify_error(error: Exception) -> None:
    """Show a service error toast per the documented convention.

    ``PermissionError`` → red (``negative``); any other user-facing error
    (``ValueError`` / ``NotFoundError``) → amber (``warning``). The message is
    ``str(error)`` with no ``Error:`` prefix. Call inside a dialog's slot context
    (e.g. ``with self.dialog:``) when notifying from a dialog handler.

    A long message additionally gets ``multi_line``, a dismiss button and a
    longer timeout: the default toast is one line for five seconds, which is
    where a validation error explaining what to fix went to die.
    """
    color = 'negative' if isinstance(error, PermissionError) else 'warning'
    message = str(error)
    if len(message) > _LONG_MESSAGE:
        ui.notify(
            message, color=color, multi_line=True, close_button='Dismiss',
            timeout=15000, classes='wiz-toast-long',
        )
        return
    ui.notify(message, color=color)
