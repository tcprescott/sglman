"""
Audit Service - Business Logic Layer

Handles audit logging for tracking user actions and system events.

All entries use namespaced action strings in the form ``verb.object`` (e.g.
``match.created``, ``user.role_granted``). Details are persisted as JSON so
the viewer can render them structurally and so they remain queryable.
"""

import json
from datetime import datetime
from typing import Any, Mapping, Optional

from application.events import Event, event_bus
from application.repositories.audit_repository import AuditRepository
from application.tenant_context import get_current_tenant_id
from models import AuditLog, User


# Canonical action verbs used across the codebase. Keeping them here gives
# one place to grep when reviewing audit coverage.
class AuditActions:
    # Match lifecycle and CRUD
    MATCH_CREATED = 'match.created'
    MATCH_UPDATED = 'match.updated'
    MATCH_DELETED = 'match.deleted'
    MATCH_CANCELLED = 'match.cancelled'
    MATCH_REQUESTED = 'match.requested'
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
    # A proctor flagging a recorded result as contested, and the flag being
    # resolved (explicitly, or implicitly by the admin confirming the match).
    MATCH_FLAGGED_FOR_REVIEW = 'match.flagged_for_review'
    MATCH_REVIEW_CLEARED = 'match.review_cleared'
    MATCH_WATCHER_ADDED = 'match.watcher_added'
    MATCH_WATCHER_REMOVED = 'match.watcher_removed'
    # A player offering their own match for stream, and taking the offer back.
    # Advisory: neither one touches is_stream_candidate.
    MATCH_STREAM_VOLUNTEERED = 'match.stream_volunteered'
    MATCH_STREAM_VOLUNTEER_WITHDRAWN = 'match.stream_volunteer_withdrawn'

    # Crew
    CREW_SIGNUP_CREATED = 'crew.signup_created'
    CREW_SIGNUP_REMOVED = 'crew.signup_removed'
    CREW_APPROVAL_CHANGED = 'crew.approval_changed'
    CREW_ACKNOWLEDGED = 'crew.acknowledged'

    # Tournament
    TOURNAMENT_CREATED = 'tournament.created'
    TOURNAMENT_UPDATED = 'tournament.updated'
    TOURNAMENT_DELETED = 'tournament.deleted'
    TOURNAMENT_ADMIN_GRANTED = 'tournament.admin_granted'
    TOURNAMENT_ADMIN_REVOKED = 'tournament.admin_revoked'
    TOURNAMENT_CREW_COORDINATOR_GRANTED = 'tournament.crew_coordinator_granted'
    TOURNAMENT_CREW_COORDINATOR_REVOKED = 'tournament.crew_coordinator_revoked'

    # User
    USER_CREATED = 'user.created'
    USER_PROVISIONED = 'user.provisioned'
    USER_PROFILE_UPDATED = 'user.profile_updated'
    USER_SELF_PROFILE_UPDATED = 'user.self_profile_updated'
    USER_ACTIVATION_CHANGED = 'user.activation_changed'
    USER_ROLE_GRANTED = 'user.role_granted'
    USER_ROLE_REVOKED = 'user.role_revoked'
    USER_TOURNAMENT_ENROLLMENT_UPDATED = 'user.tournament_enrollment_updated'

    # Discord role mapping / sync
    DISCORD_ROLE_MAPPING_ADDED = 'discord_role.mapping_added'
    DISCORD_ROLE_MAPPING_REMOVED = 'discord_role.mapping_removed'
    ROLE_DISCORD_SYNC_GRANTED = 'role.discord_sync_granted'
    ROLE_DISCORD_SYNC_REVOKED = 'role.discord_sync_revoked'
    ROLE_DISCORD_SYNC_BULK = 'role.discord_sync_bulk'
    # Tenant ↔ Discord server link (tenant-scoped; stamped with the tenant)
    DISCORD_SERVER_LINKED = 'discord.server_linked'
    DISCORD_SERVER_UNLINKED = 'discord.server_unlinked'

    # Discord Scheduled Events mirror (PR 8). The create/update/cancel rows are
    # written by the reconciler (system user on the worker, or a human on-demand);
    # the per-run summary/failure and the per-tournament settings edit are
    # audit-only plumbing.
    DISCORD_EVENT_CREATED = 'discord_event.created'
    DISCORD_EVENT_UPDATED = 'discord_event.updated'
    DISCORD_EVENT_CANCELLED = 'discord_event.cancelled'
    DISCORD_EVENT_SYNC_COMPLETED = 'discord_event.sync_completed'
    DISCORD_EVENT_SYNC_FAILED = 'discord_event.sync_failed'
    DISCORD_EVENT_SETTINGS_UPDATED = 'discord_event.settings_updated'

    # Station pool (the venue's physical seats)
    STATION_CREATED = 'station.created'
    STATION_UPDATED = 'station.updated'
    STATION_DELETED = 'station.deleted'

    # Stage
    STAGE_CREATED = 'stage.created'
    STAGE_UPDATED = 'stage.updated'
    STAGE_DELETED = 'stage.deleted'

    # System
    SYSTEM_CONFIG_UPDATED = 'system_config.updated'
    THEME_UPDATED = 'theme.updated'
    TIMEZONE_UPDATED = 'timezone.updated'
    USER_TIMEZONE_UPDATED = 'user.timezone_updated'

    # Triforce texts
    TRIFORCE_TEXT_SUBMITTED = 'triforce_text.submitted'
    TRIFORCE_TEXT_APPROVED = 'triforce_text.approved'
    TRIFORCE_TEXT_REJECTED = 'triforce_text.rejected'
    TRIFORCE_TEXT_DELETED = 'triforce_text.deleted'

    # API tokens
    APITOKEN_CREATED = 'apitoken.created'
    APITOKEN_REVOKED = 'apitoken.revoked'

    # In-app feedback
    FEEDBACK_SUBMITTED = 'feedback.submitted'
    FEEDBACK_REVIEWED = 'feedback.reviewed'
    FEEDBACK_REOPENED = 'feedback.reopened'

    # Equipment lending
    EQUIPMENT_CREATED = 'equipment.created'
    EQUIPMENT_UPDATED = 'equipment.updated'
    EQUIPMENT_DELETED = 'equipment.deleted'
    EQUIPMENT_CHECKED_OUT = 'equipment.checked_out'
    EQUIPMENT_CHECKED_IN = 'equipment.checked_in'

    # Player availability
    PLAYER_AVAILABILITY_UPDATED = 'player.availability_updated'

    # Challonge integration
    CHALLONGE_CONNECTED = 'challonge.connected'
    CHALLONGE_DISCONNECTED = 'challonge.disconnected'
    CHALLONGE_PLAYER_LINKED = 'challonge.player_linked'
    CHALLONGE_PLAYER_UNLINKED = 'challonge.player_unlinked'
    CHALLONGE_PLAYER_USERNAME_UPDATED = 'challonge.player_username_updated'
    CHALLONGE_TOURNAMENT_LINKED = 'challonge.tournament_linked'
    CHALLONGE_TOURNAMENT_UNLINKED = 'challonge.tournament_unlinked'
    CHALLONGE_BRACKET_SYNCED = 'challonge.bracket_synced'
    CHALLONGE_RESULT_PUSHED = 'challonge.result_pushed'
    CHALLONGE_WEBHOOK_SYNCED = 'challonge.webhook_synced'

    # Twitch integration
    TWITCH_LINKED = 'twitch.linked'
    TWITCH_UNLINKED = 'twitch.unlinked'

    # Racetime.gg identity linking
    RACETIME_LINKED = 'racetime.linked'
    RACETIME_UNLINKED = 'racetime.unlinked'

    # Racetime bots (platform-managed; CRUD + tenant grants are platform-level,
    # tenant=NULL) and their reusable per-tenant room profiles
    RACETIME_BOT_CREATED = 'racetime_bot.created'
    RACETIME_BOT_UPDATED = 'racetime_bot.updated'
    RACETIME_BOT_DELETED = 'racetime_bot.deleted'
    RACETIME_BOT_GRANTED = 'racetime_bot.granted'
    RACETIME_BOT_REVOKED = 'racetime_bot.revoked'
    RACE_ROOM_PROFILE_CREATED = 'race_room_profile.created'
    RACE_ROOM_PROFILE_UPDATED = 'race_room_profile.updated'
    RACE_ROOM_PROFILE_DELETED = 'race_room_profile.deleted'

    # Racetime bot runtime health (platform-level, tenant=NULL; audit-only —
    # written by the racetimebot/ connection loop as the system user)
    RACETIME_BOT_CONNECTED = 'racetime_bot.connected'
    RACETIME_BOT_DISCONNECTED = 'racetime_bot.disconnected'
    RACETIME_BOT_ERROR = 'racetime_bot.error'
    RACETIME_BOT_RESTARTED = 'racetime_bot.restarted'

    # Racetime race-room lifecycle (tenant-scoped; mirrored on the event bus as
    # ``race_room.*`` domain events — the system user is the actor)
    RACE_ROOM_CREATED = 'race_room.created'
    RACE_ROOM_OPENED = 'race_room.opened'
    RACE_ROOM_STARTED = 'race_room.started'
    RACE_ROOM_FINISHED = 'race_room.finished'
    RACE_ROOM_CANCELLED = 'race_room.cancelled'
    RACE_ROOM_RESULT_RECORDED = 'race_room.result_recorded'

    # Volunteer scheduling
    VOLUNTEER_OPTED_IN = 'volunteer.opted_in'
    VOLUNTEER_OPTED_OUT = 'volunteer.opted_out'
    VOLUNTEER_NOTE_UPDATED = 'volunteer.note_updated'
    VOLUNTEER_POSITION_CREATED = 'volunteer.position_created'
    VOLUNTEER_POSITION_UPDATED = 'volunteer.position_updated'
    VOLUNTEER_POSITION_DELETED = 'volunteer.position_deleted'
    VOLUNTEER_SHIFT_CREATED = 'volunteer.shift_created'
    VOLUNTEER_SHIFT_UPDATED = 'volunteer.shift_updated'
    VOLUNTEER_SHIFT_DELETED = 'volunteer.shift_deleted'
    VOLUNTEER_ASSIGNED = 'volunteer.assigned'
    VOLUNTEER_UNASSIGNED = 'volunteer.unassigned'
    VOLUNTEER_ACKNOWLEDGED = 'volunteer.acknowledged'
    VOLUNTEER_CHECKED_IN = 'volunteer.checked_in'
    VOLUNTEER_AVAILABILITY_UPDATED = 'volunteer.availability_updated'
    VOLUNTEER_DRAFT_GENERATED = 'volunteer.draft_generated'
    VOLUNTEER_DRAFT_CLEARED = 'volunteer.draft_cleared'
    VOLUNTEER_DRAFT_PUBLISHED = 'volunteer.draft_published'
    VOLUNTEER_RELEASED = 'volunteer.released'
    VOLUNTEER_SHIFTS_RESET = 'volunteer.shifts_reset'
    VOLUNTEER_QUALIFICATIONS_UPDATED = 'volunteer.qualifications_updated'
    VOLUNTEER_DATA_EXPORTED = 'volunteer.data_exported'

    # Web push (device notifications)
    WEB_PUSH_SUBSCRIBED = 'web_push.subscribed'
    WEB_PUSH_UNSUBSCRIBED = 'web_push.unsubscribed'
    WEB_PUSH_ROTATED = 'web_push.rotated'

    # Presets (seed-rolling settings)
    PRESET_CREATED = 'preset.created'
    PRESET_UPDATED = 'preset.updated'
    PRESET_DELETED = 'preset.deleted'
    PRESET_IMPORTED = 'preset.imported'
    RANDOMIZER_CREDENTIAL_SET = 'randomizer_credential.set'
    RANDOMIZER_CREDENTIAL_CLEARED = 'randomizer_credential.cleared'

    # SpeedGaming ETL (PR 7). Config CRUD is tenant-scoped, actor = a human
    # SYNC_ADMIN; the sync/import/skip/cancel/auto-finish rows are written by the
    # sync worker acting as the system user, tenant from ``tenant_scope``.
    SG_EVENT_LINK_CREATED = 'sg_sync.event_link_created'
    SG_EVENT_LINK_UPDATED = 'sg_sync.event_link_updated'
    SG_EVENT_LINK_DELETED = 'sg_sync.event_link_deleted'
    SG_SYNC_COMPLETED = 'sg_sync.completed'
    SG_SYNC_FAILED = 'sg_sync.failed'
    SG_EPISODE_IMPORTED = 'sg_sync.episode_imported'
    SG_EPISODE_SKIPPED = 'sg_sync.episode_skipped'
    SG_EPISODE_CANCELLED = 'sg_sync.episode_cancelled'
    SG_MATCH_AUTO_FINISHED = 'sg_sync.match_auto_finished'
    SG_PLACEHOLDER_CREATED = 'sg_sync.placeholder_created'
    SG_PLACEHOLDER_UPGRADED = 'sg_sync.placeholder_upgraded'

    # Async Qualifiers (PR 9). A peer aggregate of Tournament: qualifier/pool/
    # permalink authoring and the per-qualifier ``admins`` grants are tenant-
    # internal config (event-less); the run submitted/reviewed outcomes DO emit
    # events for subscribers (see EventType.ASYNC_QUALIFIER_RUN_*). The actor is
    # a human QUALIFIER_ADMIN for management/review and the running player for
    # start/submit/forfeit/reattempt.
    ASYNC_QUALIFIER_CREATED = 'async_qualifier.created'
    ASYNC_QUALIFIER_UPDATED = 'async_qualifier.updated'
    ASYNC_QUALIFIER_DELETED = 'async_qualifier.deleted'
    ASYNC_QUALIFIER_ADMIN_GRANTED = 'async_qualifier.admin_granted'
    ASYNC_QUALIFIER_ADMIN_REVOKED = 'async_qualifier.admin_revoked'
    ASYNC_QUALIFIER_POOL_CREATED = 'async_qualifier.pool_created'
    ASYNC_QUALIFIER_POOL_UPDATED = 'async_qualifier.pool_updated'
    ASYNC_QUALIFIER_POOL_DELETED = 'async_qualifier.pool_deleted'
    ASYNC_QUALIFIER_PERMALINK_ADDED = 'async_qualifier.permalink_added'
    ASYNC_QUALIFIER_PERMALINK_UPDATED = 'async_qualifier.permalink_updated'
    ASYNC_QUALIFIER_PERMALINK_DELETED = 'async_qualifier.permalink_deleted'
    ASYNC_QUALIFIER_RUN_STARTED = 'async_qualifier.run_started'
    ASYNC_QUALIFIER_RUN_SUBMITTED = 'async_qualifier.run_submitted'
    ASYNC_QUALIFIER_RUN_FORFEITED = 'async_qualifier.run_forfeited'
    # The worker forfeited a run the player drew and never came back to. Distinct
    # from a chosen forfeit because it is not something the runner did.
    ASYNC_QUALIFIER_RUN_EXPIRED = 'async_qualifier.run_expired'
    ASYNC_QUALIFIER_RUN_REATTEMPTED = 'async_qualifier.run_reattempted'
    # A reviewer voided someone else's run: distinct from the runner spending their
    # own allowance, because it bypasses that allowance entirely.
    ASYNC_QUALIFIER_REATTEMPT_GRANTED = 'async_qualifier.reattempt_granted'
    ASYNC_QUALIFIER_RUN_REVIEWED = 'async_qualifier.run_reviewed'
    # Async Qualifier live races (PR 10). Create/open/cancel are tenant-internal
    # scheduling (event-less); recording the finished race captures runs and DOES
    # emit an event (see EventType.ASYNC_QUALIFIER_LIVE_RACE_RECORDED).
    ASYNC_QUALIFIER_LIVE_RACE_CREATED = 'async_qualifier.live_race_created'
    ASYNC_QUALIFIER_LIVE_RACE_OPENED = 'async_qualifier.live_race_opened'
    ASYNC_QUALIFIER_LIVE_RACE_CANCELLED = 'async_qualifier.live_race_cancelled'
    ASYNC_QUALIFIER_LIVE_RACE_RECORDED = 'async_qualifier.live_race_recorded'

    # Native brackets (docs/plans/brackets-plan.md). Bracket/entrant lifecycle and the
    # match/advancement/stage events the lifecycle drives. Actor is a human STAFF
    # for management; the started/completed/advanced rows capture the graph
    # transitions the service performs.
    BRACKET_CREATED = 'bracket.created'
    # Covers every edit to a bracket's own definition — name/stage/config,
    # per-round display metadata and reseeding — with ``details`` naming which.
    BRACKET_UPDATED = 'bracket.updated'
    BRACKET_DELETED = 'bracket.deleted'
    BRACKET_STARTED = 'bracket.started'
    BRACKET_MATCH_COMPLETED = 'bracket.match_completed'
    BRACKET_GAME_SCHEDULED = 'bracket.game_scheduled'
    BRACKET_GAME_COMPLETED = 'bracket.game_completed'
    BRACKET_GAME_CANCELLED = 'bracket.game_cancelled'
    # A manually-scheduled Match attached to / detached from a matchup by staff,
    # as opposed to BRACKET_GAME_SCHEDULED's book-it-from-the-bracket path.
    BRACKET_GAME_LINKED = 'bracket.game_linked'
    BRACKET_GAME_UNLINKED = 'bracket.game_unlinked'
    # A cancelled/deleted Match handing its series slot back (D3), as opposed
    # to BRACKET_GAME_UNLINKED's deliberate staff detach.
    BRACKET_GAME_RELEASED = 'bracket.game_released'
    BRACKET_ADVANCED = 'bracket.advanced'
    BRACKET_COMPLETED = 'bracket.completed'
    BRACKET_STAGE_ADVANCED = 'bracket.stage_advanced'
    BRACKET_ENTRANT_ADDED = 'bracket.entrant_added'
    BRACKET_ENTRANT_DROPPED = 'bracket.entrant_dropped'
    BRACKET_ENTRANT_UPDATED = 'bracket.entrant_updated'
    # Per-stage participation, distinct from the tournament-level roster above:
    # who is enrolled in a stage decides who the generated graph contains.
    BRACKET_ENTRY_ADDED = 'bracket.entry_added'
    BRACKET_ENTRY_REMOVED = 'bracket.entry_removed'
    # Retiring an entry mid-stage is a different fact from un-enrolling one while
    # DRAFT: the played results stand and the field shrinks under way.
    BRACKET_ENTRY_RETIRED = 'bracket.entry_retired'
    BRACKET_CANCELLED = 'bracket.cancelled'

    # Webhooks
    WEBHOOK_CREATED = 'webhook.created'
    WEBHOOK_UPDATED = 'webhook.updated'
    WEBHOOK_DELETED = 'webhook.deleted'
    WEBHOOK_SECRET_REGENERATED = 'webhook.secret_regenerated'

    # Feature flags. Availability is a platform-level grant (super-admin on
    # /platform, tenant=NULL row, target tenant in details); the enable/disable
    # toggle is a tenant-level action by that community's STAFF (tenant-scoped).
    FEATURE_FLAG_AVAILABILITY_SET = 'feature_flag.availability_set'
    FEATURE_FLAG_ENABLED = 'feature_flag.enabled'
    FEATURE_FLAG_DISABLED = 'feature_flag.disabled'
    # Feature-flag groups (live tiers) — super-admin, platform-level (tenant=NULL).
    # Group CRUD and the per-tenant group assignment.
    FEATURE_GROUP_CREATED = 'feature_group.created'
    FEATURE_GROUP_UPDATED = 'feature_group.updated'
    FEATURE_GROUP_DELETED = 'feature_group.deleted'
    FEATURE_GROUP_ASSIGNED = 'feature_group.assigned'

    # Tenancy / platform (these audit rows carry tenant=NULL — platform-level)
    TENANT_CREATED = 'tenant.created'
    TENANT_UPDATED = 'tenant.updated'
    TENANT_DELETED = 'tenant.deleted'
    TENANT_MEMBER_ADDED = 'tenant.member_added'
    TENANT_MEMBER_REMOVED = 'tenant.member_removed'
    # The self-serve enrollment path. The request is written by someone who is
    # not yet in the tenant, so its audit row is stamped with the *target*
    # tenant rather than the requester's ambient one.
    TENANT_JOIN_REQUESTED = 'tenant.join_requested'
    TENANT_JOIN_APPROVED = 'tenant.join_approved'
    TENANT_JOIN_DENIED = 'tenant.join_denied'
    SUPER_ADMIN_GRANTED = 'platform.super_admin_granted'
    SUPER_ADMIN_REVOKED = 'platform.super_admin_revoked'


