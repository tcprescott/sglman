"""The :class:`Event` value object carried through the event bus.

Events are immutable snapshots of something that happened, published by services
*after* they commit. ``actor`` identity is snapshotted (never held as an ORM
reference) so an event can safely cross the async dispatch boundary — mirrors the
enrichment :class:`~application.services.audit_service.AuditService` does for
audit rows.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: dict[str, Any]
    actor_id: Optional[int] = None
    actor_username: Optional[str] = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, event_type: str, payload: dict[str, Any], actor: Any = None) -> "Event":
        """Build an event, snapshotting the actor's id/username if one is given."""
        return cls(
            event_type=event_type,
            payload=payload,
            actor_id=getattr(actor, 'id', None),
            actor_username=getattr(actor, 'username', None),
        )

    def to_wire(self) -> dict[str, Any]:
        """The canonical JSON-serialisable shape delivered to webhook subscribers."""
        return {
            'event_type': self.event_type,
            'occurred_at': self.occurred_at.isoformat(),
            'actor_id': self.actor_id,
            'actor_username': self.actor_username,
            'data': self.payload,
        }
