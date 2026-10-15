"""Moving and swapping volunteers between shifts, for Admin → Shift Board.

Both are an ``unassign`` plus an ``assign`` on ``VolunteerScheduleService``,
so the DMs, audit rows and events are the ones those already send. What this
adds is running ``assign``'s hard checks first, so a refusal leaves the
schedule as it was rather than with the person removed.
"""

from typing import List, Optional, Tuple

from application.feature_flags import requires_feature
from application.services.auth_service import AuthService
from application.services.tenant_membership_service import TenantMembershipService
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from models import FeatureFlag, User, VolunteerAssignment, VolunteerShift


class VolunteerShiftMoveService:
    def __init__(self) -> None:
        self.schedule = VolunteerScheduleService()

    async def _require_free_for(
        self, user: User, shift: VolunteerShift, *, leaving_shift_id: Optional[int] = None,
    ) -> None:
        """The hard checks ``assign`` makes, run before a move or swap removes anyone,
        so a refusal leaves the schedule as it was. ``leaving_shift_id`` is the
        shift the person is coming off, which can't clash with where they're going."""
        if await self.schedule.assignment_repository.exists(shift.id, user.id):
            raise ValueError(f"{user.preferred_name} is already on this shift.")
        overlapping = await self.schedule.assignment_repository.overlapping_for_user(
            user.id, shift.starts_at, shift.ends_at, exclude_shift_id=shift.id,
        )
        if any(a.shift_id != leaving_shift_id for a in overlapping):  # type: ignore[attr-defined]
            raise ValueError(
                f"{user.preferred_name} is already assigned to an overlapping shift."
            )

    @requires_feature(FeatureFlag.VOLUNTEERS)
    async def move_assignment(
        self, actor: User, assignment: VolunteerAssignment, shift: VolunteerShift,
    ) -> Tuple[VolunteerAssignment, List[str]]:
        """Take a volunteer off their shift and put them on ``shift``.

        A draft moves as a draft and tells nobody. A published one gets the
        usual pair of DMs: off the old shift, and asked to confirm the new one.
        """
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can move volunteers.",
        )
        if shift.id == assignment.shift_id:  # type: ignore[attr-defined]
            raise ValueError("Pick a different shift to move them to.")
        user = assignment.user
        await TenantMembershipService.require_community_users([user.id], actor)
        await self._require_free_for(user, shift, leaving_shift_id=assignment.shift_id)  # type: ignore[attr-defined]
        draft = assignment.auto_generated
        await self.schedule.unassign(actor, assignment)
        return await self.schedule.assign(actor, shift, user, auto_generated=draft)

    @requires_feature(FeatureFlag.VOLUNTEERS)
    async def replace_assignment(
        self, actor: User, assignment: VolunteerAssignment, user: User,
    ) -> Tuple[VolunteerAssignment, List[str]]:
        """Swap ``user`` into the place ``assignment`` holds on its shift.

        The person coming off is told, the person going on is asked to confirm,
        and a draft place stays a draft.
        """
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can swap volunteers.",
        )
        if user.id == assignment.user_id:  # type: ignore[attr-defined]
            raise ValueError(f"{user.preferred_name} is already on this shift.")
        await TenantMembershipService.require_community_users([user.id], actor)
        shift = assignment.shift
        await self._require_free_for(user, shift)
        draft = assignment.auto_generated
        await self.schedule.unassign(actor, assignment)
        return await self.schedule.assign(actor, shift, user, auto_generated=draft)
