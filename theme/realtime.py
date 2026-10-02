"""Presentation-side bridge for live match updates.

Views call :func:`register_view` at build time with an async ``on_change`` handler.
Each registration captures the current NiceGUI ``Client`` and subscribes a callback
to :mod:`application.events.match_live`. When a match changes, the callback schedules the
handler inside the captured client's context so UI mutations land in the right
browser. Subscriptions are cleaned up automatically when the client disconnects.
"""

from typing import Awaitable, Callable, Dict, List

from nicegui import app, background_tasks, context
from nicegui.storage import request_contextvar

from application.events import match_live

OnChange = Callable[[int, str], Awaitable[None]]

# client.id -> list of subscription tokens, so we can release them on disconnect.
_client_tokens: Dict[str, List[int]] = {}
_disconnect_installed = False


def register_view(on_change: OnChange) -> None:
    """Subscribe ``on_change(match_id, change_type)`` for the current client.

    Must be called during page/view construction (a NiceGUI client context).
    """
    client = context.client
    client_id = client.id

    async def _runner(match_id: int, change_type: str) -> None:
        # Enter the captured client's context so refresh()/update_row_by_id
        # resolve to the right browser (mirrors the proven `with client:`
        # pattern in theme/tables/match.py). app.storage.user is keyed off
        # NiceGUI's request contextvar, not the client, and this task inherits
        # the *publisher's* contextvars: without rebinding it, every open board
        # read the staff member who approved a move as its viewer.
        request = client.request
        session_id = (getattr(request, 'session', None) or {}).get('id')
        if session_id not in app.storage._users:  # pylint: disable=protected-access
            # The page's session has no user storage (rotated at login, or the
            # client outlived it): app.storage.user would raise, and there is
            # no viewer to refresh for.
            return
        token = request_contextvar.set(request)
        try:
            with client:
                await on_change(match_id, change_type)
        finally:
            request_contextvar.reset(token)

    def _callback(match_id: int, change_type: str) -> None:
        background_tasks.create(_runner(match_id, change_type))

    token = match_live.subscribe(_callback)
    _client_tokens.setdefault(client_id, []).append(token)
    _install_disconnect_cleanup()


def _install_disconnect_cleanup() -> None:
    global _disconnect_installed
    if _disconnect_installed:
        return
    _disconnect_installed = True
    app.on_disconnect(_on_disconnect)


def _on_disconnect(client) -> None:
    for token in _client_tokens.pop(client.id, []):
        match_live.unsubscribe(token)
