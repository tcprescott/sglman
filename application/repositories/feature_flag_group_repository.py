"""Feature Flag Group Repository — platform-managed feature tiers.

A :class:`~models.FeatureFlagGroup` is **global** (like ``RacetimeBot``): one row
per named bundle of flags, managed by super-admins on ``/platform``. Never
tenant-scoped — groups are offered across tenants and a tenant points at one via
``Tenant.feature_group``.
"""

from typing import List, Optional

from models import FeatureFlagGroup, Tenant


class FeatureFlagGroupRepository:
    """CRUD + default-group resolution for feature-flag groups."""

    @staticmethod
    async def list_all() -> List[FeatureFlagGroup]:
        return await FeatureFlagGroup.all().order_by('name')

    @staticmethod
    async def get_by_id(group_id: int) -> Optional[FeatureFlagGroup]:
        return await FeatureFlagGroup.get_or_none(id=group_id)

    @staticmethod
    async def get_by_name(name: str) -> Optional[FeatureFlagGroup]:
        return await FeatureFlagGroup.get_or_none(name=name)

    @staticmethod
    async def get_default() -> Optional[FeatureFlagGroup]:
        """The single default group (live fallback for ungrouped tenants)."""
        return await FeatureFlagGroup.filter(is_default=True).first()

    @staticmethod
    async def create(**fields) -> FeatureFlagGroup:
        return await FeatureFlagGroup.create(**fields)

    @staticmethod
    async def update(group: FeatureFlagGroup, **fields) -> FeatureFlagGroup:
        for key, value in fields.items():
            setattr(group, key, value)
        await group.save()
        return group

    @staticmethod
    async def delete(group: FeatureFlagGroup) -> None:
        await group.delete()

    @staticmethod
    async def clear_default(exclude_id: Optional[int] = None) -> None:
        """Unset ``is_default`` on every group (except ``exclude_id``).

        Used to enforce the at-most-one-default invariant before flagging a new
        default.
        """
        query = FeatureFlagGroup.filter(is_default=True)
        if exclude_id is not None:
            query = query.exclude(id=exclude_id)
        await query.update(is_default=False)

    @staticmethod
    async def count_tenants(group_id: int) -> int:
        return await Tenant.filter(feature_group_id=group_id).count()
