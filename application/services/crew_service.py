"""
Crew Service - Business Logic Layer

Handles crew (commentator and tracker) related operations.
"""

from typing import Optional, Union

from application.repositories import CommentatorRepository, TrackerRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from models import Commentator, Tracker, User


class CrewService:
    """Service for crew-related business operations."""

    def __init__(self):
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

        await crew_member.fetch_related('match', 'user')
        await AuthService.ensure(
            await AuthService.can_approve_crew(actor, crew_member.match),
            f"User cannot approve {crew_type} signups for match {crew_member.match.id}",
        )

        was_approved = bool(crew_member.approved)
        crew_member.approved = approved
        crew_member.approved_by = actor if approved else None
        if not approved:
            crew_member.acknowledged_at = None
            crew_member.auto_acknowledged = False
        await crew_member.save()
        updated = crew_member

        await self.audit_service.write_log(
            actor,
            AuditActions.CREW_APPROVAL_CHANGED,
            {
                'crew_type': crew_type,
                'crew_id': crew_member.id,
                'match_id': crew_member.match.id,
                'approved': approved,
            },
        )

        if approved and not was_approved:
            await self._request_crew_acknowledgment(updated, crew_type)

        return updated

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
        only after an admin has approved it.
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
            raise ValueError(
                f"You have already acknowledged your {crew_type} assignment for Match ID {crew_member.match.id}."
            )

        if crew_type == 'commentator':
            await self.commentator_repository.acknowledge(crew_member, auto=False)
        else:
            await self.tracker_repository.acknowledge(crew_member, auto=False)

        await self.audit_service.write_log(
            user,
            AuditActions.CREW_ACKNOWLEDGED,
            {
                'crew_type': crew_type,
                'crew_id': crew_member.id,
                'match_id': crew_member.match.id,
            },
        )

        return crew_member

    async def _request_crew_acknowledgment(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
    ) -> None:
        """Send a Discord DM asking the crew member to confirm their assignment.

        Best-effort: failures (DMs disabled, user not on Discord, bot offline)
        do not raise. The web acknowledgment button remains available regardless.
        """
        discord_id = getattr(crew_member.user, 'discord_id', None)
        if not discord_id:
            return
        try:
            discord_user_id = int(discord_id)
        except (TypeError, ValueError):
            return
        message = (
            f"You've been approved as {crew_type} for Match ID {crew_member.match.id}. "
            "Please click below to acknowledge your assignment."
        )
        await self.discord_service.send_dm_with_crew_acknowledgment_button(
            discord_user_id, message, crew_type, crew_member.id,
        )
