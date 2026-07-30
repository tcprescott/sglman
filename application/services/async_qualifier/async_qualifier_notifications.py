"""Async qualifier — the runner-facing Discord DMs.

Best-effort by construction: a DM must never block a review or a granted
reattempt, so every send is wrapped and swallowed here rather than at each call
site. The message text itself lives in
:mod:`application.utils.discord_messages`, per that module's rule that no service
inlines DM copy.

Split out of :class:`AsyncQualifierService` to keep that module inside the
file-length guideline; it is a service-layer peer, so it may reach the ORM and
the Discord service.
"""

import logging
from typing import Optional

from application.utils.discord_messages import (
    qualifier_reattempt_granted_dm,
    qualifier_run_reviewed_dm,
)
from application.utils.tenant_urls import tenant_url
from models import AsyncQualifierRun

logger = logging.getLogger(__name__)


async def notify_run_reviewed(run: AsyncQualifierRun, approved: bool, reason: str = '') -> None:
    """Tell the runner the verdict, the reason behind it, and where to look."""
    try:
        await run.fetch_related('user', 'qualifier', 'tenant')
        discord_id = run.user.discord_id
        if not discord_id or run.user.is_placeholder:
            return
        from application.services.discord.discord_service import DiscordService
        await DiscordService().send_dm(
            int(discord_id),
            qualifier_run_reviewed_dm(
                run.qualifier.name, approved=approved, reason=reason,
                qualifier_url=_qualifier_url(run),
            ),
        )
    except Exception:
        logger.debug("Failed to DM run-reviewed notification", exc_info=True)


async def notify_reattempt_granted(run: AsyncQualifierRun, reason: str) -> None:
    """Tell the runner a reviewer freed their pool slot — a change they did not make."""
    try:
        await run.fetch_related('user', 'qualifier', 'tenant', 'permalink__pool')
        discord_id = run.user.discord_id
        if not discord_id or run.user.is_placeholder:
            return
        pool = run.permalink.pool.name if run.permalink and run.permalink.pool else ''
        from application.services.discord.discord_service import DiscordService
        await DiscordService().send_dm(
            int(discord_id),
            qualifier_reattempt_granted_dm(
                run.qualifier.name, pool, reason=reason, qualifier_url=_qualifier_url(run),
            ),
        )
    except Exception:
        logger.debug("Failed to DM reattempt-granted notification", exc_info=True)


def _qualifier_url(run: AsyncQualifierRun) -> Optional[str]:
    return tenant_url(run.tenant, f'/qualifiers/{run.qualifier_id}') if run.tenant else ''
