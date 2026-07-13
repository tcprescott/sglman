"""Tests for MockDiscordService and DiscordService error branches (unit)."""

import pytest
from unittest.mock import MagicMock


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

    async def test_get_member_role_ids_returns_coherent_roles(self, mock_svc):
        # Mock members carry roles drawn from the guild's role set, so mock login
        # role sync actually grants/revokes. Everyone is at least a Volunteer.
        from application.utils import mock_discord_data as mdd

        ok, data = await mock_svc.get_member_role_ids(guild_id=mdd.GUILD_SGL_DEFAULT, user_id=2)
        assert ok is True
        assert isinstance(data, set)
        assert data <= {r['id'] for r in mdd.roles_for(mdd.GUILD_SGL_DEFAULT)}
        assert mdd.ROLE_VOLUNTEER in data

    def test_get_bot_returns_none(self, mock_svc):
        assert mock_svc.get_bot() is None


# ---------------------------------------------------------------------------
# DiscordService error branches via a stub bot
# ---------------------------------------------------------------------------


@pytest.fixture
def real_svc_not_ready(monkeypatch):
    """DiscordService backed by a stub bot that is never 'ready'.

    Uses the real implementation explicitly (`_RealDiscordService`), which survives
    the MOCK_DISCORD swap, so these error branches are exercised in both run modes.
    """
    from application.services.discord_service import _RealDiscordService

    stub_bot = MagicMock()
    stub_bot.is_ready.return_value = False

    monkeypatch.setattr(
        'application.services.discord_service.get_discord_bot',
        lambda: stub_bot,
    )

    svc = object.__new__(_RealDiscordService)
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

    async def test_member_can_manage_guild_fails_closed_when_not_ready(self, real_svc_not_ready):
        # Must fail closed (ok=False) so callers never treat an error as authorized.
        ok, result = await real_svc_not_ready.member_can_manage_guild(guild_id=1, user_id=2)
        assert ok is False

    async def test_get_guild_summary_fails_gracefully(self, real_svc_not_ready):
        ok, result = await real_svc_not_ready.get_guild_summary(guild_id=1)
        assert ok is False


class TestMemberCanManageGuild:
    """Authority check on a ready bot (owner / Administrator / Manage Server)."""

    def _svc_with_guild(self, monkeypatch, guild):
        from application.services.discord_service import _RealDiscordService

        stub_bot = MagicMock()
        stub_bot.is_ready.return_value = True
        stub_bot.get_guild.return_value = guild
        svc = object.__new__(_RealDiscordService)
        svc._bot = stub_bot
        return svc

    async def test_owner_can_manage(self, monkeypatch):
        guild = MagicMock()
        guild.owner_id = 42
        svc = self._svc_with_guild(monkeypatch, guild)
        ok, can = await svc.member_can_manage_guild(guild_id=1, user_id=42)
        assert (ok, can) == (True, True)

    async def test_manage_guild_permission_grants(self, monkeypatch):
        guild = MagicMock()
        guild.owner_id = 999
        member = MagicMock()
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = True
        guild.get_member.return_value = member
        svc = self._svc_with_guild(monkeypatch, guild)
        ok, can = await svc.member_can_manage_guild(guild_id=1, user_id=42)
        assert (ok, can) == (True, True)

    async def test_plain_member_cannot_manage(self, monkeypatch):
        guild = MagicMock()
        guild.owner_id = 999
        member = MagicMock()
        member.guild_permissions.administrator = False
        member.guild_permissions.manage_guild = False
        guild.get_member.return_value = member
        svc = self._svc_with_guild(monkeypatch, guild)
        ok, can = await svc.member_can_manage_guild(guild_id=1, user_id=42)
        assert (ok, can) == (True, False)


class TestMockAuthorityHelpers:
    async def test_member_can_manage_guild_true(self, mock_svc):
        ok, can = await mock_svc.member_can_manage_guild(guild_id=1, user_id=2)
        assert (ok, can) == (True, True)

    async def test_get_guild_summary_returns_dict(self, mock_svc):
        ok, data = await mock_svc.get_guild_summary(guild_id=7)
        assert ok is True
        assert data['id'] == 7
