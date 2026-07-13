"""Discord Scheduled Events reconciler worker (PR 8).

A background loop (modeled on ``speedgaming_sync_worker`` / ``race_room_worker``)
that periodically reconciles every tenant with a linked Discord guild: its
opted-in tournaments' scheduled matches are mirrored into that guild's Discord
Scheduled Events. Gated by ``DISCORD_EVENTS_SYNC_ENABLED`` (off by default). Each
tenant's reconcile runs inside ``tenant_scope`` acting as the reserved **system
``User``**, so audit/event attribution and the shared-guild safety scoping are
correct even though the loop runs off a timer with no request context.

Per-tenant failures are logged and retried next tick — one bad guild never stops
the others, and the loop itself never dies. Reconciliation is idempotent, so a
tenant whose schedule hasn't changed is a cheap no-op (content hashes match, no
Discord calls).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from application.tenant_context import tenant_scope

logger = logging.getLogger(__name__)

# Reconcile is idempotent and mostly no-op, so a slower tick than the SG/racetime
# workers is plenty — a schedule change surfaces within a few minutes.
TICK_SECONDS = 300

_task: Optional[asyncio.Task] = None


async def _tick() -> None:
    from application.repositories import TenantRepository
    from application.services.discord_event_reconciler_service import DiscordEventReconcilerService
    from application.services.user_service import UserService

    tenants = [t for t in await TenantRepository.list_all() if t.discord_guild_id is not None]
    if not tenants:
        return

    now = datetime.now(timezone.utc)
    system_user = await UserService().get_system_user()
    reconciler = DiscordEventReconcilerService()

    for tenant in tenants:
        try:
            with tenant_scope(tenant.id):
                result = await reconciler.reconcile_tenant(tenant, actor=system_user, now=now)
            if result.created or result.updated or result.cancelled or result.errors:
                logger.info('Discord events reconcile for tenant %s: %s', tenant.id, result.as_dict())
        except Exception:
            logger.exception('Discord events reconcile failed for tenant %s', getattr(tenant, 'id', None))


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except Exception as e:  # never let the loop die
            logger.exception('Discord events reconcile tick failed: %s', e)
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
