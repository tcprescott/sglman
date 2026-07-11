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

from application.tenant_context import tenant_scope

logger = logging.getLogger(__name__)

# How often the loop wakes up to look for due reminders.
TICK_SECONDS = 60

# The reminder lead time is now a per-tenant SystemConfiguration, but the loop
# iterates assignments across all tenants in one cross-tenant scan. So it scans a
# generous fixed window up front, then re-checks each assignment against ITS
# tenant's configured lead. Any tenant lead beyond this bound would be missed, so
# keep it comfortably above any realistic lead.
MAX_LEAD_MINUTES = 24 * 60

_task: Optional[asyncio.Task] = None


async def _scoped_dm(tenant_id: int, coro) -> None:
    """Await a DM-send coroutine with its tenant bound so deep links resolve."""
    with tenant_scope(tenant_id):
        await coro


async def _tick() -> None:
    from application.repositories import VolunteerAssignmentRepository
    from application.services import discord_queue
    from application.services.discord_service import DiscordService
    from application.services.system_config_service import SystemConfigService
    from application.utils.discord_messages import volunteer_reminder_dm
    from application.utils.timezone import format_eastern_display

    now = datetime.now(timezone.utc)
    # Cross-tenant scan over a wide window (due_for_reminder is intentionally
    # unscoped); each assignment is re-checked against its own tenant's lead.
    window_end = now + timedelta(minutes=MAX_LEAD_MINUTES)
    due = await VolunteerAssignmentRepository.due_for_reminder(now, window_end)
    if not due:
        return

    discord_service = DiscordService()
    for assignment in due:
        tenant_id = assignment.tenant_id
        if tenant_id is None:
            continue
        try:
            with tenant_scope(tenant_id):
                lead = await SystemConfigService.get_volunteer_reminder_lead_minutes()
                shift = assignment.shift
                # Not yet within this tenant's lead window — leave un-stamped so a
                # later tick reminds it once it enters the window.
                if shift.starts_at > now + timedelta(minutes=lead):
                    continue
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
                # Close the DM over the tenant scope so its deep links / web-push
                # mirror resolve under the right tenant when the worker runs it.
                discord_queue.enqueue(
                    _scoped_dm(
                        tenant_id,
                        discord_service.send_dm_with_volunteer_acknowledgment_button(
                            int(discord_id), message, assignment.id,
                        ),
                    )
                )
        except Exception:
            logger.exception('volunteer reminder failed for assignment %s', getattr(assignment, 'id', None))


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
