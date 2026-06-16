"""
Feedback Repository - Data Access Layer

Handles database operations for in-app feedback submissions.
"""

from typing import List, Optional

from models import Feedback, FeedbackCategory, FeedbackStatus, User


class FeedbackRepository:
    """Repository for feedback data access."""

    @staticmethod
    async def create(
        user: User,
        category: FeedbackCategory,
        message: str,
        page_url: str,
    ) -> Feedback:
        return await Feedback.create(
            user=user,
            category=category,
            message=message,
            page_url=page_url,
        )

    @staticmethod
    async def get_by_id(feedback_id: int) -> Optional[Feedback]:
        return await Feedback.get_or_none(id=feedback_id)

    @staticmethod
    async def list_recent(limit: int = 200) -> List[Feedback]:
        """Most recent submissions first, with the submitting user prefetched."""
        return await Feedback.all().order_by('-created_at').limit(limit).prefetch_related('user')

    @staticmethod
    async def set_status(feedback: Feedback, status: FeedbackStatus) -> None:
        feedback.status = status
        await feedback.save(update_fields=['status', 'updated_at'])
