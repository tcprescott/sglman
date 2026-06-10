"""Presentation-side bridge for live match updates.

Views call :func:`register_view` at build time with an async ``on_change`` handler.
Each registration captures the current NiceGUI ``Client`` and subscribes a callback
to :mod:`application.match_events`. When a match changes, the callback schedules the
handler inside the captured client's context so UI mutations land in the right
browser. Subscriptions are cleaned up automatically when the client disconnects.
"""

from typing import Awaitable, Callable, Dict, List

from nicegui import app, background_tasks, context

from application import match_events

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
        # Enter the captured client's context so refresh()/update_row_by_id and
        # app.storage.user resolve to the right browser (mirrors the proven
        # `with client:` pattern in theme/tables/match.py).
        with client:
            await on_change(match_id, change_type)

    def _callback(match_id: int, change_type: str) -> None:
        background_tasks.create(_runner(match_id, change_type))

    token = match_events.subscribe(_callback)
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
        match_events.unsubscribe(token)
