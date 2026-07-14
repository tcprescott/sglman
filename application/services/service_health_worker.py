"""Platform service-health monitor worker (PR 5).

A background loop (modeled on ``discord_event_worker``) that periodically refreshes
every dependency probe, keeping the ``/platform`` health board warm and driving the
alert-on-transition path without anyone loading the page. Gated by
``SERVICE_HEALTH_ENABLED`` (off by default); the board still refreshes on demand
from the UI regardless.

Runs with **no tenant scope** — every probe is platform-level (the racetime and
Challonge probes read across all tenants via explicitly-unscoped queries). The loop
never dies: a failing tick is logged and retried next interval.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Probes reach external hosts, so a gentle cadence is plenty — an outage surfaces
# within a couple of minutes, and the board can always be force-refreshed.
TICK_SECONDS = 120

_task: Optional[asyncio.Task] = None


async def _tick() -> None:
    from application.services.service_health_service import ServiceHealthService
    results = await ServiceHealthService().refresh()
    unhealthy = [r for r in results if r.status.value in ('down', 'credential_warning', 'degraded')]
    if unhealthy:
        logger.info('Service health: %s dependency/dependencies need attention: %s',
                    len(unhealthy), ', '.join(f'{r.label}={r.status.value}' for r in unhealthy))


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except Exception as e:  # never let the loop die
            logger.exception('Service health tick failed: %s', e)
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
