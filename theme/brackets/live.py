"""Live bracket refresh — subscribe a bracket detail view to the event bus.

The public bracket page registers here at build time; the registration subscribes
a fast, non-blocking listener to the in-process :mod:`application.events` bus (the
``BRACKET_*`` events services publish after they commit). When a matching event
fires, the listener invokes the caller's ``on_event`` callback — a *sync,
non-blocking* function that schedules its own (debounced, client-scoped) refresh.
Subscriptions are released on client disconnect.

Coalescing lives in the caller (the page debounces so a burst of events — e.g.
``BRACKET_MATCH_COMPLETED`` then ``BRACKET_COMPLETED`` from one report — collapses
into a single rebuild), keeping this module a thin, non-blocking bridge.
"""

from typing import Callable, Dict, List

from nicegui import app, context

from application.events import EventType, event_bus

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


def register_bracket_view(bracket_id: int, on_event: Callable[[], None]) -> None:
    """Call ``on_event()`` when this bracket changes.

    Must be called during page construction (a live client context). ``on_event``
    is a **sync, non-blocking** callback (it runs inside ``publish``): it should
    only *schedule* a refresh (see the page's debounced ``request_refresh``),
    never block or await.
    """
    client_id = context.client.id

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
        on_event()

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
