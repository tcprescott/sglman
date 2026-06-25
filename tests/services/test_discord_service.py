"""Tests for MockDiscordService and DiscordService error branches (unit)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# MockDiscordService — always available in test environments
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_svc():
    """Directly instantiate MockDiscordService (no Discord bot needed)."""
    from application.services.discord_service import MockDiscordService
    return MockDiscordService()


class TestMockDiscordService:
    async def test_send_dm_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm(12345, 'Hello')
        assert ok is True
        assert 'mock' in msg.lower() or 'sent' in msg.lower()

    async def test_send_dm_with_crew_buttons_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm_with_crew_buttons(1, 'msg', match_id=7)
        assert ok is True

    async def test_send_dm_with_acknowledgment_button_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm_with_acknowledgment_button(1, 'msg', match_id=3)
        assert ok is True

    async def test_send_dm_with_crew_acknowledgment_button_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm_with_crew_acknowledgment_button(
            1, 'msg', crew_type='commentator', crew_id=5,
        )
        assert ok is True

    async def test_send_dm_with_volunteer_acknowledgment_button_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm_with_volunteer_acknowledgment_button(
            1, 'msg', assignment_id=9,
        )
        assert ok is True

    async def test_send_dm_with_unwatch_button_returns_success(self, mock_svc):
        ok, msg = await mock_svc.send_dm_with_unwatch_button(1, 'msg', match_id=2)
        assert ok is True

    async def test_list_guilds_returns_list(self, mock_svc):
        ok, data = await mock_svc.list_guilds()
        assert ok is True
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_list_guild_roles_returns_list(self, mock_svc):
        ok, data = await mock_svc.list_guild_roles(guild_id=1)
        assert ok is True
        assert isinstance(data, list)

    async def test_add_role_to_user_returns_success(self, mock_svc):
        ok, msg = await mock_svc.add_role_to_user(
            guild_id=1, user_id=2, role_id=3,
        )
        assert ok is True

    async def test_remove_role_from_user_returns_success(self, mock_svc):
        ok, msg = await mock_svc.remove_role_from_user(
            guild_id=1, user_id=2, role_id=3,
        )
        assert ok is True

    async def test_get_member_role_ids_returns_empty_set(self, mock_svc):
        ok, data = await mock_svc.get_member_role_ids(guild_id=1, user_id=2)
        assert ok is True
        assert isinstance(data, set)

    def test_get_bot_returns_none(self, mock_svc):
        assert mock_svc.get_bot() is None


# ---------------------------------------------------------------------------
# DiscordService error branches via a stub bot
# ---------------------------------------------------------------------------


@pytest.fixture
def real_svc_not_ready(monkeypatch):
    """DiscordService backed by a stub bot that is never 'ready'."""
    from application.services.discord_service import DiscordService

    stub_bot = MagicMock()
    stub_bot.is_ready.return_value = False

    monkeypatch.setattr(
        'application.services.discord_service.get_discord_bot',
        lambda: stub_bot,
    )

    svc = object.__new__(DiscordService)
    svc._bot = stub_bot
    return svc


class TestDiscordServiceNotReady:
    """When the bot is not connected every method should return (False, <error>)."""

    async def test_send_dm_fails_gracefully(self, real_svc_not_ready):
        ok, msg = await real_svc_not_ready.send_dm(123, 'hi')
        assert ok is False
        assert msg  # non-empty error string

    async def test_list_guilds_fails_gracefully(self, real_svc_not_ready):
        ok, msg = await real_svc_not_ready.list_guilds()
        assert ok is False

    async def test_list_guild_roles_fails_gracefully(self, real_svc_not_ready):
        ok, msg = await real_svc_not_ready.list_guild_roles(guild_id=1)
        assert ok is False

    async def test_get_member_role_ids_fails_gracefully(self, real_svc_not_ready):
        ok, msg = await real_svc_not_ready.get_member_role_ids(guild_id=1, user_id=2)
        assert ok is False
