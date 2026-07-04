"""Centralized in-process event system.

Publishers::

    from application.events import event_bus, Event, EventType
    event_bus.publish(Event.create(EventType.MATCH_CREATED, {...}, actor))

Subscribers register with ``event_bus.subscribe_sync`` (inline, non-blocking) or
``event_bus.subscribe_async`` (I/O, runs on the dispatch worker). See
``application/events/bus.py`` for the full contract.
"""

from application.events import bus as event_bus
from application.events import dispatch_queue
from application.events.event import Event
from application.events.event_types import EventType

__all__ = ['event_bus', 'dispatch_queue', 'Event', 'EventType']
