"""
Volunteer Profile Service - Business Logic Layer

Self-service opt-in for users who hold ``Role.VOLUNTEER``, plus the assignable
pool used by the coordinator UI and the auto-scheduler.
"""

from datetime import datetime, timezone
from typing import List, Optional

from application.repositories import VolunteerProfileRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Role, User, UserRole, VolunteerProfile


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
        await AuthService.ensure(
            await AuthService.is_volunteer(user),
            "You need the Volunteer role before you can opt in.",
        )
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
        """Users who hold ``Role.VOLUNTEER`` and have opted in, ordered by name."""
        opted_in_ids = set(await self.repository.opted_in_user_ids())
        if not opted_in_ids:
            return []
        role_ids = set(
            await UserRole.filter(role=Role.VOLUNTEER).values_list('user_id', flat=True)
        )
        eligible = opted_in_ids & role_ids
        if not eligible:
            return []
        users = await User.filter(id__in=list(eligible))
        return sorted(users, key=lambda u: u.preferred_name.lower())
