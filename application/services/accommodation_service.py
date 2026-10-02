"""
Accommodation Service - Business Logic Layer

ADA accommodation requests: a member ticks a box on their profile (with
optional details), and the community's STAFF track each request through
``NEW → ACKNOWLEDGED → ARRANGED`` with their own private notes.

Who sees what is the whole design. The requester sees their own checkbox,
details and status, never the staff notes. STAFF (and super-admins, via
``AuthService.is_staff``) see everything for their community. Nobody else does,
and no free text leaves the app: audit rows carry ids and status only, nothing
is published on the event bus, and there is no REST or MCP surface.

Gated by :attr:`~models.FeatureFlag.ADA_ACCOMMODATIONS`.
"""

from typing import Dict, Iterable, List, Optional, Set

from application.errors import require_found
from application.feature_flags import requires_feature
from application.repositories.accommodation_repository import AccommodationRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.feature_flag_service import FeatureFlagService
from application.services.tenant_membership_service import TenantMembershipService
from models import AccommodationRequest, AccommodationStatus, FeatureFlag, Role, User

DETAILS_MAX_LENGTH = 2000
STAFF_NOTES_MAX_LENGTH = 4000

OPEN_STATUSES = (
    AccommodationStatus.NEW,
    AccommodationStatus.ACKNOWLEDGED,
    AccommodationStatus.ARRANGED,
)


def _clean(text: Optional[str], limit: int, what: str) -> Optional[str]:
    text = (text or '').strip()
    if len(text) > limit:
        raise ValueError(f'{what} must be {limit} characters or fewer.')
    return text or None


