"""Canonical registry of domain event names published on the event bus.

Names are namespaced ``object.verb`` strings, mirroring the discipline of
:class:`~application.services.audit_service.AuditActions`. Unlike audit actions
these are an **external contract**: webhook subscribers pick from them and match
on them, so treat renames as breaking changes. Kept deliberately import-free of
the service layer so the events package stays cycle-free (like
``application.match_events``).
"""

from typing import FrozenSet


class EventType:
    # Match lifecycle
    MATCH_CREATED = 'match.created'
    MATCH_UPDATED = 'match.updated'
    MATCH_RESCHEDULED = 'match.rescheduled'
    MATCH_SEATED = 'match.seated'
    MATCH_STARTED = 'match.started'
    MATCH_FINISHED = 'match.finished'
    MATCH_CONFIRMED = 'match.confirmed'
    MATCH_SEED_ROLLED = 'match.seed_rolled'
    MATCH_STAGE_ASSIGNED = 'match.stage_assigned'
    MATCH_STAGE_CLEARED = 'match.stage_cleared'
    MATCH_STREAM_CANDIDATE_SET = 'match.stream_candidate_set'
    MATCH_STREAM_CANDIDATE_CLEARED = 'match.stream_candidate_cleared'

    # Crew
    CREW_SIGNUP_CREATED = 'crew.signup_created'
    CREW_SIGNUP_REMOVED = 'crew.signup_removed'
    CREW_APPROVAL_CHANGED = 'crew.approval_changed'
    CREW_ACKNOWLEDGED = 'crew.acknowledged'

    # Volunteer
    VOLUNTEER_ASSIGNED = 'volunteer.assigned'
    VOLUNTEER_UNASSIGNED = 'volunteer.unassigned'
    VOLUNTEER_ACKNOWLEDGED = 'volunteer.acknowledged'

    # Every published event name; drives the webhook UI multiselect + validation.
    ALL: FrozenSet[str] = frozenset({
        MATCH_CREATED, MATCH_UPDATED, MATCH_RESCHEDULED, MATCH_SEATED,
        MATCH_STARTED, MATCH_FINISHED, MATCH_CONFIRMED, MATCH_SEED_ROLLED,
        MATCH_STAGE_ASSIGNED, MATCH_STAGE_CLEARED,
        MATCH_STREAM_CANDIDATE_SET, MATCH_STREAM_CANDIDATE_CLEARED,
        CREW_SIGNUP_CREATED, CREW_SIGNUP_REMOVED, CREW_APPROVAL_CHANGED,
        CREW_ACKNOWLEDGED,
        VOLUNTEER_ASSIGNED, VOLUNTEER_UNASSIGNED, VOLUNTEER_ACKNOWLEDGED,
    })

    # Wildcard a subscriber can register to receive every event.
    WILDCARD = '*'

    @classmethod
    def is_valid(cls, name: str) -> bool:
        """True for the wildcard or any registered event name."""
        return name == cls.WILDCARD or name in cls.ALL
