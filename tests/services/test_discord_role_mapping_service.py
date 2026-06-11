"""Unit tests for DiscordRoleMappingService.

Covers the login-time role sync (grant/revoke/full-sync semantics, the
manual-vs-discord source guard, and fail-open behaviour) plus the mapping
CRUD permission gates and audit logging.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services import discord_role_mapping_service as drms
from application.services.discord_role_mapping_service import DiscordRoleMappingService
from models import Role, RoleSource


def make_service():
    svc = object.__new__(DiscordRoleMappingService)
    svc.mapping_repository = MagicMock()
    svc.mapping_repository.list_for_guild = AsyncMock(return_value=[])
    svc.mapping_repository.get_match = AsyncMock(return_value=None)
    svc.mapping_repository.get_by_id = AsyncMock(return_value=None)
    svc.mapping_repository.create = AsyncMock()
    svc.mapping_repository.delete = AsyncMock()
    svc.role_repository = MagicMock()
    svc.role_repository.add = AsyncMock()
    svc.role_repository.remove = AsyncMock()
    svc.role_repository.list_for_user_by_source = AsyncMock(return_value=[])
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_user(user_id=1, discord_id=123):
    return SimpleNamespace(id=user_id, discord_id=discord_id)


def mapping(discord_role_id, app_role):
    return SimpleNamespace(discord_role_id=discord_role_id, app_role=app_role)


@pytest.fixture
def patch_deps(monkeypatch):
    """Helper to configure the module-level dependencies of sync_user_roles."""

    def _apply(*, guild_id=42, member_result=(True, set()), current_roles=set()):
        monkeypatch.setattr(
            drms.SystemConfigService, 'get_discord_sync_guild_id',
            AsyncMock(return_value=guild_id),
        )
        monkeypatch.setattr(
            drms.AuthService, 'get_roles', AsyncMock(return_value=set(current_roles)),
        )
        fake_discord = SimpleNamespace(
            get_member_role_ids=AsyncMock(return_value=member_result)
        )
        monkeypatch.setattr(drms, 'DiscordService', lambda: fake_discord)

    return _apply


# ---------------------------------------------------------------------------
# sync_user_roles
# ---------------------------------------------------------------------------


class TestSyncUserRoles:
    async def test_grants_mapped_role(self, patch_deps):
        patch_deps(member_result=(True, {111}), current_roles=set())
        svc = make_service()
        svc.mapping_repository.list_for_guild = AsyncMock(
            return_value=[mapping(111, Role.PROCTOR)]
        )
        user = make_user()

        summary = await svc.sync_user_roles(user)

        svc.role_repository.add.assert_awaited_once_with(
            user, Role.PROCTOR, granted_by=None, source=RoleSource.DISCORD
        )
        svc.role_repository.remove.assert_not_awaited()
        assert summary['granted'] == ['proctor']
        assert summary['revoked'] == []
        action = svc.audit_service.write_log.await_args.args[1]
        assert action == 'role.discord_sync_granted'

    async def test_revokes_discord_role_when_absent(self, patch_deps):
        # Member no longer has the Discord role; mapping still exists.
        patch_deps(member_result=(True, set()), current_roles={Role.PROCTOR})
        svc = make_service()
        svc.mapping_repository.list_for_guild = AsyncMock(
            return_value=[mapping(111, Role.PROCTOR)]
        )
        svc.role_repository.list_for_user_by_source = AsyncMock(
            return_value=[SimpleNamespace(role=Role.PROCTOR)]
        )
        user = make_user()

        summary = await svc.sync_user_roles(user)

        svc.role_repository.remove.assert_awaited_once_with(user, Role.PROCTOR)
        svc.role_repository.add.assert_not_awaited()
        assert summary['revoked'] == ['proctor']
        action = svc.audit_service.write_log.await_args.args[1]
        assert action == 'role.discord_sync_revoked'

    async def test_manual_role_never_revoked(self, patch_deps):
        # User holds STAFF manually; it is absent from Discord and from the
        # discord-sourced rows, so it must be left untouched.
        patch_deps(member_result=(True, set()), current_roles={Role.STAFF})
        svc = make_service()
        svc.mapping_repository.list_for_guild = AsyncMock(
            return_value=[mapping(999, Role.STAFF)]
        )
        svc.role_repository.list_for_user_by_source = AsyncMock(return_value=[])
        user = make_user()

        summary = await svc.sync_user_roles(user)

        svc.role_repository.remove.assert_not_awaited()
        svc.role_repository.add.assert_not_awaited()
        assert summary['revoked'] == []
        assert summary['granted'] == []

    async def test_no_guild_configured_is_noop(self, patch_deps):
        patch_deps(guild_id=None)
        svc = make_service()
        user = make_user()

        summary = await svc.sync_user_roles(user)

        assert summary['skipped'] == 'no_guild_configured'
        svc.role_repository.add.assert_not_awaited()
        svc.role_repository.remove.assert_not_awaited()

    async def test_discord_unavailable_fails_open(self, patch_deps):
        patch_deps(member_result=(False, 'bot not ready'), current_roles={Role.PROCTOR})
        svc = make_service()
        svc.mapping_repository.list_for_guild = AsyncMock(
            return_value=[mapping(111, Role.PROCTOR)]
        )
        svc.role_repository.list_for_user_by_source = AsyncMock(
            return_value=[SimpleNamespace(role=Role.PROCTOR)]
        )
        user = make_user()

        summary = await svc.sync_user_roles(user)

        assert summary['skipped'] == 'discord_unavailable'
        svc.role_repository.add.assert_not_awaited()
        svc.role_repository.remove.assert_not_awaited()

    async def test_already_held_role_not_regranted(self, patch_deps):
        patch_deps(member_result=(True, {111}), current_roles={Role.PROCTOR})
        svc = make_service()
        svc.mapping_repository.list_for_guild = AsyncMock(
            return_value=[mapping(111, Role.PROCTOR)]
        )
        svc.role_repository.list_for_user_by_source = AsyncMock(
            return_value=[SimpleNamespace(role=Role.PROCTOR)]
        )
        user = make_user()

        summary = await svc.sync_user_roles(user)

        svc.role_repository.add.assert_not_awaited()
        svc.role_repository.remove.assert_not_awaited()
        assert summary == {'granted': [], 'revoked': [], 'skipped': None}


# ---------------------------------------------------------------------------
# add_mapping / remove_mapping
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    monkeypatch.setattr(drms.AuthService, 'can_grant_roles', allow)
    monkeypatch.setattr(drms.AuthService, 'ensure', noop_ensure)


class TestMappingCrud:
    async def test_add_mapping_creates_and_audits(self):
        svc = make_service()
        actor = make_user()

        await svc.add_mapping(
            guild_id=42, discord_role_id=111, discord_role_name='Mods',
            app_role=Role.PROCTOR, actor=actor,
        )

        svc.mapping_repository.create.assert_awaited_once_with(42, 111, 'Mods', Role.PROCTOR)
        action = svc.audit_service.write_log.await_args.args[1]
        assert action == 'discord_role.mapping_added'

    async def test_add_mapping_rejects_duplicate(self):
        svc = make_service()
        svc.mapping_repository.get_match = AsyncMock(return_value=SimpleNamespace(id=1))

        with pytest.raises(ValueError):
            await svc.add_mapping(
                guild_id=42, discord_role_id=111, discord_role_name='Mods',
                app_role=Role.PROCTOR, actor=make_user(),
            )
        svc.mapping_repository.create.assert_not_awaited()

    async def test_remove_mapping_deletes_and_audits(self):
        svc = make_service()
        existing = SimpleNamespace(
            id=5, guild_id=42, discord_role_id=111,
            discord_role_name='Mods', app_role=Role.PROCTOR,
        )
        svc.mapping_repository.get_by_id = AsyncMock(return_value=existing)

        await svc.remove_mapping(5, actor=make_user())

        svc.mapping_repository.delete.assert_awaited_once_with(existing)
        action = svc.audit_service.write_log.await_args.args[1]
        assert action == 'discord_role.mapping_removed'

    async def test_remove_mapping_missing_raises(self):
        svc = make_service()
        svc.mapping_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError):
            await svc.remove_mapping(999, actor=make_user())
        svc.mapping_repository.delete.assert_not_awaited()

    async def test_non_staff_cannot_add_mapping(self, monkeypatch):
        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(drms.AuthService, 'can_grant_roles', deny)
        monkeypatch.setattr(drms.AuthService, 'ensure', real_ensure)

        svc = make_service()
        with pytest.raises(PermissionError):
            await svc.add_mapping(
                guild_id=42, discord_role_id=111, discord_role_name='Mods',
                app_role=Role.PROCTOR, actor=make_user(),
            )


# ---------------------------------------------------------------------------
# Integration: real ORM (in-memory SQLite) exercising the migration columns
# ---------------------------------------------------------------------------


class TestSyncIntegration:
    async def test_full_sync_against_real_db(self, db, monkeypatch):
        from application.repositories.discord_role_mapping_repository import (
            DiscordRoleMappingRepository,
        )
        from application.repositories.user_role_repository import UserRoleRepository
        from models import User, UserRole

        guild_id = 42
        user = await User.create(discord_id=555, username='bob')
        await DiscordRoleMappingRepository.create(guild_id, 111, 'Mods', Role.PROCTOR)
        # A manually-granted role that must survive the sync.
        await UserRoleRepository.add(user, Role.STAFF, source=RoleSource.MANUAL)

        monkeypatch.setattr(
            drms.SystemConfigService, 'get_discord_sync_guild_id',
            AsyncMock(return_value=guild_id),
        )
        member_roles = {111}
        fake = SimpleNamespace(
            get_member_role_ids=AsyncMock(side_effect=lambda g, u: (True, set(member_roles)))
        )
        monkeypatch.setattr(drms, 'DiscordService', lambda: fake)

        svc = DiscordRoleMappingService()

        # 1) Member holds the mapped Discord role -> PROCTOR granted as `discord`.
        summary = await svc.sync_user_roles(user)
        assert summary['granted'] == ['proctor']
        proctor = await UserRole.get(user=user, role=Role.PROCTOR)
        assert proctor.source == RoleSource.DISCORD

        # 2) Member loses the Discord role -> PROCTOR revoked, STAFF (manual) kept.
        member_roles.clear()
        summary = await svc.sync_user_roles(user)
        assert summary['revoked'] == ['proctor']
        assert not await UserRole.filter(user=user, role=Role.PROCTOR).exists()
        assert await UserRole.filter(user=user, role=Role.STAFF).exists()
