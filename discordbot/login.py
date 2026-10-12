"""Log in from Discord: ``/login``, ``/wizzrobe login-panel`` and the panel button.

``/login`` and a press on the panel button both answer with an ephemeral reply
holding a one-time sign-in link (see ``DiscordLoginService``). The reply deletes
itself when the link expires. ``/wizzrobe login-panel`` posts the permanent
panel; Discord shows it only to members with Manage Server, and the service adds
the community's STAFF gate.

The panel button's custom_id carries the community id (``wiz_login:<tenant_id>``)
because one server can back several communities, and so a panel keeps working
across bot restarts with nothing stored.
"""

import logging
import time
from typing import Optional

import discord
from discord import app_commands

from application.services import DiscordLoginService
from application.services.discord.discord_login_service import LINK_TTL_SECONDS
from application.utils.discord_embeds import COLOR_SCHEDULED, notification_embed
from application.utils.discord_messages import msg_unexpected_error
from models import Tenant

logger = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = 'wiz_login'

MSG_NOT_LINKED = "This server isn't linked to a Wizzrobe community."
MSG_LOGIN_FAILED = msg_unexpected_error('log in')
_BUTTON_LABEL_MAX = 80


def _login_label(tenant: Tenant) -> str:
    return f'Log in to {tenant.name}'[:_BUTTON_LABEL_MAX]


def make_login_panel_view(tenant_id: int) -> discord.ui.View:
    """The panel's persistent button; presses route to :func:`handle_login_panel_interaction`."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Log in',
        style=discord.ButtonStyle.primary,
        custom_id=f'{CUSTOM_ID_PREFIX}:{tenant_id}',
    ))
    return view


def login_panel_embed(tenant: Tenant) -> discord.Embed:
    return notification_embed(
        title=f'Log in to {tenant.name}',
        color=COLOR_SCHEDULED,
        description=(
            "Press **Log in** for a private link that signs you in on the web. "
            "Only you can see it, it works once, and it expires after two minutes."
        ),
        community_name=tenant.name,
    )


async def _defer(interaction: discord.Interaction) -> None:
    """Acknowledge within Discord's 3-second window; the answer follows up.

    Minting provisions an account and the panel posts to the channel first, so
    an immediate reply can miss the deadline ("Unknown interaction").
    """
    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
    except Exception:
        logger.exception('Failed to defer Discord login interaction')


async def _reply(
    interaction: discord.Interaction,
    message: str,
    *,
    delete_after: Optional[float] = None,
    **kwargs,
) -> None:
    try:
        if interaction.response.is_done():
            sent = await interaction.followup.send(message, ephemeral=True, wait=True, **kwargs)
            if delete_after is not None:
                await sent.delete(delay=delete_after)
        else:
            await interaction.response.send_message(
                message, ephemeral=True, delete_after=delete_after, **kwargs,
            )
    except Exception:
        logger.exception('Failed to send Discord login reply')


async def send_login_links(interaction: discord.Interaction, tenants: list[Tenant]) -> None:
    """Reply privately with one sign-in link per community, deleted at expiry."""
    if not tenants:
        await _reply(interaction, MSG_NOT_LINKED)
        return
    member = interaction.user
    view = discord.ui.View(timeout=None)
    try:
        for tenant in tenants:
            url = await DiscordLoginService.mint_link(
                tenant,
                discord_id=member.id,
                username=member.name,
                avatar_hash=member.avatar.key if member.avatar else '',
                avatar_url=str(member.display_avatar.url),
            )
            view.add_item(discord.ui.Button(label=_login_label(tenant), url=url))
    except ValueError as e:
        await _reply(interaction, str(e))
        return
    except Exception:
        logger.exception('Minting a Discord login link failed (discord user %s)', member.id)
        await _reply(interaction, MSG_LOGIN_FAILED)
        return
    expires = int(time.time()) + LINK_TTL_SECONDS
    await _reply(
        interaction,
        f"Here's your login link. It works once and expires <t:{expires}:R>. Don't share it.",
        view=view,
        delete_after=LINK_TTL_SECONDS,
    )


async def handle_login_panel_interaction(interaction: discord.Interaction) -> None:
    """A press on a login panel: custom_id ``wiz_login:<tenant_id>``."""
    await _defer(interaction)
    custom_id = str((interaction.data or {}).get('custom_id', ''))  # type: ignore[call-overload]
    try:
        tenant_id = int(custom_id.split(':', 1)[1])
    except (IndexError, ValueError):
        await _reply(interaction, MSG_NOT_LINKED)
        return
    try:
        tenant = await DiscordLoginService.community_for_panel(interaction.guild_id, tenant_id)
    except ValueError as e:
        await _reply(interaction, str(e))
        return
    await send_login_links(interaction, [tenant])


@app_commands.command(name='login', description='Get a private one-time link that signs you in to Wizzrobe')
@app_commands.guild_only()
async def login_command(interaction: discord.Interaction) -> None:
    await _defer(interaction)
    await send_login_links(
        interaction, await DiscordLoginService.communities_for_guild(interaction.guild_id),
    )


wizzrobe_group = app_commands.Group(
    name='wizzrobe',
    description='Wizzrobe server tools',
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


async def _pick_community(interaction: discord.Interaction, community: Optional[str]) -> Optional[Tenant]:
    tenants = await DiscordLoginService.communities_for_guild(interaction.guild_id)
    if community:
        return next((t for t in tenants if t.slug == community), None)
    return tenants[0] if len(tenants) == 1 else None


async def _community_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    tenants = await DiscordLoginService.communities_for_guild(interaction.guild_id)
    needle = current.lower()
    return [
        app_commands.Choice(name=t.name[:100], value=t.slug)
        for t in tenants
        if needle in t.name.lower() or needle in t.slug.lower()
    ][:25]


@wizzrobe_group.command(name='login-panel', description='Post a Log in button in this channel')
@app_commands.describe(community='Which community the button signs people in to (needed when this server has several)')
@app_commands.autocomplete(community=_community_autocomplete)
async def login_panel_command(interaction: discord.Interaction, community: Optional[str] = None) -> None:
    await _defer(interaction)
    tenants = await DiscordLoginService.communities_for_guild(interaction.guild_id)
    if not tenants:
        await _reply(interaction, MSG_NOT_LINKED)
        return
    tenant = await _pick_community(interaction, community)
    if tenant is None:
        await _reply(interaction, 'This server is linked to more than one community. Pick one with the `community` option.')
        return
    try:
        actor = await DiscordLoginService.authorize_panel(interaction.user.id, tenant)
    except PermissionError as e:
        await _reply(interaction, str(e))
        return
    channel = interaction.channel
    if not isinstance(channel, discord.abc.Messageable):
        await _reply(interaction, "I can't post in this kind of channel.")
        return
    try:
        await channel.send(embed=login_panel_embed(tenant), view=make_login_panel_view(tenant.id))
    except discord.Forbidden:
        await _reply(interaction, "I don't have permission to send messages here. Give the bot **Send Messages** and **Embed Links** in this channel, then try again.")
        return
    except Exception:
        logger.exception('Posting the Discord login panel failed (channel %s)', getattr(channel, 'id', None))
        await _reply(interaction, msg_unexpected_error('post the panel'))
        return
    await DiscordLoginService.record_panel_posted(actor, tenant, interaction.channel_id or 0)
    await _reply(interaction, f'Posted the {tenant.name} login panel.')
