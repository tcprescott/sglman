"""Tenant Service — tenancy machinery for resolution, CRUD, and membership.

Resolves a tenant from a URL slug (middleware), a custom domain, or a Discord
guild id (bot routing), and backs the ``/platform`` super-admin surface. Lookups
are cached in-process (one worker) and the cache is dropped on any write.

CRUD and grant operations are **super-admin gated** and run with *no* tenant
context (the platform surface), so they pass explicit ids to the repositories
rather than relying on the ambient tenant. Their audit rows are therefore
platform-level (``tenant=NULL``).
"""

import re
from typing import List, Optional

from application.repositories.tenant_repository import TenantRepository
from application.repositories.tenant_membership_repository import TenantMembershipRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Role, RoleSource, Tenant, User

_SLUG_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$')
# Top-level paths the platform surface owns; a tenant slug can never be one
# (slugs live under /t/<slug>, but reserving these avoids confusing links).
_RESERVED_SLUGS = {'platform', 'api', 'static', 'login', 'logout', 'oauth', 't', 'sw', 'health'}

# Simple per-process caches; invalidated wholesale on any write. Safe under the
# single-worker deployment. Keyed by the resolution inputs the request path uses.
_cache_by_slug: dict[str, Optional[Tenant]] = {}
_cache_by_guild: dict[int, Optional[Tenant]] = {}


def _clear_cache() -> None:
    _cache_by_slug.clear()
    _cache_by_guild.clear()


def slugify(name: str) -> str:
    """Best-effort URL-safe slug from a display name (for suggestions)."""
    slug = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    return slug[:63] or 'tenant'


