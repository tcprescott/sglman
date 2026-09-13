"""
Discord Service - Business Logic Layer

Handles Discord-related operations like sending DMs.
"""

import logging
from typing import Awaitable, Callable, Dict, Optional, Tuple

import discord
from discord.ext import commands

from application.events import dispatch_queue as event_dispatch_queue
from application.services.discord.discord_guild_ops import (
    GuildOpsMixin,
    MockGuildOpsMixin,
)
from application.services.discord.discord_member_events import (
    sync_member_avatar,
    sync_member_roles,
)
from application.services.discord.discord_scheduled_events import (
    MockScheduledEventsMixin,
    ScheduledEventsMixin,
)
from application.services.web_push_service import WebPushService
from application.utils.discord_messages import DMLink

logger = logging.getLogger(__name__)


def _mirror_dm_to_web_push(
    user_id: int, message: str, navigate: Optional[str] = None,
) -> None:
    """Fan every outgoing DM out to the recipient's web-push devices.

    send_dm is the chokepoint all notification paths flow through, so mirroring
    here gives device notifications the exact coverage DMs have. The mirror is
    enqueued fire-and-forget onto the event dispatch worker — the caller may be
    the serial discord_queue worker or a UI click handler awaiting send_dm
    inline, and neither may ever wait on push-service round-trips. No coroutine
    is created at all while VAPID is unconfigured.

    ``navigate`` is the DM's :class:`~application.utils.discord_messages.DMLink`
    target, so tapping the phone notification lands on the same control the
    Discord button does.
    """
    if not WebPushService.is_configured():
        return
    event_dispatch_queue.enqueue(
        WebPushService().mirror_dm(user_id, message, navigate=navigate)
    )


def _with_link_button(
    view: Optional[discord.ui.View], link: Optional[DMLink],
) -> Optional[discord.ui.View]:
    """Append ``link`` to ``view`` as a Discord link button, creating one if needed.

    A link button needs no interaction handler and no ``custom_id``, so it
    composes with the acknowledgment / crew / unwatch views rather than replacing
    them: a player gets **Acknowledge** and **View match** side by side. A blank
    URL yields no button — Discord rejects one — so a caller whose tenant could
    not be resolved degrades to the DM it would have sent anyway.
    """
    if link is None or not link.url:
        return view
    view = view if view is not None else discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label=link.label, style=discord.ButtonStyle.link, url=link.url,
    ))
    return view


# Shared bot instance (singleton pattern)
_bot_instance: Optional[commands.Bot] = None


# ---------------------------------------------------------------------------
# Interaction-handler and DM view-factory registries
#
# These invert what used to be a bidirectional import cycle between this module
# and the Discord bot package (previously held together by ~20 deferred,
# function-body imports). The bot package registers each interaction handler
# and view factory here at startup, so the dependency now runs one way (the bot
# package -> ``application.services``) and this module never imports it back.
# Mirrors ``application/events/match_live.py``.
# ---------------------------------------------------------------------------

# Stable view-factory kinds, shared with the bot package's registration so the
# DM senders below and the registering code agree on the lookup keys.
VIEW_CREW_SIGNUP = 'crew_signup'
VIEW_MATCH_ACK = 'match_ack'
VIEW_CREW_ACK = 'crew_ack'
VIEW_VOLUNTEER_ACK = 'volunteer_ack'
VIEW_UNWATCH = 'match_watch'
VIEW_RESCHEDULE_AGREE = 'reschedule_agree'
VIEW_HARD_PRESET = 'match_hard'

InteractionHandler = Callable[[discord.Interaction], Awaitable[None]]
ViewFactory = Callable[..., discord.ui.View]

_interaction_handlers: Dict[str, InteractionHandler] = {}
_view_factories: Dict[str, ViewFactory] = {}


def register_interaction_handler(prefix: str, handler: InteractionHandler) -> None:
    """Register a component-interaction handler keyed by its custom_id prefix.

    ``on_interaction`` dispatches an incoming component interaction to the
    handler whose ``prefix`` matches the text before the first ``:`` in the
    button's ``custom_id``.
    """
    _interaction_handlers[prefix] = handler


def register_view_factory(kind: str, factory: ViewFactory) -> None:
    """Register a Discord ``View`` factory keyed by ``kind`` (a ``VIEW_*`` const).

    The DM senders look the factory up by ``kind`` instead of importing it from
    the bot package directly.
    """
    _view_factories[kind] = factory


