"""Unit tests for the live (gateway-event) role sync helper.

`_sync_member_roles` runs from the bot's `on_member_update` / `on_member_remove`
handlers. It re-syncs a member's app roles only when the event is for the
configured guild and a local User exists.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.services import discord_service as dsvc
from application.services import system_config_service as scs
from application.services import discord_role_mapping_service as drms
from models import User


@pytest.fixture
def sync_spy(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(drms.DiscordRoleMappingService, 'sync_user_roles', spy)
    return spy


def _set_guild(monkeypatch, guild_id):
    monkeypatch.setattr(
        scs.SystemConfigService, 'get_discord_sync_guild_id',
        AsyncMock(return_value=guild_id),
    )


async def test_skips_when_guild_not_configured(monkeypatch, sync_spy):
    _set_guild(monkeypatch, None)
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()


async def test_skips_when_guild_mismatch(monkeypatch, sync_spy):
    _set_guild(monkeypatch, 99)
    monkeypatch.setattr(User, 'get_or_none', AsyncMock(return_value=SimpleNamespace(id=1)))
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()


async def test_skips_when_user_unknown(monkeypatch, sync_spy):
    _set_guild(monkeypatch, 42)
    monkeypatch.setattr(User, 'get_or_none', AsyncMock(return_value=None))
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()


async def test_syncs_when_guild_matches_and_user_known(monkeypatch, sync_spy):
    _set_guild(monkeypatch, 42)
    user = SimpleNamespace(id=7, discord_id=5)
    monkeypatch.setattr(User, 'get_or_none', AsyncMock(return_value=user))
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_awaited_once_with(user)


async def test_never_raises_on_internal_error(monkeypatch, sync_spy):
    # A failure resolving the guild config must be swallowed (best-effort).
    monkeypatch.setattr(
        scs.SystemConfigService, 'get_discord_sync_guild_id',
        AsyncMock(side_effect=RuntimeError('db down')),
    )
    await dsvc._sync_member_roles(guild_id=42, discord_user_id=5)
    sync_spy.assert_not_awaited()