class TenantService:
    """Tenant resolution, CRUD, membership, and super-admin grants."""

    # ---- resolution (cached, cross-tenant) --------------------------------

    @staticmethod
    async def get_by_id(tenant_id: int) -> Optional[Tenant]:
        return await TenantRepository.get_by_id(tenant_id)

    @staticmethod
    async def get_by_slug(slug: str) -> Optional[Tenant]:
        key = (slug or '').lower()
        if key in _cache_by_slug:
            return _cache_by_slug[key]
        tenant = await TenantRepository.get_by_slug(key)
        _cache_by_slug[key] = tenant
        return tenant

    @staticmethod
    async def get_by_domain(domain: str) -> Optional[Tenant]:
        return await TenantRepository.get_by_domain((domain or '').lower())

    @staticmethod
    async def get_by_guild_id(guild_id: int) -> Optional[Tenant]:
        if guild_id in _cache_by_guild:
            return _cache_by_guild[guild_id]
        tenant = await TenantRepository.get_by_guild_id(guild_id)
        _cache_by_guild[guild_id] = tenant
        return tenant

    @staticmethod
    async def list_tenants() -> List[Tenant]:
        return await TenantRepository.list_all()

    # ---- CRUD (super-admin gated, platform-level) -------------------------

    @staticmethod
    async def _validate_slug(slug: str, exclude_id: Optional[int] = None) -> str:
        slug = (slug or '').strip().lower()
        if not _SLUG_RE.match(slug):
            raise ValueError(
                'Slug must be 1-64 chars, lowercase letters/digits/hyphens, '
                'not starting or ending with a hyphen.'
            )
        if slug in _RESERVED_SLUGS:
            raise ValueError(f"'{slug}' is a reserved slug.")
        if await TenantRepository.slug_exists(slug, exclude_id=exclude_id):
            raise ValueError(f"A tenant with slug '{slug}' already exists.")
        return slug

    @staticmethod
    async def _validate_domain(domain: Optional[str], exclude_id: Optional[int] = None) -> Optional[str]:
        domain = (domain or '').strip().lower() or None
        if domain and await TenantRepository.domain_exists(domain, exclude_id=exclude_id):
            raise ValueError(f"A tenant with domain '{domain}' already exists.")
        return domain

    @staticmethod
    async def create_tenant(
        actor: User,
        *,
        name: str,
        slug: str,
        domain: Optional[str] = None,
        discord_guild_id: Optional[int] = None,
        is_active: bool = True,
        config: Optional[dict] = None,
    ) -> Tenant:
        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        name = (name or '').strip()
        if not name:
            raise ValueError('Tenant name is required.')
        slug = await TenantService._validate_slug(slug)
        domain = await TenantService._validate_domain(domain)

        tenant = await TenantRepository.create(
            name=name, slug=slug, domain=domain,
            discord_guild_id=discord_guild_id, is_active=is_active,
            config=config or {},
        )
        _clear_cache()
        await AuditService().write_log(
            actor, AuditActions.TENANT_CREATED,
            {'tenant_id': tenant.id, 'slug': slug, 'name': name},
        )
        return tenant

    @staticmethod
    async def update_tenant(actor: User, tenant: Tenant, **fields) -> Tenant:
        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        if 'slug' in fields:
            fields['slug'] = await TenantService._validate_slug(fields['slug'], exclude_id=tenant.id)
        if 'domain' in fields:
            fields['domain'] = await TenantService._validate_domain(fields['domain'], exclude_id=tenant.id)
        if 'name' in fields:
            fields['name'] = (fields['name'] or '').strip()
            if not fields['name']:
                raise ValueError('Tenant name is required.')

        await TenantRepository.update(tenant, **fields)
        _clear_cache()
        await AuditService().write_log(
            actor, AuditActions.TENANT_UPDATED,
            {'tenant_id': tenant.id, 'changed': sorted(fields.keys())},
        )
        return tenant

    # ---- membership -------------------------------------------------------

    @staticmethod
    async def is_member(user_id: int, tenant_id: int) -> bool:
        return await TenantMembershipRepository.is_member(user_id, tenant_id)

    @staticmethod
    async def add_member(actor: User, user: User, tenant_id: int) -> None:
        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        await TenantMembershipRepository.add(user, tenant_id)
        await AuditService().write_log(
            actor, AuditActions.TENANT_MEMBER_ADDED,
            {'tenant_id': tenant_id, 'user_id': user.id},
        )

    @staticmethod
    async def list_members(tenant_id: int) -> List:
        return await TenantMembershipRepository.list_for_tenant(tenant_id)

    @staticmethod
    async def list_memberships_for_user(user: User) -> List:
        return await TenantMembershipRepository.list_for_user(user)

    # ---- super-admin grants + per-tenant bootstrap ------------------------

    @staticmethod
    async def grant_super_admin(actor: User, user: User) -> None:
        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        # SUPER_ADMIN carries tenant=NULL; UserRoleRepository.add encodes that.
        await UserRoleRepository.add(user, Role.SUPER_ADMIN, granted_by=actor)
        await AuditService().write_log(
            actor, AuditActions.SUPER_ADMIN_GRANTED, {'user_id': user.id},
        )

    @staticmethod
    async def revoke_super_admin(actor: User, user: User) -> None:
        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        await UserRoleRepository.remove(user, Role.SUPER_ADMIN)
        await AuditService().write_log(
            actor, AuditActions.SUPER_ADMIN_REVOKED, {'user_id': user.id},
        )

    @staticmethod
    async def bootstrap_staff(actor: User, tenant_id: int, user: User) -> None:
        """Grant the first STAFF role in a tenant + membership, from /platform.

        Runs at platform level (no tenant context), so it stamps the tenant
        explicitly rather than through the ambient scope.
        """
        from application.tenant_context import tenant_scope

        await AuthService.ensure(await AuthService.is_super_admin(actor), 'Super-admin required')
        await TenantMembershipRepository.add(user, tenant_id)
        with tenant_scope(tenant_id):
            await UserRoleRepository.add(user, Role.STAFF, granted_by=actor, source=RoleSource.MANUAL)
        await AuditService().write_log(
            actor, AuditActions.USER_ROLE_GRANTED,
            {'tenant_id': tenant_id, 'user_id': user.id, 'role': Role.STAFF.value, 'bootstrap': True},
        )
