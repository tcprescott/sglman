"""Station Repository - Data Access Layer

Handles database operations for the venue's station pool.
"""

from typing import List

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import Station


class StationRepository(TenantScopedRepository[Station]):
    """Repository for station pool data access."""

    model = Station

    @staticmethod
    async def get_all() -> List[Station]:
        """Every station this community has defined, in display order."""
        return await scoped(Station.all()).order_by('sort_order', 'name')

    @staticmethod
    async def get_active() -> List[Station]:
        """The stations currently available to assign, in display order."""
        return await scoped(Station.filter(is_active=True)).order_by('sort_order', 'name')

    @staticmethod
    async def active_names() -> set[str]:
        """The labels a station assignment may use.

        An empty set means this community has not defined a pool, which keeps the
        historical free-text behaviour.
        """
        return set(
            await scoped(Station.filter(is_active=True)).values_list('name', flat=True)
        )
