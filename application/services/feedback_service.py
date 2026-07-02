"""
Feedback Service - Business Logic Layer

Records in-app feedback from logged-in attendees and lets staff review it.
"""

from typing import List

from application.repositories.feedback_repository import FeedbackRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Feedback, FeedbackCategory, FeedbackStatus, User

PAGE_URL_MAX_LENGTH = 512


class FeedbackService:
    """Service for in-app feedback operations."""

    def __init__(self) -> None:
        self.repository = FeedbackRepository()
        self.audit_service = AuditService()

    @staticmethod
    def _coerce_category(category) -> FeedbackCategory:
        """Resolve an arbitrary category input to a valid enum, defaulting to OTHER."""
        try:
            return FeedbackCategory(category)
        except ValueError:
            return FeedbackCategory.OTHER

    async def submit(
        self,
        actor: User,
        category,
        message: str,
        page_url: str,
    ) -> Feedback:
        """Record a feedback submission from ``actor``."""
        message = (message or '').strip()
        if not message:
            raise ValueError("Feedback message is required.")

        category = self._coerce_category(category)
        page_url = (page_url or '')[:PAGE_URL_MAX_LENGTH]

        feedback = await self.repository.create(
            user=actor,
            category=category,
            message=message,
            page_url=page_url,
        )

        await self.audit_service.write_log(
            actor,
            AuditActions.FEEDBACK_SUBMITTED,
            {'feedback_id': feedback.id, 'category': category.value, 'page_url': page_url},
        )
        return feedback

    async def list_recent(self, limit: int = 200) -> List[Feedback]:
        return await self.repository.list_recent(limit)

    async def mark_reviewed(self, actor: User, feedback_id: int) -> Feedback:
        """Mark a submission reviewed. Admin-only."""
        await AuthService.ensure(
            await AuthService.can_view_admin(actor),
            "Only admins can review feedback.",
        )
        feedback = await self.repository.get_by_id(feedback_id)
        if feedback is None:
            raise ValueError("Feedback not found.")

        await self.repository.set_status(feedback, FeedbackStatus.REVIEWED)
        await self.audit_service.write_log(
            actor,
            AuditActions.FEEDBACK_REVIEWED,
            {'feedback_id': feedback.id},
        )
        return feedback
