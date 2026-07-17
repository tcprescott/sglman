"""
Shared helpers for the Discord DM interaction handlers.

``run_dm_interaction`` captures the defer/parse/resolve-tenant/lookup-user/
except ladder every DM button handler needs (acknowledgment, crew signup,
unwatch), so each handler only supplies its custom_id parsing, tenant
resolution, and the scoped body.
"""

import logging
from typing import Any, Awaitable, Callable, Optional

import discord

from application.utils.discord_messages import MSG_NO_ACCOUNT

logger = logging.getLogger(__name__)


SendFn = Callable[[str], Awaitable[None]]


class DMInteractionError(Exception):
    """Raised by a parse callback to short-circuit with an ephemeral message."""


def make_acknowledged_view(prefix: str) -> discord.ui.View:
    """Create a Discord View with a single disabled 'Acknowledged' button."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledged',
        style=discord.ButtonStyle.secondary,
        custom_id=f'{prefix}:acknowledged',
        disabled=True,
    ))
    return view


async def send_ephemeral(interaction: discord.Interaction, message: str, *, log_label: str) -> None:
    """Send an ephemeral reply via followup if defer succeeded, else fall back to response."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        logger.exception("Failed to send Discord %s response", log_label)


async def run_dm_interaction(
    interaction: discord.Interaction,
    *,
    log_label: str,
    parse: Callable[[str], Any],
    resolve_tenant: Callable[[Any], Awaitable[Optional[int]]],
    not_found_message: str,
    handle: Callable[[discord.Interaction, Any, Any, SendFn], Awaitable[None]],
    unexpected_error_message: str,
) -> None:
    """Run a DM button handler through the shared defer/lookup/error ladder.

    Steps, in order:
      1. Defer ephemerally to extend Discord's 3-second interaction deadline.
      2. ``parse`` the custom_id (raise :class:`DMInteractionError` to reply and stop).
      3. ``resolve_tenant`` the referenced entity (``None`` -> ``not_found_message``).
      4. Inside ``tenant_scope``, look up the account (missing -> ``MSG_NO_ACCOUNT``).
      5. Run ``handle`` with a ``send`` helper; ``ValueError`` replies with its text,
         any other exception is logged and replies with ``unexpected_error_message``.
    """
    from application.services import UserService
    from application.tenant_context import tenant_scope

    async def send(message: str) -> None:
        await send_ephemeral(interaction, message, log_label=log_label)

    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        logger.exception("Failed to defer Discord %s interaction", log_label)

    custom_id = (interaction.data or {}).get('custom_id', '')
    try:
        parsed = parse(custom_id)
    except DMInteractionError as e:
        await send(str(e))
        return

    try:
        # DM buttons carry no tenant; discover it from the referenced entity,
        # then scope all tenant-aware service work to it.
        tenant_id = await resolve_tenant(parsed)
        if tenant_id is None:
            await send(not_found_message)
            return

        with tenant_scope(tenant_id):
            user = await UserService().get_user_by_discord_id(str(interaction.user.id))
            if not user:
                await send(MSG_NO_ACCOUNT)
                return

            await handle(interaction, parsed, user, send)
    except ValueError as e:
        await send(str(e))
    except Exception:
        logger.exception("Discord %s handler failed", log_label)
        await send(unexpected_error_message)
