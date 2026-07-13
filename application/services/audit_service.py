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
    MATCH_WATCHER_ADDED = 'match.watcher_added'
    MATCH_WATCHER_REMOVED = 'match.watcher_removed'

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

    # Stream room
    STREAM_ROOM_CREATED = 'stream_room.created'
    STREAM_ROOM_UPDATED = 'stream_room.updated'
    STREAM_ROOM_DELETED = 'stream_room.deleted'

    # System
    SYSTEM_CONFIG_UPDATED = 'system_config.updated'

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
    CHALLONGE_BRACKET_SYNCED = 'challonge.bracket_synced'
    CHALLONGE_RESULT_PUSHED = 'challonge.result_pushed'
    CHALLONGE_WEBHOOK_SYNCED = 'challonge.webhook_synced'

    # Twitch integration
    TWITCH_LINKED = 'twitch.linked'
    TWITCH_UNLINKED = 'twitch.unlinked'

    # Volunteer scheduling
    VOLUNTEER_OPTED_IN = 'volunteer.opted_in'
    VOLUNTEER_OPTED_OUT = 'volunteer.opted_out'
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
    VOLUNTEER_SHIFTS_RESET = 'volunteer.shifts_reset'
    VOLUNTEER_QUALIFICATIONS_UPDATED = 'volunteer.qualifications_updated'

    # Web push (device notifications)
    WEB_PUSH_SUBSCRIBED = 'web_push.subscribed'
    WEB_PUSH_UNSUBSCRIBED = 'web_push.unsubscribed'

    # Webhooks
    WEBHOOK_CREATED = 'webhook.created'
    WEBHOOK_UPDATED = 'webhook.updated'
    WEBHOOK_DELETED = 'webhook.deleted'
    WEBHOOK_SECRET_REGENERATED = 'webhook.secret_regenerated'

    # Tenancy / platform (these audit rows carry tenant=NULL — platform-level)
    TENANT_CREATED = 'tenant.created'
    TENANT_UPDATED = 'tenant.updated'
    TENANT_DELETED = 'tenant.deleted'
    TENANT_MEMBER_ADDED = 'tenant.member_added'
    TENANT_MEMBER_REMOVED = 'tenant.member_removed'
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