def get_discord_bot() -> commands.Bot:
    """
    Get or create the shared Discord bot instance.
    
    Returns:
        The Discord bot instance
    """
    global _bot_instance
    if _bot_instance is None:
        # Intents required for DM, guild/role visibility
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.dm_messages = True
        
        _bot_instance = commands.Bot(command_prefix='!', intents=intents)
        
        @_bot_instance.event
        async def on_ready() -> None:
            logger.info('Discord bot ready. Logged in as %s', _bot_instance.user)

        @_bot_instance.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            if interaction.type == discord.InteractionType.component:
                custom_id = (interaction.data or {}).get('custom_id', '')
                prefix = custom_id.split(':', 1)[0]
                handler = _interaction_handlers.get(prefix)
                if handler is not None:
                    await handler(interaction)

        @_bot_instance.event
        async def on_member_update(before: discord.Member, after: discord.Member) -> None:
            # The event fires for nick/avatar/timeout/role changes alike, so each
            # sync decides for itself whether anything it cares about moved.
            if before.avatar != after.avatar:
                await sync_member_avatar(after)
            if {r.id for r in before.roles} != {r.id for r in after.roles}:
                await sync_member_roles(after.guild.id, after.id)

        @_bot_instance.event
        async def on_member_remove(member: discord.Member) -> None:
            # Left/kicked/banned: re-sync strips their Discord-sourced roles.
            await sync_member_roles(member.guild.id, member.id)

    return _bot_instance


class DiscordService(GuildOpsMixin, ScheduledEventsMixin):
    """Service for Discord-related operations.

    This module owns the DM surface — the one path every notification flows
    through. Guild/role reads and writes and the Scheduled Events wrappers are
    mixed in from their own modules; ``MockDiscordService`` composes the mock
    twin of each, so the two surfaces cannot drift apart.
    """
    
    def __init__(self) -> None:
        self._bot = get_discord_bot()

    async def send_dm(
        self,
        user_id: int,
        message: str,
        view_factory: Optional[Callable[[], discord.ui.View]] = None,
        embed: Optional[discord.Embed] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user, optionally with attached buttons.

        Args:
            user_id: Discord user ID
            message: Plain-text message. Always mirrored to the recipient's
                web-push devices, and sent as the Discord content **unless** an
                ``embed`` is given (then the embed is the Discord representation
                and ``message`` serves only as the web-push/fallback text).
            view_factory: Optional zero-arg callable returning the
                ``discord.ui.View`` (buttons) to attach. Called just before the
                message is sent, so it only runs once the bot is ready and the
                user has been fetched.
            embed: Optional rich embed. When present it is sent instead of the
                plain content (Discord would otherwise show both).
            link: Optional :class:`DMLink` rendered as a link button beside any
                buttons ``view_factory`` supplied, and used as the web-push
                mirror's tap target. Every DM that asks for an action should
                carry one — a markdown link in ``message`` is **not** a
                substitute, because an embed suppresses the content entirely.

        Returns:
            Tuple of (success: bool, message: str)
            - If successful: (True, "Message sent successfully.")
            - If failed: (False, error_message)
        """
        # Mirror before the bot-readiness checks so device notifications still
        # go out when the bot is down or the user blocks Discord DMs. Corollary:
        # a (False, ...) return means the *Discord* send failed — subscribed
        # devices may already have been notified, so don't blindly re-send. The
        # mirror always uses the plain text, even when an embed carries the DM.
        _mirror_dm_to_web_push(user_id, message, navigate=link.url if link else None)
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            user = await self._bot.fetch_user(user_id)
            kwargs: dict = {}
            view = _with_link_button(
                view_factory() if view_factory is not None else None, link,
            )
            if view is not None:
                kwargs['view'] = view
            if embed is not None:
                # Embed is the Discord representation; content omitted to avoid
                # showing the plain text above the card.
                await user.send(embed=embed, **kwargs)
            else:
                await user.send(message, **kwargs)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {e!s}"
        except Exception as e:
            return False, f"Discord bot error: {e!s}"

    # The five view-bearing senders below are thin wrappers over send_dm: each
    # resolves its registered view factory by kind (populated by the bot package
    # at startup — see the registries above) and defers to send_dm.
    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int, embed: Optional[discord.Embed] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        """Send a DM with the commentator/tracker crew signup buttons for a match."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_CREW_SIGNUP](match_id), embed=embed, link=link)

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int, embed: Optional[discord.Embed] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        """Send a DM with a match Acknowledge button."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_MATCH_ACK](match_id), embed=embed, link=link)

    async def send_dm_with_reschedule_agree_button(
        self,
        user_id: int,
        message: str,
        request_id: int,
        embed: Optional[discord.Embed] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        """Send a DM with the opponent's Agree button for a reschedule request."""
        return await self.send_dm(
            user_id, message, lambda: _view_factories[VIEW_RESCHEDULE_AGREE](request_id),
            embed=embed, link=link,
        )

    async def send_dm_with_hard_preset_buttons(
        self,
        user_id: int,
        message: str,
        match_id: int,
        opted_in: bool,
        embed: Optional[discord.Embed] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        """Send a DM with the harder-settings opt-in (or back-out) button.

        ``opted_in`` picks which single button the DM carries, so the message
        never shows a state the reader is not already in.
        """
        return await self.send_dm(
            user_id, message,
            lambda: _view_factories[VIEW_HARD_PRESET](match_id, opted_in),
            embed=embed, link=link,
        )

    async def send_dm_with_crew_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        crew_type: str,
        crew_id: int,
        embed: Optional[discord.Embed] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        """Send a DM with a crew-assignment Acknowledge button.

        ``crew_type`` is 'commentator' or 'tracker'; ``crew_id`` is the crew row id.
        """
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_CREW_ACK](crew_type, crew_id), embed=embed, link=link)

    async def send_dm_with_volunteer_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        assignment_id: int,
        embed: Optional[discord.Embed] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        """Send a DM with a volunteer shift Acknowledge button."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_VOLUNTEER_ACK](assignment_id), embed=embed, link=link)

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int, embed: Optional[discord.Embed] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        """Send a DM with an Unwatch button for match watchers."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_UNWATCH](match_id), embed=embed, link=link)

    def get_bot(self) -> Optional[commands.Bot]:
        """Get the Discord bot instance."""
        return self._bot


