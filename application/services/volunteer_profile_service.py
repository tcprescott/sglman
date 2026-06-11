"""
Volunteer Profile Service - Business Logic Layer

Self-service opt-in available to any logged-in user, plus the assignable pool
used by the coordinator UI and the auto-scheduler.
"""

from datetime import datetime, timezone
from typing import List, Optional

from application.repositories import VolunteerProfileRepository
from application.services.audit_service import AuditActions, AuditService
from models import User, VolunteerProfile


class VolunteerProfileService:
    """Opt-in lifecycle and the assignable-volunteer pool."""

    def __init__(self):
        self.repository = VolunteerProfileRepository()
        self.audit_service = AuditService()

    async def get_or_create(self, user: User) -> VolunteerProfile:
        return await self.repository.get_or_create_for_user(user)

    async def is_opted_in(self, user: User) -> bool:
        profile = await self.repository.get_for_user(user)
        return bool(profile and profile.opted_in_at)

    async def opt_in(self, user: User, note: Optional[str] = None) -> VolunteerProfile:
        profile = await self.repository.get_or_create_for_user(user)
        if profile.opted_in_at is None:
            profile.opted_in_at = datetime.now(timezone.utc)
        if note is not None:
            profile.note = note
        await self.repository.save(profile)
        await self.audit_service.write_log(
            user, AuditActions.VOLUNTEER_OPTED_IN, {'note': note},
        )
        return profile

    async def opt_out(self, user: User) -> VolunteerProfile:
        profile = await self.repository.get_or_create_for_user(user)
        if profile.opted_in_at is not None:
            profile.opted_in_at = None
            await self.repository.save(profile)
            await self.audit_service.write_log(user, AuditActions.VOLUNTEER_OPTED_OUT, {})
        return profile

    async def update_note(self, user: User, note: Optional[str]) -> VolunteerProfile:
        profile = await self.repository.get_or_create_for_user(user)
        profile.note = note
        await self.repository.save(profile)
        return profile

    async def assignable_volunteers(self) -> List[User]:
        """All users who have opted in, ordered by name."""
        opted_in_ids = set(await self.repository.opted_in_user_ids())
        if not opted_in_ids:
            return []
        users = await User.filter(id__in=list(opted_in_ids))
        return sorted(users, key=lambda u: u.preferred_name.lower())
