"""
Crew Service - Business Logic Layer

Handles crew (commentator and tracker) related operations.
"""

from typing import Optional, Union

from application.repositories import CommentatorRepository, TrackerRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Commentator, Tracker, User


class CrewService:
    """Service for crew-related business operations."""

    def __init__(self):
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
        self.audit_service = AuditService()

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

        await crew_member.fetch_related('match')
        await AuthService.ensure(
            await AuthService.can_approve_crew(actor, crew_member.match),
            f"User cannot approve {crew_type} signups for match {crew_member.match.id}",
        )

        crew_member.approved = approved
        crew_member.approved_by = actor if approved else None
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

        return updated

    async def approve_crew_member(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        actor: Optional[User] = None,
    ) -> Union[Commentator, Tracker]:
        return await self.update_crew_approval(crew_member, crew_type, approved=True, actor=actor)
