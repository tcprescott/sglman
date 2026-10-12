"""The bot's login surface: ``/login``, ``/wizzrobe login-panel`` and the panel button.

Driven with fake interactions (Discord can't be reached from tests). Checks what
the person sees: a private reply, one link button per community, deleted when
the link expires, and the staff gate on posting a panel.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from application.services import tenant_service
from application.services.audit_service import AuditActions
from application.services.discord import discord_login_service as dls
from discordbot import login as bot_login
from models import AuditLog, Role, Tenant, UserRole
from tests.factories import make_user

GUILD = 4242


@pytest.fixture(autouse=True)
def _secret_and_reset(monkeypatch):
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    monkeypatch.setenv('BASE_URL', 'https://wizzrobe.test')
    dls.reset()
    yield
    dls.reset()


@pytest.fixture
async def tenant(db):
    t = await Tenant.get(id=1)
    t.discord_guild_id = GUILD
    await t.save()
    tenant_service._clear_cache()
    return t


def _interaction(*, guild_id=GUILD, user_id=777, custom_id=None, channel=None):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.channel_id = 31337
    interaction.channel = channel
    interaction.data = {'custom_id': custom_id} if custom_id else {}
    interaction.user.id = user_id
    interaction.user.name = 'pressy'
    interaction.user.avatar = None
    interaction.user.display_avatar.url = 'https://cdn.test/a.png'
    interaction.response.send_message = AsyncMock()
    return interaction


def _reply(interaction):
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.call_args
    return args[0], kwargs


def _link_urls(kwargs):
    return [item.url for item in kwargs['view'].children]


async def test_login_replies_privately_with_a_self_deleting_link(tenant):
    interaction = _interaction()
    await bot_login.login_command.callback(interaction)
    text, kwargs = _reply(interaction)
    assert kwargs['ephemeral'] is True
    assert kwargs['delete_after'] == dls.LINK_TTL_SECONDS
    assert 'works once' in text
    [url] = _link_urls(kwargs)
    assert url.startswith('https://wizzrobe.test/t/default/login/discord?token=')


async def test_login_offers_one_link_per_linked_community(tenant):
    await Tenant.create(name='Second', slug='second', discord_guild_id=GUILD)
    tenant_service._clear_cache()
    interaction = _interaction()
    await bot_login.login_command.callback(interaction)
    _text, kwargs = _reply(interaction)
    labels = [item.label for item in kwargs['view'].children]
    assert labels == ['Log in to Default', 'Log in to Second']


async def test_login_in_an_unlinked_server(tenant):
    interaction = _interaction(guild_id=1)
    await bot_login.login_command.callback(interaction)
    text, kwargs = _reply(interaction)
    assert text == bot_login.MSG_NOT_LINKED
    assert kwargs['ephemeral'] is True


async def test_inactive_account_is_told_why(tenant):
    await make_user(discord_id=777, is_active=False)
    interaction = _interaction()
    await bot_login.login_command.callback(interaction)
    text, kwargs = _reply(interaction)
    assert 'inactive' in text
    assert 'view' not in kwargs


async def test_panel_press_mints_a_link(tenant):
    interaction = _interaction(custom_id=f'wiz_login:{tenant.id}')
    await bot_login.handle_login_panel_interaction(interaction)
    _text, kwargs = _reply(interaction)
    assert len(_link_urls(kwargs)) == 1


async def test_stale_panel_says_so(tenant):
    interaction = _interaction(guild_id=GUILD + 1, custom_id=f'wiz_login:{tenant.id}')
    await bot_login.handle_login_panel_interaction(interaction)
    text, _kwargs = _reply(interaction)
    assert 'no longer linked' in text


async def test_malformed_panel_button(tenant):
    interaction = _interaction(custom_id='wiz_login:nope')
    await bot_login.handle_login_panel_interaction(interaction)
    text, _kwargs = _reply(interaction)
    assert text == bot_login.MSG_NOT_LINKED


def _channel():
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    return channel


async def test_non_staff_cannot_post_the_panel(tenant):
    await make_user(discord_id=777)
    channel = _channel()
    interaction = _interaction(channel=channel)
    await bot_login.login_panel_command.callback(interaction)
    text, _kwargs = _reply(interaction)
    assert 'staff' in text
    channel.send.assert_not_awaited()


async def test_staff_posts_the_panel_and_it_is_audited(tenant):
    staff = await make_user(discord_id=777)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)
    channel = _channel()
    interaction = _interaction(channel=channel)
    await bot_login.login_panel_command.callback(interaction)

    channel.send.assert_awaited_once()
    view = channel.send.call_args.kwargs['view']
    [button] = view.children
    assert button.custom_id == f'wiz_login:{tenant.id}'
    text, kwargs = _reply(interaction)
    assert kwargs['ephemeral'] is True
    assert text == 'Posted the Default login panel.'
    row = await AuditLog.get(action=AuditActions.DISCORD_LOGIN_PANEL_POSTED)
    assert json.loads(row.details)['channel_id'] == 31337


async def test_panel_needs_a_community_choice_when_the_server_has_several(tenant):
    await Tenant.create(name='Second', slug='second', discord_guild_id=GUILD)
    tenant_service._clear_cache()
    staff = await make_user(discord_id=777)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)
    channel = _channel()

    interaction = _interaction(channel=channel)
    await bot_login.login_panel_command.callback(interaction)
    text, _kwargs = _reply(interaction)
    assert 'more than one community' in text
    channel.send.assert_not_awaited()

    interaction = _interaction(channel=channel)
    await bot_login.login_panel_command.callback(interaction, community='default')
    channel.send.assert_awaited_once()


async def test_panel_without_send_permission(tenant):
    staff = await make_user(discord_id=777)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)
    channel = _channel()
    channel.send.side_effect = discord.Forbidden(MagicMock(status=403), 'nope')
    interaction = _interaction(channel=channel)
    await bot_login.login_panel_command.callback(interaction)
    text, _kwargs = _reply(interaction)
    assert 'Send Messages' in text
    assert not await AuditLog.filter(action=AuditActions.DISCORD_LOGIN_PANEL_POSTED).exists()


def test_commands_are_server_only_and_the_panel_needs_manage_server():
    assert bot_login.login_command.guild_only is True
    assert bot_login.wizzrobe_group.guild_only is True
    assert bot_login.wizzrobe_group.default_permissions == discord.Permissions(manage_guild=True)
