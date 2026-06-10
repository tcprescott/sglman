"""
VolunteerProfile Repository - Data Access Layer

Per-user opt-in records for onsite volunteering.
"""

from typing import List, Optional

from models import User, VolunteerProfile


class VolunteerProfileRepository:
    """Repository for volunteer opt-in profiles."""

    @staticmethod
    async def get_for_user(user: User) -> Optional[VolunteerProfile]:
        return await VolunteerProfile.get_or_none(user=user)

    @staticmethod
    async def get_or_create_for_user(user: User) -> VolunteerProfile:
        profile, _ = await VolunteerProfile.get_or_create(user=user)
        return profile

    @staticmethod
    async def save(profile: VolunteerProfile) -> VolunteerProfile:
        await profile.save()
        return profile

    @staticmethod
    async def list_opted_in() -> List[VolunteerProfile]:
        """All profiles that have opted in, with the user prefetched."""
        return await (
            VolunteerProfile.filter(opted_in_at__isnull=False)
            .prefetch_related('user')
        )

    @staticmethod
    async def opted_in_user_ids() -> List[int]:
        return await (
            VolunteerProfile.filter(opted_in_at__isnull=False)
            .values_list('user_id', flat=True)
        )
