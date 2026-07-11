"""Tenant Repository — lookups for the tenancy machinery.

Intentionally **not** tenant-scoped: a tenant is resolved *before* any tenant
context exists (from the URL by the middleware, or from a Discord guild id by the
bot), and the ``/platform`` super-admin surface queries every tenant. So these
methods never call the ``_tenant`` scoping helpers.
"""

from typing import List, Optional

from models import Tenant


class TenantRepository:
    """Cross-tenant lookups + CRUD for :class:`~models.Tenant`."""

    @staticmethod
    async def get_by_id(tenant_id: int) -> Optional[Tenant]:
        return await Tenant.get_or_none(id=tenant_id)

    @staticmethod
    async def get_by_slug(slug: str) -> Optional[Tenant]:
        return await Tenant.get_or_none(slug=slug)

    @staticmethod
    async def get_by_domain(domain: str) -> Optional[Tenant]:
        return await Tenant.get_or_none(domain=domain)

    @staticmethod
    async def get_by_guild_id(guild_id: int) -> Optional[Tenant]:
        # Lowest id wins if two tenants somehow share a guild (shouldn't happen).
        return await Tenant.filter(discord_guild_id=guild_id).order_by('id').first()

    @staticmethod
    async def list_all() -> List[Tenant]:
        return await Tenant.all().order_by('name')

    @staticmethod
    async def slug_exists(slug: str, exclude_id: Optional[int] = None) -> bool:
        query = Tenant.filter(slug=slug)
        if exclude_id is not None:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    @staticmethod
    async def domain_exists(domain: str, exclude_id: Optional[int] = None) -> bool:
        query = Tenant.filter(domain=domain)
        if exclude_id is not None:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    @staticmethod
    async def create(**fields) -> Tenant:
        return await Tenant.create(**fields)

    @staticmethod
    async def update(tenant: Tenant, **fields) -> None:
        for key, value in fields.items():
            setattr(tenant, key, value)
        await tenant.save()

    @staticmethod
    async def delete(tenant: Tenant) -> None:
        await tenant.delete()