class MockDiscordService(MockGuildOpsMixin, MockScheduledEventsMixin):
    """Stub Discord service for local development without a real bot.

    Mirrors the public surface of DiscordService. Methods log to stdout and
    return success tuples with shapes matching the real implementation, so
    notification code paths can be exercised end-to-end.
    """

    def __init__(self) -> None:
        self._bot = None

    async def send_dm(
        self,
        user_id: int,
        message: str,
        view_factory: Optional[Callable[[], "discord.ui.View"]] = None,
        embed: Optional["discord.Embed"] = None,
        link: Optional[DMLink] = None,
    ) -> Tuple[bool, str]:
        # Deliberately no web-push mirror: mock mode must have no external side
        # effects (a dev with a prod DB snapshot + prod VAPID keys would push
        # to real users' phones). Real delivery requires the real service.
        suffix = f" [embed: {embed.title}]" if embed is not None else ""
        # The link is printed because it is the half of the DM mock mode can
        # actually verify — button interactions need a live bot, but whether the
        # call to action points anywhere is checkable from stdout.
        if link is not None and link.url:
            suffix += f" [button: {link.label} -> {link.url}]"
        print(f"[MOCK Discord DM] -> {user_id}: {message}{suffix}")
        return True, "Message sent (mock)"

    # Thin wrappers matching DiscordService's public surface; all defer to the
    # single send_dm stub above (the buttons are irrelevant in mock mode).
    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_reschedule_agree_button(self, user_id: int, message: str, request_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_hard_preset_buttons(self, user_id: int, message: str, match_id: int, opted_in: bool, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_crew_acknowledgment_button(self, user_id: int, message: str, crew_type: str, crew_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_volunteer_acknowledgment_button(self, user_id: int, message: str, assignment_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int, embed: Optional["discord.Embed"] = None, link: Optional[DMLink] = None) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message, embed=embed, link=link)

    def get_bot(self) -> None:
        return None



from application.utils.mocks.mock_discord import is_mock_discord

# Stable handle to the real implementation; survives the mock swap below so tests
# can exercise the real error branches regardless of MOCK_DISCORD.
_RealDiscordService = DiscordService

if is_mock_discord():
    DiscordService = MockDiscordService  # type: ignore[misc,assignment]
