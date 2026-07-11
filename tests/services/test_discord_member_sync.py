"""Unit tests for the live (gateway-event) role sync helper.

`_sync_member_roles` runs from the bot's `on_member_update` / `on_member_remove`
handlers. It routes the Discord guild to its tenant, and (when a local User
exists) re-syncs that user's app roles for that tenant only.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.services import discord_service as dsvc
from application.services import tenant_service as tsvc
from application.services import discord_role_mapping_service as drms
from models import User


@pytest.fixture
def sync_spy(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(drms.DiscordRoleMappingService, 'sync_user_roles_for_tenant', spy)
    return spy


def _route_guild_to(monkeypatch, tenant):
    monkeypatch.setattr(
        tsvc.TenantService, 'get_by_guild_id', AsyncMock(return_value=tenant),
    )


async def test_skips_when_guild_not_linked_to_a_tenant(monkeypatch, sync_spy):
    _route_guild_to(monkeypatch, None)
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()


async def test_skips_when_user_unknown(monkeypatch, sync_spy):
    _route_guild_to(monkeypatch, SimpleNamespace(id=1, discord_guild_id=42))
    monkeypatch.setattr(User, 'get_or_none', AsyncMock(return_value=None))
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()


async def test_syncs_for_the_routed_tenant_when_user_known(monkeypatch, sync_spy):
    tenant = SimpleNamespace(id=1, discord_guild_id=42)
    _route_guild_to(monkeypatch, tenant)
    user = SimpleNamespace(id=7, discord_id=5)
    monkeypatch.setattr(User, 'get_or_none', AsyncMock(return_value=user))
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_awaited_once_with(user, tenant)


async def test_never_raises_on_internal_error(monkeypatch, sync_spy):
    # A failure resolving the guild's tenant must be swallowed (best-effort).
    monkeypatch.setattr(
        tsvc.TenantService, 'get_by_guild_id',
        AsyncMock(side_effect=RuntimeError('db down')),
    )
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()
