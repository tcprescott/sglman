"""
Volunteer shift reminder loop.

A lightweight background worker (modeled on ``discord_queue``) that periodically
finds upcoming volunteer assignments within the configured lead time, enqueues a
reminder DM with an acknowledge button, and stamps ``reminder_sent_at`` so each
assignment is only reminded once.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# How often the loop wakes up to look for due reminders.
TICK_SECONDS = 60

_task: Optional[asyncio.Task] = None


async def _tick() -> None:
    from application.repositories import VolunteerAssignmentRepository
    from application.services import discord_queue
    from application.services.discord_service import DiscordService
    from application.services.system_config_service import SystemConfigService
    from application.utils.discord_messages import volunteer_reminder_dm
    from application.utils.timezone import format_eastern_display

    now = datetime.now(timezone.utc)
    lead = await SystemConfigService.get_volunteer_reminder_lead_minutes()
    window_end = now + timedelta(minutes=lead)

    due = await VolunteerAssignmentRepository.due_for_reminder(now, window_end)
    if not due:
        return

    discord_service = DiscordService()
    for assignment in due:
        shift = assignment.shift
        user = assignment.user
        # Stamp first so a delivery failure (or a restart) doesn't re-fire.
        assignment.reminder_sent_at = now
        await assignment.save()

        discord_id = getattr(user, 'discord_id', None)
        if not discord_id or not getattr(user, 'dm_notifications', True):
            continue
        position_name = shift.position.name if shift.position else ''
        message = volunteer_reminder_dm(
            position_name=position_name,
            label=shift.label,
            starts_display=format_eastern_display(shift.starts_at),
            ends_display=format_eastern_display(shift.ends_at),
        )
        discord_queue.enqueue(
            discord_service.send_dm_with_volunteer_acknowledgment_button(
                int(discord_id), message, assignment.id,
            )
        )


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except Exception as e:  # never let the loop die
            logger.exception("volunteer reminder tick failed: %s", e)
        await asyncio.sleep(TICK_SECONDS)


def start() -> None:
    global _task
    if _task is None:
        _task = asyncio.get_event_loop().create_task(_loop())


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
