"""
Crew Service - Business Logic Layer

Handles crew (commentator and tracker) related operations.
"""

import logging
from typing import Optional, Union

from tortoise.transactions import in_transaction

from application import match_events
from application.repositories import CommentatorRepository, TrackerRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services import discord_queue
from application.services.discord_service import DiscordService
from application.utils.discord_messages import crew_assignment_dm
from application.utils.timezone import format_eastern_display
from models import Commentator, Tracker, User


logger = logging.getLogger(__name__)


class CrewService:
    """Service for crew-related business operations."""

    def __init__(self) -> None:
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
        self.audit_service = AuditService()
        self.discord_service = DiscordService()

    async def get_crew_member_by_id(
        self,
        crew_id: int,
        crew_type: str,
    ) -> Optional[Union[Commentator, Tracker]]:
        if crew_type == 'commentator':
            return await self.commentator_repository.get_by_id(crew_id)
        elif crew_type == 'tracker':
            return await self.tracker_repository.get_by_id(crew_id)
        else:
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")

    async def update_crew_approval(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        approved: bool,
        actor: Optional[User] = None,
    ) -> Union[Commentator, Tracker]:
        if crew_type not in ('commentator', 'tracker'):
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")

        await crew_member.fetch_related('match', 'user', 'match__stream_room')
        await AuthService.ensure(
            await AuthService.can_approve_crew(actor, crew_member.match),
            f"User cannot approve {crew_type} signups for match {crew_member.match.id}",
        )

        # Refresh from DB to narrow the race window where two admins approve concurrently.
        await crew_member.refresh_from_db()
        was_approved = bool(crew_member.approved)
        was_acknowledged = crew_member.acknowledged_at is not None

        # No-op if state already matches — don't audit or DM for a click that didn't change anything.
        if was_approved == approved:
            return crew_member

        crew_member.approved = approved
        crew_member.approved_by = actor if approved else None
        if not approved:
            crew_member.acknowledged_at = None

        async with in_transaction():
            await crew_member.save()
            details = {
                'crew_type': crew_type,
                'crew_id': crew_member.id,
                'match_id': crew_member.match.id,
                'approved': approved,
            }
            if not approved and was_acknowledged:
                details['previously_acknowledged'] = True
            await self.audit_service.write_log(
                actor,
                AuditActions.CREW_APPROVAL_CHANGED,
                details,
            )

        if approved:
            await self._request_crew_acknowledgment(crew_member, crew_type)

        match_events.publish(crew_member.match.id)

        return crew_member

    async def approve_crew_member(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        actor: Optional[User] = None,
    ) -> Union[Commentator, Tracker]:
        return await self.update_crew_approval(crew_member, crew_type, approved=True, actor=actor)

    async def acknowledge_crew_assignment(
        self,
        crew_id: int,
        crew_type: str,
        user: User,
    ) -> Union[Commentator, Tracker]:
        """Mark a crew assignment as acknowledged by the crew member themselves.

        Only the assigned crew member may acknowledge their own assignment, and
        only after an admin has approved it. Already-acknowledged assignments
        are treated as a no-op so double-clicks don't surface confusing errors.
        """
        crew_member = await self.get_crew_member_by_id(crew_id, crew_type)
        if crew_member is None:
            raise ValueError(f"{crew_type.capitalize()} assignment not found.")

        await crew_member.fetch_related('user', 'match')

        if crew_member.user_id != user.id:
            raise ValueError("You can only acknowledge your own crew assignments.")

        if not crew_member.approved:
            raise ValueError(
                f"This {crew_type} assignment has not been approved yet."
            )

        if crew_member.acknowledged_at is not None:
            return crew_member

        async with in_transaction():
            if crew_type == 'commentator':
                crew_member = await self.commentator_repository.acknowledge(crew_member)
            else:
                crew_member = await self.tracker_repository.acknowledge(crew_member)

            await self.audit_service.write_log(
                user,
                AuditActions.CREW_ACKNOWLEDGED,
                {
                    'crew_type': crew_type,
                    'crew_id': crew_member.id,
                    'match_id': crew_member.match_id,
                },
            )

        match_events.publish(crew_member.match_id)

        return crew_member

    async def _request_crew_acknowledgment(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
    ) -> None:
        """Send a Discord DM asking the crew member to confirm their assignment.

        Best-effort: failures (DMs disabled, user not on Discord, bot offline,
        Discord library errors) are logged but never raise. The web
        acknowledgment button remains available regardless of DM delivery.
        """
        discord_id = getattr(crew_member.user, 'discord_id', None)
        if not discord_id:
            return

        match = crew_member.match
        players = await match.players.all().prefetch_related('user')
        message = crew_assignment_dm(
            crew_type=crew_type,
            match_title=match.title or None,
            scheduled_at_display=format_eastern_display(match.scheduled_at) if match.scheduled_at else '',
            stream_room_name=match.stream_room.name if match.stream_room else None,
            player_names=[p.user.preferred_name for p in players] if players else None,
        )
        discord_queue.enqueue(
            self.discord_service.send_dm_with_crew_acknowledgment_button(
                int(discord_id), message, crew_type, crew_member.id,
            )
        )
