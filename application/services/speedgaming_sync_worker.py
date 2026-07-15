"""SpeedGaming ETL sync worker (PR 7).

A background loop (modeled on ``race_room_worker`` / ``volunteer_reminder``) that
polls each active :class:`SpeedGamingEventLink` on its configured cadence and
runs the ETL to materialize SG episodes into ``Match`` rows. Gated by
``SPEEDGAMING_SYNC_ENABLED`` (off by default). Each link's work runs inside
``tenant_scope`` (the link's tenant) acting as the reserved **system ``User``**,
so audit/event attribution and tenant scoping are correct even though the loop
runs off a timer with no request context.

Per-link failures are logged and retried next tick — one bad event slug never
stops the others, and the loop itself never dies.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from application.tenant_context import tenant_scope

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

_task: Optional[asyncio.Task] = None


async def _tick() -> None:
    from application.repositories import SpeedGamingEventLinkRepository
    from application.services.feature_flag_service import FeatureFlagService
    from application.services.speedgaming_etl_service import SpeedGamingETLService
    from application.services.user_service import UserService
    from models import FeatureFlag

    repo = SpeedGamingEventLinkRepository()
    links = await repo.list_active_all()
    if not links:
        return

    now = datetime.now(timezone.utc)
    system_user = await UserService().get_system_user()
    etl = SpeedGamingETLService()

    for link in links:
        tenant_id = link.tenant_id
        if tenant_id is None:
            continue
        interval = timedelta(minutes=link.sync_interval_minutes or 15)
        if link.last_synced_at is not None and now - link.last_synced_at < interval:
            continue  # not due yet on this link's cadence
        try:
            with tenant_scope(tenant_id):
                if not await FeatureFlagService().is_enabled(FeatureFlag.SPEEDGAMING_ETL):
                    continue  # tenant has SpeedGaming sync disabled
                result = await etl.sync_event_link(link, actor=system_user, now=now)
            logger.info(
                'SG sync for link %s (%s): %s',
                link.id, link.event_slug, result.as_dict(),
            )
        except Exception:
            logger.exception('SG sync failed for event link %s', getattr(link, 'id', None))


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except Exception as e:  # never let the loop die
            logger.exception('SpeedGaming sync tick failed: %s', e)
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
