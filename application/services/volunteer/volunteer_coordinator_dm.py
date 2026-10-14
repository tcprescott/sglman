"""DMs to the people who staff the volunteer schedule.

A volunteer giving a shift back and a volunteer running late both have to reach
whoever is covering the roster: every ``VOLUNTEER_COORDINATOR`` and ``STAFF``
holder in the community. Both land on the schedule on the day of the shift.
"""

from typing import Dict

import discord

from application.repositories import UserRoleRepository
from application.services.discord import discord_queue
from application.services.discord.discord_service import DiscordService
from application.services.timezone_service import TimezoneService
from application.utils.timezone import to_local
from models import Role, User, VolunteerShift


async def notify_coordinators(
    shift: VolunteerShift, message: str, embed: discord.Embed, *, link_label: str,
) -> None:
    """Queue the DM to every coordinator and staff member. Never raises on delivery."""
    from application.services import notification_links

    recipients: Dict[int, User] = {}
    for role in (Role.VOLUNTEER_COORDINATOR, Role.STAFF):
        for candidate in await UserRoleRepository.list_users_with_role(role):
            recipients[candidate.id] = candidate
    if not recipients:
        return

    # The community's own clock, not any reader's: the roster day is a property
    # of the schedule, and a coordinator abroad must not be sent to yesterday's
    # board.
    day = None
    if shift.starts_at:
        local = to_local(shift.starts_at, await TimezoneService.tenant_timezone_name())
        day = local.date() if local else None
    link = await notification_links.admin_volunteer_schedule(day, label=link_label)
    discord_service = DiscordService()
    for coordinator in recipients.values():
        discord_id = getattr(coordinator, 'discord_id', None)
        if not discord_id:
            continue
        discord_queue.enqueue(
            discord_service.send_dm(int(discord_id), message, embed=embed, link=link)
        )
