"""Canonical registry of domain event names published on the event bus.

Names are namespaced ``object.verb`` strings, mirroring the discipline of
:class:`~application.services.audit_service.AuditActions`. Unlike audit actions
these are an **external contract**: webhook subscribers pick from them and match
on them, so treat renames as breaking changes. Kept deliberately import-free of
the service layer so the events package stays cycle-free (like
``application.events.match_live``).
"""

from typing import FrozenSet


class EventType:
    # Match lifecycle
    MATCH_CREATED = 'match.created'
    MATCH_UPDATED = 'match.updated'
    MATCH_DELETED = 'match.deleted'
    MATCH_CANCELLED = 'match.cancelled'
    MATCH_RESCHEDULED = 'match.rescheduled'
    MATCH_SEATED = 'match.seated'
    MATCH_STARTED = 'match.started'
    MATCH_FINISHED = 'match.finished'
    MATCH_CONFIRMED = 'match.confirmed'
    MATCH_ACKNOWLEDGED = 'match.acknowledged'
    MATCH_RESULT_RECORDED = 'match.result_recorded'
    MATCH_SEED_ROLLED = 'match.seed_rolled'
    MATCH_SEED_ROLL_QUEUED = 'match.seed_roll_queued'
    MATCH_SEED_ROLL_FAILED = 'match.seed_roll_failed'
    MATCH_STAGE_ASSIGNED = 'match.stage_assigned'
    MATCH_STAGE_CLEARED = 'match.stage_cleared'
    MATCH_STATIONS_ASSIGNED = 'match.stations_assigned'
    MATCH_STREAM_CANDIDATE_SET = 'match.stream_candidate_set'
    MATCH_STREAM_CANDIDATE_CLEARED = 'match.stream_candidate_cleared'
    # A contested result is precisely what an alerting subscriber wants to hear
    # about, and the clear tells it the contest is over — so both are emitted,
    # unlike the tenant-internal station/venue actions.
    MATCH_FLAGGED_FOR_REVIEW = 'match.flagged_for_review'
    MATCH_REVIEW_CLEARED = 'match.review_cleared'
    # A player putting their own match forward for stream. Advisory — it says
    # nothing about whether the match will be streamed, only that its players
    # are willing. MATCH_STREAM_CANDIDATE_SET is still the decision.
    MATCH_STREAM_VOLUNTEERED = 'match.stream_volunteered'
    MATCH_STREAM_VOLUNTEER_WITHDRAWN = 'match.stream_volunteer_withdrawn'
    # A player asking staff to move or call off their match. Worth publishing
    # separately from the match.rescheduled an approval also emits: a subscriber
    # wants to hear that someone *asked*, not only that the schedule moved.
    MATCH_RESCHEDULE_REQUESTED = 'match.reschedule_requested'
    MATCH_RESCHEDULE_AGREED = 'match.reschedule_agreed'
    MATCH_RESCHEDULE_APPROVED = 'match.reschedule_approved'
    MATCH_RESCHEDULE_DECLINED = 'match.reschedule_declined'
    MATCH_RESCHEDULE_WITHDRAWN = 'match.reschedule_withdrawn'

    # Crew
    CREW_SIGNUP_CREATED = 'crew.signup_created'
    CREW_SIGNUP_REMOVED = 'crew.signup_removed'
    CREW_APPROVAL_CHANGED = 'crew.approval_changed'
    CREW_ACKNOWLEDGED = 'crew.acknowledged'

    # Volunteer
    VOLUNTEER_ASSIGNED = 'volunteer.assigned'
    VOLUNTEER_UNASSIGNED = 'volunteer.unassigned'
    VOLUNTEER_ACKNOWLEDGED = 'volunteer.acknowledged'
    # Deliberately distinct from VOLUNTEER_UNASSIGNED: a subscriber has to be able
    # to tell "the coordinator removed them" from "the volunteer dropped out",
    # because only the second one needs cover found.
    VOLUNTEER_RELEASED = 'volunteer.released'

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

    # Async Qualifiers (PR 9; mirrors AuditActions.ASYNC_QUALIFIER_RUN_*). A run
    # entering review (submitted) and a run being reviewed (approved/rejected) are
    # tenant-scoped domain events a subscriber can act on. Qualifier/pool/permalink
    # authoring and admin grants stay audit-only (tenant-internal config).
    ASYNC_QUALIFIER_RUN_SUBMITTED = 'async_qualifier.run_submitted'
    ASYNC_QUALIFIER_RUN_REVIEWED = 'async_qualifier.run_reviewed'
    # A run the expiry worker forfeited. Emitted (rather than audit-only) because
    # it changes a standing on nobody's instruction — a subscriber tracking
    # entrants needs to hear that one just went to zero.
    ASYNC_QUALIFIER_RUN_EXPIRED = 'async_qualifier.run_expired'

    # Async Qualifier live races (PR 10; mirrors AuditActions). A live race whose
    # entrants' results were captured into runs is a domain event a subscriber can
    # act on; create/open/cancel stay audit-only (tenant-internal scheduling).
    ASYNC_QUALIFIER_LIVE_RACE_RECORDED = 'async_qualifier.live_race_recorded'

    # Native brackets (mirrors AuditActions.BRACKET_*). Tenant-scoped domain
    # events a webhook subscriber can act on: a bracket created/started, a match
    # completed, an advancement, a bracket or stage completed. Published by the
    # bracket lifecycle as the acting STAFF user.
    BRACKET_CREATED = 'bracket.created'
    BRACKET_STARTED = 'bracket.started'
    BRACKET_MATCH_COMPLETED = 'bracket.match_completed'
    BRACKET_GAME_SCHEDULED = 'bracket.game_scheduled'
    BRACKET_GAME_COMPLETED = 'bracket.game_completed'
    BRACKET_GAME_CANCELLED = 'bracket.game_cancelled'
    BRACKET_GAME_LINKED = 'bracket.game_linked'
    BRACKET_GAME_UNLINKED = 'bracket.game_unlinked'
    BRACKET_GAME_RELEASED = 'bracket.game_released'
    BRACKET_ADVANCED = 'bracket.advanced'
    BRACKET_COMPLETED = 'bracket.completed'
    BRACKET_STAGE_ADVANCED = 'bracket.stage_advanced'
    BRACKET_ENTRANT_ADDED = 'bracket.entrant_added'
    BRACKET_ENTRANT_DROPPED = 'bracket.entrant_dropped'
    # The third roster mutation beside add/drop: which account an entrant *is*.
    # A subscriber mirroring the roster goes stale without it — the link is what
    # makes an entrant addressable at all.
    BRACKET_ENTRANT_UPDATED = 'bracket.entrant_updated'
    # A field shrinking mid-stage, and a stage abandoned outright — both change
    # what a subscriber should expect to be played, so both are announced.
    BRACKET_ENTRY_RETIRED = 'bracket.entry_retired'
    BRACKET_CANCELLED = 'bracket.cancelled'

    # Community membership (mirrors AuditActions.TENANT_MEMBER_*). Who belongs to
    # a community is exactly what an external roster or Discord-side subscriber
    # needs to mirror, so both directions are announced. Tenant CRUD itself stays
    # audit-only — it is a platform-level act, not something a tenant's own
    # webhook subscriber can see or act on.
    TENANT_MEMBER_ADDED = 'tenant.member_added'
    TENANT_MEMBER_REMOVED = 'tenant.member_removed'
    # The join-request lifecycle. A subscriber routing "someone wants in" to a
    # staff channel is the point; the decisions close the loop for it.
    TENANT_JOIN_REQUESTED = 'tenant.join_requested'
    TENANT_JOIN_APPROVED = 'tenant.join_approved'
    TENANT_JOIN_DENIED = 'tenant.join_denied'

    # Tournament rosters. Split by direction because a subscriber mirroring a
    # roster — a Discord role bot, an external bracket tool — needs to know which
    # way it moved; the audit trail keeps one action for both, since there it is
    # one fact reached from four screens. Payload carries ``tournament_id`` and
    # ``user_id`` as routing keys.
    TOURNAMENT_ENROLLED = 'tournament.enrolled'
    TOURNAMENT_WITHDRAWN = 'tournament.withdrawn'

    # Every published event name; drives the webhook UI multiselect + validation.
    ALL: FrozenSet[str] = frozenset({
        MATCH_CREATED, MATCH_UPDATED, MATCH_DELETED, MATCH_CANCELLED, MATCH_RESCHEDULED,
        MATCH_SEATED, MATCH_STARTED, MATCH_FINISHED, MATCH_CONFIRMED,
        MATCH_ACKNOWLEDGED, MATCH_RESULT_RECORDED, MATCH_SEED_ROLLED,
        MATCH_SEED_ROLL_QUEUED, MATCH_SEED_ROLL_FAILED,
        MATCH_STAGE_ASSIGNED, MATCH_STAGE_CLEARED, MATCH_STATIONS_ASSIGNED,
        MATCH_STREAM_CANDIDATE_SET, MATCH_STREAM_CANDIDATE_CLEARED,
        MATCH_FLAGGED_FOR_REVIEW, MATCH_REVIEW_CLEARED,
        MATCH_STREAM_VOLUNTEERED, MATCH_STREAM_VOLUNTEER_WITHDRAWN,
        MATCH_RESCHEDULE_REQUESTED, MATCH_RESCHEDULE_AGREED,
        MATCH_RESCHEDULE_APPROVED, MATCH_RESCHEDULE_DECLINED,
        MATCH_RESCHEDULE_WITHDRAWN,
        CREW_SIGNUP_CREATED, CREW_SIGNUP_REMOVED, CREW_APPROVAL_CHANGED,
        CREW_ACKNOWLEDGED,
        VOLUNTEER_ASSIGNED, VOLUNTEER_UNASSIGNED, VOLUNTEER_ACKNOWLEDGED,
        VOLUNTEER_RELEASED,
        RACE_ROOM_CREATED, RACE_ROOM_OPENED, RACE_ROOM_STARTED,
        RACE_ROOM_FINISHED, RACE_ROOM_CANCELLED, RACE_ROOM_RESULT_RECORDED,
        SG_EPISODE_IMPORTED, SG_EPISODE_CANCELLED, SG_MATCH_AUTO_FINISHED,
        DISCORD_EVENT_CREATED, DISCORD_EVENT_UPDATED, DISCORD_EVENT_CANCELLED,
        SERVICE_HEALTH_ALERT,
        ASYNC_QUALIFIER_RUN_SUBMITTED, ASYNC_QUALIFIER_RUN_REVIEWED,
        ASYNC_QUALIFIER_RUN_EXPIRED,
        ASYNC_QUALIFIER_LIVE_RACE_RECORDED,
        BRACKET_CREATED, BRACKET_STARTED, BRACKET_MATCH_COMPLETED,
        BRACKET_ADVANCED, BRACKET_COMPLETED, BRACKET_STAGE_ADVANCED,
        BRACKET_ENTRANT_ADDED, BRACKET_ENTRANT_DROPPED, BRACKET_ENTRANT_UPDATED,
        BRACKET_ENTRY_RETIRED, BRACKET_CANCELLED,
        BRACKET_GAME_SCHEDULED, BRACKET_GAME_COMPLETED, BRACKET_GAME_CANCELLED,
        BRACKET_GAME_LINKED, BRACKET_GAME_UNLINKED, BRACKET_GAME_RELEASED,
        TENANT_MEMBER_ADDED, TENANT_MEMBER_REMOVED,
        TENANT_JOIN_REQUESTED, TENANT_JOIN_APPROVED, TENANT_JOIN_DENIED,
        TOURNAMENT_ENROLLED, TOURNAMENT_WITHDRAWN,
    })

    # Wildcard a subscriber can register to receive every event.
    WILDCARD = '*'

    @classmethod
    def is_valid(cls, name: str) -> bool:
        """True for the wildcard or any registered event name."""
        return name == cls.WILDCARD or name in cls.ALL