def _encode_details(details: Optional[Mapping[str, Any]]) -> Optional[str]:
    if details is None:
        return None
    return json.dumps(dict(details), default=str, sort_keys=True)


class AuditService:
    """Service for audit logging operations."""

    def __init__(self) -> None:
        self.repository = AuditRepository()

    async def list_logs(
        self,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        return await self.repository.list(
            start=start,
            end=end,
            user_id=user_id,
            action_contains=action_contains,
            limit=limit,
            offset=offset,
        )

    async def count_logs(
        self,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
    ) -> int:
        return await self.repository.count(
            start=start,
            end=end,
            user_id=user_id,
            action_contains=action_contains,
        )

    async def write_log(
        self,
        actor: User,
        action: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> AuditLog:
        """Write an audit log entry.

        Args:
            actor: The User performing the action. Required - if no actor is
                available the caller has a bug and should be fixed rather
                than the audit silently dropped.
            action: Namespaced action string (``verb.object``). Use a
                constant from :class:`AuditActions` where one exists.
            details: Optional structured context, JSON-encoded before
                storage. Use plain JSON-serializable values; datetimes and
                other objects fall back to ``str``.

        Raises:
            ValueError: If ``actor`` is None.
        """
        if actor is None:
            raise ValueError("AuditService.write_log requires an actor")

        # Snapshot the actor's identity into details so attribution survives a
        # later user deletion (AuditLog.user is ON DELETE SET NULL). getattr
        # keeps auditing resilient if the actor is a partial object.
        enriched: dict[str, Any] = dict(details) if details else {}
        actor_username = getattr(actor, 'username', None)
        if actor_username is not None:
            enriched.setdefault('actor_username', actor_username)
        actor_discord_id = getattr(actor, 'discord_id', None)
        if actor_discord_id is not None:
            enriched.setdefault('actor_discord_id', str(actor_discord_id))

        # Stamp the ambient tenant so the trail is per-tenant; NULL when the
        # action is platform-level (super-admin tenant CRUD on /platform, which
        # runs with no tenant context).
        return await AuditLog.create(
            tenant_id=get_current_tenant_id(),
            user=actor,
            action=action,
            details=_encode_details(enriched),
        )

    async def write_and_publish(
        self,
        actor: User,
        action: str,
        details: Optional[Mapping[str, Any]],
        event_type: str,
        *,
        event_extra: Optional[Mapping[str, Any]] = None,
        event_details: Optional[Mapping[str, Any]] = None,
    ) -> AuditLog:
        """Write an audit row, then fire the matching event on the in-process bus.

        Promotes the audit-then-publish pairing that services previously
        hand-rolled into one call. Publishing is synchronous, fire-and-forget, and
        never raises, so a subscriber failure cannot roll back the audit write.

        By default the event carries the same ``details`` and ``actor`` as the
        audit row. The two payloads legitimately diverge, though — the audit trail
        is tenant-internal and records *what a human did*, while the event is an
        **external contract** whose subscribers need routing keys (``user_id``,
        ``tournament_id``) that the audit row already implies from its own
        ``user`` FK and context. Two ways to express that:

        - ``event_extra`` — the common case: ``details`` plus these keys. Prefer
          this, because the shared keys stay written once.
        - ``event_details`` — a wholly independent event payload, for the rare
          case where the audit row carries detail the contract should *not*
          expose (an internal ``guild_id``, a verbose diff).

        Passing both is a caller bug: ``event_extra`` would silently do nothing.
        """
        if event_extra is not None and event_details is not None:
            raise ValueError(
                "write_and_publish takes event_extra or event_details, not both"
            )
        log = await self.write_log(actor, action, details)
        if event_details is not None:
            payload = dict(event_details)
        else:
            payload = dict(details) if details else {}
            if event_extra:
                payload.update(event_extra)
        event_bus.publish(Event.create(event_type, payload, actor))
        return log

    async def get_logs_for_user(
        self,
        user: User,
        limit: Optional[int] = None,
    ) -> list[AuditLog]:
        """Get audit logs for a specific user in the current tenant, most recent first."""
        query = AuditLog.filter(
            user=user, tenant_id=get_current_tenant_id()
        ).order_by('-created_at')
        if limit:
            query = query.limit(limit)
        return await query

    async def get_recent_logs(self, limit: int = 100) -> list[AuditLog]:
        """Get recent audit logs for the current tenant, across all users."""
        return await AuditLog.filter(
            tenant_id=get_current_tenant_id()
        ).order_by('-created_at').limit(limit).prefetch_related('user')