class AccommodationService:
    """Service for ADA accommodation requests."""

    def __init__(self) -> None:
        self.repository = AccommodationRepository()
        self.audit_service = AuditService()

    @staticmethod
    async def _ensure_staff(actor: Optional[User]) -> None:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            'Only staff can view accommodation requests.',
        )

    # --- the requester's side ---------------------------------------------

    @requires_feature(FeatureFlag.ADA_ACCOMMODATIONS)
    async def get_mine(self, actor: User) -> Optional[AccommodationRequest]:
        """``actor``'s own request in this community, withdrawn or not."""
        return await self.repository.get_for_user(actor)

    @requires_feature(FeatureFlag.ADA_ACCOMMODATIONS)
    async def set_my_request(
        self, actor: User, requested: bool, details: Optional[str] = None,
    ) -> Optional[AccommodationRequest]:
        """Ask for accommodation, change the details, or withdraw.

        Withdrawing clears the details but keeps the row and its staff notes.
        Asking again after a withdrawal, or changing the details on a request
        staff already acknowledged or arranged, puts it back to ``NEW`` so the
        change is not missed. Re-saving identical details is a no-op.
        """
        existing = await self.repository.get_for_user(actor)

        if not requested:
            if existing is None or existing.status is AccommodationStatus.WITHDRAWN:
                return existing
            await self.repository.update(existing, status=AccommodationStatus.WITHDRAWN, details=None)
            await self._audit(actor, AuditActions.ACCOMMODATION_WITHDRAWN, existing)
            return existing

        details = _clean(details, DETAILS_MAX_LENGTH, 'Accommodation details')

        if existing is None:
            if not await TenantMembershipService().is_member(actor):
                raise ValueError('Join this community before requesting accommodation.')
            created = await self.repository.create(user=actor, details=details)
            await self._audit(actor, AuditActions.ACCOMMODATION_REQUESTED, created)
            return created

        if existing.status is AccommodationStatus.WITHDRAWN:
            await self.repository.update(existing, status=AccommodationStatus.NEW, details=details)
            await self._audit(actor, AuditActions.ACCOMMODATION_REQUESTED, existing)
            return existing

        if details == existing.details:
            return existing
        await self.repository.update(existing, status=AccommodationStatus.NEW, details=details)
        await self._audit(actor, AuditActions.ACCOMMODATION_UPDATED, existing)
        return existing

    # --- staff side -------------------------------------------------------

    @requires_feature(FeatureFlag.ADA_ACCOMMODATIONS)
    async def list_requests(
        self, actor: User, include_withdrawn: bool = False,
    ) -> List[AccommodationRequest]:
        await self._ensure_staff(actor)
        statuses = list(OPEN_STATUSES)
        if include_withdrawn:
            statuses.append(AccommodationStatus.WITHDRAWN)
        return await self.repository.list_by_status(statuses)

    @requires_feature(FeatureFlag.ADA_ACCOMMODATIONS)
    async def requesting_user_ids(self, actor: User) -> Set[int]:
        """Members with an open (not withdrawn) request, for the Users-tab filter."""
        await self._ensure_staff(actor)
        return await self.repository.user_ids_with_status(OPEN_STATUSES)

    # feature-gate: exempt — soft integration point; see the docstring below.
    async def arranged_notes_for(
        self, actor: Optional[User], user_ids: Iterable[int],
    ) -> Dict[int, str]:
        """Staff notes for players whose request is ``ARRANGED``, keyed by user id.

        Feeds the accessibility icon on the admin Schedule and Proctor Station
        boards, which are not themselves flag-gated and are also open to roles
        that must not see this (tournament admins, stream managers). So it is
        soft: it returns ``{}`` rather than raising when the feature is off or
        the viewer is neither STAFF nor a PROCTOR, and every board can call it
        unconditionally. A proctor gets the staff notes only, never the
        requester's own details. A note may be ``''`` (arranged, no note yet).
        """
        ids = {i for i in user_ids if i is not None}
        if not ids or actor is None:
            return {}
        if not await FeatureFlagService().is_enabled(FeatureFlag.ADA_ACCOMMODATIONS):
            return {}
        if not (await AuthService.is_staff(actor) or await AuthService.has_role(actor, Role.PROCTOR)):
            return {}
        requests = await self.repository.list_for_users(ids, AccommodationStatus.ARRANGED)
        return {r.user_id: r.staff_notes or '' for r in requests}

    @requires_feature(FeatureFlag.ADA_ACCOMMODATIONS)
    async def update_request(
        self,
        actor: User,
        request_id: int,
        status: AccommodationStatus,
        staff_notes: Optional[str],
    ) -> AccommodationRequest:
        """Set a request's status and staff notes in one save.

        Staff cannot withdraw on someone's behalf (only the requester can), and
        cannot move a withdrawn request out of ``WITHDRAWN``: reopening is the
        requester ticking the box again. Notes stay editable either way.
        """
        await self._ensure_staff(actor)
        request = require_found(await self.repository.get_by_id(request_id), 'Accommodation request')
        status = AccommodationStatus(status)
        staff_notes = _clean(staff_notes, STAFF_NOTES_MAX_LENGTH, 'Staff notes')

        if request.status is AccommodationStatus.WITHDRAWN:
            if status is not AccommodationStatus.WITHDRAWN:
                raise ValueError('This request was withdrawn. It reopens when the member asks again.')
        elif status is AccommodationStatus.WITHDRAWN:
            raise ValueError('Only the member can withdraw their request.')

        status_changed = status is not request.status
        notes_changed = staff_notes != request.staff_notes
        if not (status_changed or notes_changed):
            return request

        previous = request.status
        await self.repository.update(request, status=status, staff_notes=staff_notes)
        if status_changed:
            await self._audit(
                actor, AuditActions.ACCOMMODATION_STATUS_CHANGED, request,
                previous_status=previous.value,
            )
        if notes_changed:
            await self._audit(actor, AuditActions.ACCOMMODATION_NOTES_UPDATED, request)
        return request

    async def _audit(
        self, actor: User, action: str, request: AccommodationRequest, **extra: str,
    ) -> None:
        await self.audit_service.write_log(
            actor,
            action,
            {
                'request_id': request.id,
                'user_id': request.user_id,
                'status': request.status.value,
                **extra,
            },
        )
