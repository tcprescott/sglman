"""A community must not be able to hand out authority over the platform.

``SUPER_ADMIN`` is the one global role: its ``UserRole`` row carries
``tenant=NULL`` and ``AuthService.is_super_admin`` bypasses every per-tenant
gate. Every surface that grants roles is gated on ``can_grant_roles``, which is
``is_staff`` — and ``is_staff`` is evaluated inside the *actor's own* community.
So any check that stops at "is this person staff?" is asking a tenant-local
question about a platform-wide answer.

Two surfaces reached it, and both are covered here because they fail
differently: the Users tab grants immediately, while a Discord role mapping is a
standing grant that lands on someone else's next login. The mapping is also
tested from the stored row, not just the create call — a row written before the
guard existed, or restored from a backup, must not still pay out.
"""

import pytest

from application.services import UserService
from application.services.auth_service import AuthService
from application.services.discord.discord_role_mapping_service import (
    DiscordRoleMappingService,
)
from application.tenant_context import tenant_scope
from models import DiscordRoleMapping, Role, Tenant, User, UserRole


@pytest.fixture
async def community(db):
    """A community with its own STAFF — the attacker in every test below."""
    tenant = await Tenant.create(name='Small Club', slug='small-club', is_active=True)
    staff = await User.create(discord_id=880001, username='club-staff')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)
    return tenant, staff


class TestUsersTab:
    async def test_staff_cannot_grant_super_admin(self, community):
        tenant, staff = community
        target = await User.create(discord_id=880002, username='accomplice')
        with tenant_scope(tenant.id):
            assert await AuthService.is_staff(staff)
            with pytest.raises(PermissionError, match='platform role'):
                await UserService().grant_role(target, Role.SUPER_ADMIN, actor=staff)
        assert await UserRole.get_or_none(user=target, role=Role.SUPER_ADMIN) is None
        with tenant_scope(tenant.id):
            assert not await AuthService.is_super_admin(target)

    async def test_staff_cannot_grant_it_to_themselves(self, community):
        """The likelier shape: no accomplice needed, one checkbox."""
        tenant, staff = community
        with tenant_scope(tenant.id):
            with pytest.raises(PermissionError, match='platform role'):
                await UserService().grant_role(staff, Role.SUPER_ADMIN, actor=staff)
            assert not await AuthService.is_super_admin(staff)

    async def test_staff_cannot_revoke_an_existing_super_admin(self, community):
        """Otherwise any community could unseat the people who police it."""
        tenant, staff = community
        admin = await User.create(discord_id=880003, username='platform-admin')
        await UserRole.create(user=admin, role=Role.SUPER_ADMIN, tenant=None)
        with tenant_scope(tenant.id):
            with pytest.raises(PermissionError, match='platform role'):
                await UserService().revoke_role(admin, Role.SUPER_ADMIN, actor=staff)
            assert await AuthService.is_super_admin(admin)

    async def test_ordinary_roles_still_work(self, community):
        """The guard is on the one role, not on the surface."""
        tenant, staff = community
        target = await User.create(discord_id=880004, username='new-proctor')
        with tenant_scope(tenant.id):
            await UserService().grant_role(target, Role.PROCTOR, actor=staff)
            assert Role.PROCTOR in await AuthService.get_roles(target)


class TestDiscordRoleMapping:
    async def test_super_admin_cannot_be_mapped(self, community):
        tenant, staff = community
        with tenant_scope(tenant.id):
            with pytest.raises(ValueError, match='platform role'):
                await DiscordRoleMappingService().add_mapping(
                    guild_id=999,
                    discord_role_id=1234,
                    discord_role_name='Mods',
                    actor=staff,
                    app_role=Role.SUPER_ADMIN,
                )
        assert await DiscordRoleMapping.all().count() == 0

    async def test_a_stored_mapping_row_does_not_pay_out(self, community):
        """The row is what the sync reads, so the sync filters it too.

        A mapping written before the create-side guard existed would otherwise
        grant platform authority on the holder's next login, with nobody
        performing an action to notice.
        """
        tenant, staff = community
        victim_role_id = 4321
        with tenant_scope(tenant.id):
            await DiscordRoleMapping.create(
                tenant=tenant,
                guild_id=999,
                discord_role_id=victim_role_id,
                discord_role_name='Mods',
                app_role=Role.SUPER_ADMIN,
            )
            mappings = await DiscordRoleMappingService().mapping_repository.list_for_guild(999)
            grantable = set(Role.tenant_grantable())
            desired = {
                m.app_role for m in mappings
                if m.app_role in grantable and m.discord_role_id in {victim_role_id}
            }
        assert desired == set(), desired

    async def test_ordinary_roles_still_map(self, community):
        tenant, staff = community
        with tenant_scope(tenant.id):
            mapping = await DiscordRoleMappingService().add_mapping(
                guild_id=999,
                discord_role_id=1234,
                discord_role_name='Proctors',
                actor=staff,
                app_role=Role.PROCTOR,
            )
        assert mapping.app_role is Role.PROCTOR
