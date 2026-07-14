"""Tests for RaceRoomProfileService — SYNC_ADMIN-gated CRUD.

Covers the authorization gate, the per-tenant name uniqueness, and that the
boolean/integer room settings round-trip through create/update.
"""

import pytest

from application.services import RaceRoomProfileService
from application.services.audit_service import AuditActions
from application.tenant_context import tenant_scope
from models import AuditLog, Role, Tenant, User, UserRole


@pytest.fixture
async def sync_admin(db):
    u = await User.create(discord_id=3000, username='sync')
    await UserRole.create(user=u, role=Role.SYNC_ADMIN, tenant=await Tenant.get(id=1))
    return u


@pytest.fixture
async def plain_user(db):
    return await User.create(discord_id=3001, username='nobody')


class TestProfileCrud:
    async def test_requires_sync_permission(self, plain_user, db):
        with tenant_scope(1):
            with pytest.raises(PermissionError):
                await RaceRoomProfileService().create_profile(plain_user, name='House')

    async def test_create_update_delete_roundtrip(self, sync_admin, db):
        service = RaceRoomProfileService()
        with tenant_scope(1):
            profile = await service.create_profile(
                sync_admin, name='House', goal='beat the game',
                auto_start=False, start_delay=30, streaming_required=True,
            )
            assert profile.goal == 'beat the game'
            assert profile.auto_start is False
            assert profile.start_delay == 30
            assert profile.streaming_required is True
            assert await AuditLog.filter(action=AuditActions.RACE_ROOM_PROFILE_CREATED).count() == 1

            updated = await service.update_profile(
                sync_admin, profile.id, name='House Rules', time_limit=12,
            )
            assert updated.name == 'House Rules'
            assert updated.time_limit == 12

            await service.delete_profile(sync_admin, profile.id)
            assert await service.list_profiles(sync_admin) == []

    async def test_duplicate_name_rejected(self, sync_admin, db):
        service = RaceRoomProfileService()
        with tenant_scope(1):
            await service.create_profile(sync_admin, name='House')
            with pytest.raises(ValueError):
                await service.create_profile(sync_admin, name='House')

    async def test_negative_timer_rejected(self, sync_admin, db):
        service = RaceRoomProfileService()
        with tenant_scope(1):
            with pytest.raises(ValueError):
                await service.create_profile(sync_admin, name='House', start_delay=-5)
