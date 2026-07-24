"""Live bracket refresh — subscribe a bracket detail view to the event bus.

The public bracket page registers here at build time; each registration captures
the current NiceGUI ``Client`` and subscribes a fast, non-blocking listener to
the in-process :mod:`application.events` bus (the ``BRACKET_*`` events services
publish after they commit). When a matching event fires, the listener schedules
the view's ``on_change`` inside the captured client's context so the refresh
lands in the right browser. Subscriptions are released on client disconnect.

Mirrors the ``theme/realtime.py`` pattern, but against the domain event bus
(``event_bus.subscribe_sync``) rather than ``application.match_events``.
"""

from typing import Awaitable, Callable, Dict, List

from nicegui import app, background_tasks, context

from application.events import EventType, event_bus

OnChange = Callable[[], Awaitable[None]]

_BRACKET_EVENTS = (
    EventType.BRACKET_MATCH_COMPLETED,
    EventType.BRACKET_ADVANCED,
    EventType.BRACKET_COMPLETED,
    EventType.BRACKET_STAGE_ADVANCED,
    EventType.BRACKET_STARTED,
)

# client.id -> event-bus subscription tokens, released on disconnect.
_client_tokens: Dict[str, List[int]] = {}
_disconnect_installed = False


def register_bracket_view(bracket_id: int, on_change: OnChange) -> None:
    """Refresh the current view when its bracket changes.

    Must be called during page construction (a live client context). ``on_change``
    is an async no-arg callable (typically a ``@ui.refreshable``'s ``.refresh``).
    """
    client = context.client
    client_id = client.id

    async def _runner() -> None:
        with client:
            await on_change()

    def _callback(event) -> None:
        payload = event.payload or {}
        # Match events touching this bracket — including a stage advance that
        # seeds it (to_bracket_id) or drew from it (from_bracket_id).
        related = {
            payload.get('bracket_id'),
            payload.get('to_bracket_id'),
            payload.get('from_bracket_id'),
        }
        if bracket_id not in related:
            return
        background_tasks.create(_runner())

    token = event_bus.subscribe_sync(_callback, _BRACKET_EVENTS)
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
        event_bus.unsubscribe(token)
