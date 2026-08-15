"""Creating, moving and cancelling a guild's Scheduled Events.

Split out of ``discord_service`` the way ``discord_member_events`` was, and
composed the way :class:`StationAssignmentMixin` is composed into
``MatchService``: :class:`ScheduledEventsMixin` reaches ``self._bot`` through the
class it is mixed into.

The Discord Events reconciler mirrors Wizzrobe's schedule into the tenant
guild's Scheduled Events. These are thin, fail-closed wrappers over the
discord.py scheduled-event API; the reconciler owns idempotency (it tracks which
events it created via ``DiscordScheduledEvent`` rows).

The mock twin lives here too rather than in ``discord_service``, for the reason
given in ``discord_guild_ops``: a mirror kept in another file drifts, and it
drifts in the one mode nobody runs the tests in.
"""

import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple, Union

import discord
from discord.ext import commands

from application.utils.mocks import mock_discord_data

logger = logging.getLogger(__name__)


def _description_or_missing(description: Optional[str]) -> str:
    """Truncate a scheduled-event description, or ``MISSING`` when it is empty.

    discord.py omits ``description`` from the payload only when the argument is
    ``MISSING``; passing ``None`` puts a literal JSON ``null`` on the wire, which
    *clears* an existing description instead of leaving it untouched.
    """
    return (description or '')[:1000] or discord.utils.MISSING



class ScheduledEventsMixin:
    """Scheduled-event operations against the live bot."""

    #: Set by the composed class's ``__init__``; declared so the mixin's own
    #: reads type-check without the composed class being visible from here.
    _bot: Optional[commands.Bot]

    async def _get_guild(self, guild_id: int) -> Optional["discord.Guild"]:
        if self._bot is None:
            return None
        guild = self._bot.get_guild(guild_id)
        if guild is None:
            try:
                guild = await self._bot.fetch_guild(guild_id)
            except (discord.NotFound, discord.Forbidden):
                return None
        return guild

    async def _scheduled_event_op(
        self,
        guild_id: int,
        op: Callable[["discord.Guild"], Awaitable[Tuple[bool, Union[int, str]]]],
        *,
        gerund: str,
        verb: str,
    ) -> Tuple[bool, Union[int, str]]:
        """Run a guild-scoped scheduled-event ``op`` with the shared guard + error tail.

        Applies the not-connected preamble, resolves the guild (via ``_get_guild``,
        returning "not in this server" when absent), then delegates to ``op(guild)``
        and maps the discord.py exception tail to a ``(False, message)`` tuple.
        ``gerund``/``verb`` name the action for the error text (e.g. 'creating'/'create').
        """
        try:
            if self._bot is None or not self._bot.is_ready():
                return False, "Discord bot is not connected."
            guild = await self._get_guild(guild_id)
            if guild is None:
                return False, "The bot is not in this server."
            return await op(guild)
        except discord.Forbidden:
            return False, "Bot lacks permission to manage events in this server."
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while {gerund} event: {e!s}"
        except Exception as e:
            return False, f"Failed to {verb} event: {e!s}"

    async def create_scheduled_event(
        self,
        guild_id: int,
        *,
        name: str,
        start_time: "datetime",
        end_time: "datetime",
        description: Optional[str] = None,
        location: str = 'Stream',
    ) -> Tuple[bool, Union[int, str]]:
        """Create an external Scheduled Event; return ``(True, event_id)`` or an error."""
        async def _op(guild: "discord.Guild") -> Tuple[bool, Union[int, str]]:
            event = await guild.create_scheduled_event(
                name=name[:100],
                start_time=start_time,
                end_time=end_time,
                description=_description_or_missing(description),
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location=location[:100],
            )
            return True, int(event.id)

        return await self._scheduled_event_op(guild_id, _op, gerund="creating", verb="create")

    async def edit_scheduled_event(
        self,
        guild_id: int,
        event_id: int,
        *,
        name: str,
        start_time: "datetime",
        end_time: "datetime",
        description: Optional[str] = None,
        location: str = 'Stream',
    ) -> Tuple[bool, str]:
        """Edit an existing Scheduled Event to match the current schedule."""
        async def _op(guild: "discord.Guild") -> Tuple[bool, Union[int, str]]:
            event = guild.get_scheduled_event(event_id)
            if event is None:
                try:
                    event = await guild.fetch_scheduled_event(event_id)
                except discord.NotFound:
                    return False, "Scheduled event not found."
            await event.edit(
                name=name[:100],
                start_time=start_time,
                end_time=end_time,
                description=_description_or_missing(description),
                entity_type=discord.EntityType.external,
                location=location[:100],
            )
            return True, "Event updated."

        return await self._scheduled_event_op(guild_id, _op, gerund="editing", verb="edit")

    async def delete_scheduled_event(self, guild_id: int, event_id: int) -> Tuple[bool, str]:
        """Cancel (delete) a Scheduled Event. Treats an already-gone event as success."""
        async def _op(guild: "discord.Guild") -> Tuple[bool, Union[int, str]]:
            event = guild.get_scheduled_event(event_id)
            if event is None:
                try:
                    event = await guild.fetch_scheduled_event(event_id)
                except discord.NotFound:
                    return True, "Event already removed."
            await event.delete()
            return True, "Event cancelled."

        return await self._scheduled_event_op(guild_id, _op, gerund="deleting", verb="delete")


class MockScheduledEventsMixin:
    """The same surface against ``mock_discord_data``'s in-memory event store."""

    async def create_scheduled_event(
        self, guild_id: int, *, name: str, start_time: "datetime", end_time: "datetime",
        description: Optional[str] = None, location: str = 'Stream',
    ) -> Tuple[bool, Union[int, str]]:
        event_id = mock_discord_data.create_scheduled_event(
            guild_id, name=name, start_time=start_time, end_time=end_time,
            description=description, location=location,
        )
        print(f"[MOCK Discord] create_scheduled_event guild={guild_id} name={name!r} -> {event_id}")
        return True, event_id

    async def edit_scheduled_event(
        self, guild_id: int, event_id: int, *, name: str, start_time: "datetime",
        end_time: "datetime", description: Optional[str] = None, location: str = 'Stream',
    ) -> Tuple[bool, str]:
        ok = mock_discord_data.edit_scheduled_event(
            event_id, guild_id=guild_id, name=name, start_time=start_time,
            end_time=end_time, description=description, location=location,
        )
        print(f"[MOCK Discord] edit_scheduled_event guild={guild_id} event={event_id} ok={ok}")
        return (True, "Event updated.") if ok else (False, "Scheduled event not found.")

    async def delete_scheduled_event(self, guild_id: int, event_id: int) -> Tuple[bool, str]:
        mock_discord_data.delete_scheduled_event(event_id)
        print(f"[MOCK Discord] delete_scheduled_event guild={guild_id} event={event_id}")
        return True, "Event cancelled."
