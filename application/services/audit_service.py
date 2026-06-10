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
    USER_PROFILE_UPDATED = 'user.profile_updated'
    USER_SELF_PROFILE_UPDATED = 'user.self_profile_updated'
    USER_ACTIVATION_CHANGED = 'user.activation_changed'
    USER_ROLE_GRANTED = 'user.role_granted'
    USER_ROLE_REVOKED = 'user.role_revoked'
    USER_TOURNAMENT_ENROLLMENT_UPDATED = 'user.tournament_enrollment_updated'

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


def _encode_details(details: Optional[Mapping[str, Any]]) -> Optional[str]:
    if details is None:
        return None
    return json.dumps(dict(details), default=str, sort_keys=True)


class AuditService:
    """Service for audit logging operations."""

    def __init__(self):
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

        return await AuditLog.create(
            user=actor,
            action=action,
            details=_encode_details(details),
        )

    async def get_logs_for_user(
        self,
        user: User,
        limit: Optional[int] = None,
    ) -> list[AuditLog]:
        """Get audit logs for a specific user, most recent first."""
        query = AuditLog.filter(user=user).order_by('-created_at')
        if limit:
            query = query.limit(limit)
        return await query

    async def get_recent_logs(self, limit: int = 100) -> list[AuditLog]:
        """Get recent audit logs across all users."""
        return await AuditLog.all().order_by('-created_at').limit(limit).prefetch_related('user')
