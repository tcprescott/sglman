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
    MATCH_DELETED = 'match.deleted'
    MATCH_RESCHEDULED = 'match.rescheduled'
    MATCH_SEATED = 'match.seated'
    MATCH_STARTED = 'match.started'
    MATCH_FINISHED = 'match.finished'
    MATCH_CONFIRMED = 'match.confirmed'
    MATCH_ACKNOWLEDGED = 'match.acknowledged'
    MATCH_RESULT_RECORDED = 'match.result_recorded'
    MATCH_SEED_ROLLED = 'match.seed_rolled'
    MATCH_STAGE_ASSIGNED = 'match.stage_assigned'
    MATCH_STAGE_CLEARED = 'match.stage_cleared'
    MATCH_STATIONS_ASSIGNED = 'match.stations_assigned'
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

    # Racetime race-room lifecycle (mirrors AuditActions.RACE_ROOM_*). Tenant-
    # scoped domain events a webhook subscriber can act on; published by the
    # racetime room lifecycle as the system user.
    RACE_ROOM_CREATED = 'race_room.created'
    RACE_ROOM_OPENED = 'race_room.opened'
    RACE_ROOM_STARTED = 'race_room.started'
    RACE_ROOM_FINISHED = 'race_room.finished'
    RACE_ROOM_CANCELLED = 'race_room.cancelled'
    RACE_ROOM_RESULT_RECORDED = 'race_room.result_recorded'

    # SpeedGaming ETL (mirrors AuditActions.SG_*). Tenant-scoped domain events a
    # webhook subscriber can act on; published by the sync worker as the system
    # user. A subscriber can react to a freshly-imported or cancelled match.
    SG_EPISODE_IMPORTED = 'sg_sync.episode_imported'
    SG_EPISODE_CANCELLED = 'sg_sync.episode_cancelled'
    SG_MATCH_AUTO_FINISHED = 'sg_sync.match_auto_finished'

    # Discord Scheduled Events mirror (mirrors AuditActions.DISCORD_EVENT_*).
    # Tenant-scoped domain events a webhook subscriber can act on; published by
    # the reconciler when it creates/updates/cancels a mirrored Discord event.
    DISCORD_EVENT_CREATED = 'discord_event.created'
    DISCORD_EVENT_UPDATED = 'discord_event.updated'
    DISCORD_EVENT_CANCELLED = 'discord_event.cancelled'

    # Platform external-service health (PR 5). Published by the health monitor
    # when a probed dependency transitions into an unhealthy state (down or a
    # credential warning). Platform-level (no tenant), so tenant-scoped webhooks
    # never receive it — the alert's real delivery is Sentry + optional super-
    # admin DM; it is published here so the contract is uniform and any future
    # platform-level subscriber can act on it. Not mirrored by an AuditAction:
    # health transitions are observations by the monitor, not user actions.
    SERVICE_HEALTH_ALERT = 'service_health.alert'

    # Every published event name; drives the webhook UI multiselect + validation.
    ALL: FrozenSet[str] = frozenset({
        MATCH_CREATED, MATCH_UPDATED, MATCH_DELETED, MATCH_RESCHEDULED,
        MATCH_SEATED, MATCH_STARTED, MATCH_FINISHED, MATCH_CONFIRMED,
        MATCH_ACKNOWLEDGED, MATCH_RESULT_RECORDED, MATCH_SEED_ROLLED,
        MATCH_STAGE_ASSIGNED, MATCH_STAGE_CLEARED, MATCH_STATIONS_ASSIGNED,
        MATCH_STREAM_CANDIDATE_SET, MATCH_STREAM_CANDIDATE_CLEARED,
        CREW_SIGNUP_CREATED, CREW_SIGNUP_REMOVED, CREW_APPROVAL_CHANGED,
        CREW_ACKNOWLEDGED,
        VOLUNTEER_ASSIGNED, VOLUNTEER_UNASSIGNED, VOLUNTEER_ACKNOWLEDGED,
        RACE_ROOM_CREATED, RACE_ROOM_OPENED, RACE_ROOM_STARTED,
        RACE_ROOM_FINISHED, RACE_ROOM_CANCELLED, RACE_ROOM_RESULT_RECORDED,
        SG_EPISODE_IMPORTED, SG_EPISODE_CANCELLED, SG_MATCH_AUTO_FINISHED,
        DISCORD_EVENT_CREATED, DISCORD_EVENT_UPDATED, DISCORD_EVENT_CANCELLED,
        SERVICE_HEALTH_ALERT,
    })

    # Wildcard a subscriber can register to receive every event.
    WILDCARD = '*'

    @classmethod
    def is_valid(cls, name: str) -> bool:
        """True for the wildcard or any registered event name."""
        return name == cls.WILDCARD or name in cls.ALL
