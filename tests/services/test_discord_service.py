"""Tests for MockDiscordService and DiscordService error branches (unit)."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

# Scheduled events must carry aware datetimes — discord.py raises ValueError on
# naive ones. Tortoise hands back aware UTC, so this matches production.
START = datetime(2026, 7, 28, 18, 30, tzinfo=timezone.utc)
END = START + timedelta(hours=1)


# ---------------------------------------------------------------------------
# MockDiscordService — always available in test environments
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_svc():
    """Directly instantiate MockDiscordService (no Discord bot needed)."""
    from application.services.discord.discord_service import MockDiscordService
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
        from application.utils.mocks import mock_discord_data as mdd

        ok, data = await mock_svc.get_member_role_ids(guild_id=mdd.GUILD_WIZ_DEFAULT, user_id=2)
        assert ok is True
        assert isinstance(data, set)
        assert data <= {r['id'] for r in mdd.roles_for(mdd.GUILD_WIZ_DEFAULT)}
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
    from application.services.discord.discord_service import _RealDiscordService

    stub_bot = MagicMock()
    stub_bot.is_ready.return_value = False

    monkeypatch.setattr(
        'application.services.discord.discord_service.get_discord_bot',
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
        from application.services.discord.discord_service import _RealDiscordService

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


# ---------------------------------------------------------------------------
# The Discord library itself
#
# py-cord and discord.py are hard forks that both install into the same
# top-level ``discord/`` package, so installing both leaves whichever unpacked
# last owning the shared modules. That happened here: py-cord shadowed
# discord.py, ``discord.EntityType`` / ``discord.PrivacyLevel`` silently stopped
# existing, and the scheduled-event calls below failed for every real guild
# while the suite stayed green (they are only ever reached through
# MockDiscordService). These tests pin the library identity and the exact
# signatures the service depends on.
# ---------------------------------------------------------------------------


class TestDiscordLibraryIdentity:
    def test_only_discord_py_provides_the_discord_package(self):
        from importlib.metadata import packages_distributions

        providers = packages_distributions().get('discord', [])
        assert providers == ['discord.py'], (
            f'the `discord` package is provided by {providers}; it must come from '
            'discord.py alone. py-cord and discord.py are forks that install into '
            'the same directory and silently overwrite each other.'
        )

    def test_library_is_discord_py_not_pycord(self):
        import discord

        # py-cord sets __title__ = 'pycord' and __author__ = 'Pycord Development'.
        assert (discord.__title__, discord.__author__) == ('discord', 'Rapptz')

    def test_scheduled_event_enums_exist(self):
        import discord

        # The two names discord_service dereferences; both absent under py-cord.
        assert discord.EntityType.external is not None
        assert discord.PrivacyLevel.guild_only is not None

    def test_scheduled_event_signatures_accept_the_kwargs_we_pass(self):
        import inspect

        import discord

        create = inspect.signature(discord.Guild.create_scheduled_event).parameters
        assert {'entity_type', 'privacy_level', 'location', 'end_time'} <= set(create)
        assert {'entity_type', 'location'} <= set(inspect.signature(discord.ScheduledEvent.edit).parameters)


class TestScheduledEventKwargs:
    """Drive the real service's scheduled-event ops against a stub guild.

    Every other scheduled-event test goes through MockDiscordService, so these
    are the only tests that reach the discord library at all.
    """

    def _svc(self, monkeypatch, guild):
        from application.services.discord.discord_service import _RealDiscordService

        stub_bot = MagicMock()
        stub_bot.is_ready.return_value = True
        stub_bot.get_guild.return_value = guild
        monkeypatch.setattr(
            'application.services.discord.discord_service.get_discord_bot',
            lambda: stub_bot,
        )
        svc = object.__new__(_RealDiscordService)
        svc._bot = stub_bot
        return svc

    async def test_create_passes_external_entity_type_and_truncates(self, monkeypatch):
        import discord

        guild = MagicMock()
        guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=999))
        svc = self._svc(monkeypatch, guild)

        ok, event_id = await svc.create_scheduled_event(
            1, name='N' * 150, start_time=START, end_time=END,
            description='D' * 1500, location='L' * 150,
        )

        # Assert success first: _scheduled_event_op turns any exception into
        # (False, msg), so a bare kwargs assertion would fail on call_args=None
        # and hide the real cause.
        assert (ok, event_id) == (True, 999)
        kwargs = guild.create_scheduled_event.await_args.kwargs
        assert kwargs['entity_type'] is discord.EntityType.external
        assert kwargs['privacy_level'] is discord.PrivacyLevel.guild_only
        assert (kwargs['start_time'], kwargs['end_time']) == (START, END)
        assert len(kwargs['name']) == 100
        assert len(kwargs['description']) == 1000
        assert len(kwargs['location']) == 100

    async def test_create_omits_empty_description(self, monkeypatch):
        import discord

        guild = MagicMock()
        guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=1))
        svc = self._svc(monkeypatch, guild)

        ok, _ = await svc.create_scheduled_event(
            1, name='n', start_time=START, end_time=END, description=None,
        )

        assert ok is True
        # MISSING (not None) — discord.py only omits the field for MISSING, and
        # a literal null clears the description rather than leaving it unset.
        assert guild.create_scheduled_event.await_args.kwargs['description'] is discord.utils.MISSING

    async def test_edit_passes_external_entity_type_and_omits_empty_description(self, monkeypatch):
        import discord

        event = MagicMock()
        event.edit = AsyncMock()
        guild = MagicMock()
        guild.get_scheduled_event.return_value = event
        svc = self._svc(monkeypatch, guild)

        ok, msg = await svc.edit_scheduled_event(
            1, 55, name='n', start_time=START, end_time=END, description='',
        )

        assert (ok, msg) == (True, 'Event updated.')
        kwargs = event.edit.await_args.kwargs
        assert kwargs['entity_type'] is discord.EntityType.external
        assert kwargs['description'] is discord.utils.MISSING
        # create sends privacy_level; edit deliberately leaves it untouched.
        assert 'privacy_level' not in kwargs

    async def test_edit_reports_not_found_so_the_reconciler_can_self_heal(self, monkeypatch):
        import discord

        guild = MagicMock()
        guild.get_scheduled_event.return_value = None
        guild.fetch_scheduled_event = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), 'nope')
        )
        svc = self._svc(monkeypatch, guild)

        ok, msg = await svc.edit_scheduled_event(
            1, 55, name='n', start_time=START, end_time=END,
        )

        assert ok is False
        # DiscordEventReconcilerService keys its re-create branch off this text.
        assert 'not found' in msg.lower()
