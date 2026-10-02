"""
Accommodation Repository - Data Access Layer

Handles database operations for ADA accommodation requests.
"""

from typing import Iterable, List, Optional, Set

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import AccommodationRequest, AccommodationStatus, User


class AccommodationRepository(TenantScopedRepository[AccommodationRequest]):
    """Repository for accommodation request data access."""

    model = AccommodationRequest

    @staticmethod
    async def get_by_id(obj_id: int) -> Optional[AccommodationRequest]:
        return await AccommodationRequest.get_or_none(
            id=obj_id, tenant_id=current_tenant_id(),
        ).prefetch_related('user')

    @staticmethod
    async def get_for_user(user: User) -> Optional[AccommodationRequest]:
        return await AccommodationRequest.get_or_none(user_id=user.id, tenant_id=current_tenant_id())

    @staticmethod
    async def list_by_status(statuses: Iterable[AccommodationStatus]) -> List[AccommodationRequest]:
        """Requests in any of ``statuses``, oldest first so the queue reads in order asked."""
        return await scoped(
            AccommodationRequest.filter(status__in=list(statuses))
        ).order_by('created_at').prefetch_related('user')

    @staticmethod
    async def list_for_users(
        user_ids: Iterable[int], status: AccommodationStatus,
    ) -> List[AccommodationRequest]:
        return await scoped(
            AccommodationRequest.filter(user_id__in=list(user_ids), status=status)
        )

    @staticmethod
    async def user_ids_with_status(statuses: Iterable[AccommodationStatus]) -> Set[int]:
        rows = await scoped(
            AccommodationRequest.filter(status__in=list(statuses))
        ).values_list('user_id', flat=True)
        return {int(r) for r in rows}  # type: ignore[call-overload]
