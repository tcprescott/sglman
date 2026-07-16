"""Reusable background-worker loop skeleton.

Every periodic worker (racetime room auto-open, SpeedGaming sync, Discord event
reconcile, service-health monitor, volunteer reminders) hand-rolls the same
``_loop``/``start``/``stop`` + module-global ``_task`` scaffold: a loop that awaits
a ``tick`` coroutine, logs and swallows any failure so it never dies, sleeps a
fixed interval, and can be started once and cancelled cleanly.

:class:`BackgroundLoop` captures that skeleton; a worker keeps a module-level
instance and delegates its ``start``/``stop`` to it. :func:`for_each_tenant_scoped`
captures the companion per-item pattern — iterate a batch, run each item's work
inside its own ``tenant_scope`` with per-item error isolation — so a tick that
fans out over tenant-scoped rows stays a few lines.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

from application.tenant_context import tenant_scope

_default_logger = logging.getLogger(__name__)

T = TypeVar('T')

TickFn = Callable[[], Awaitable[None]]


class BackgroundLoop:
    """A single periodic worker task: run ``tick`` every ``interval`` seconds.

    ``start`` is idempotent (a second call while running is a no-op). A failing
    ``tick`` is logged (``"{name} tick failed: ..."``) and the loop continues.
    ``stop`` cancels the task and clears it, and is safe to call when never
    started.
    """

    def __init__(
        self,
        tick: TickFn,
        *,
        interval: float,
        name: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._tick = tick
        self._interval = interval
        self.name = name
        self._logger = logger or _default_logger
        self._task: Optional[asyncio.Task] = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as e:  # never let the loop die
                self._logger.exception('%s tick failed: %s', self.name, e)
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_event_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None


def run_worker_loop(
    tick: TickFn,
    interval: float,
    name: str,
    logger: Optional[logging.Logger] = None,
) -> BackgroundLoop:
    """Construct a :class:`BackgroundLoop` (not yet started).

    Convenience factory so a worker can write
    ``_loop = run_worker_loop(_tick, TICK_SECONDS, 'my worker', logger)`` and
    delegate its ``start``/``stop`` to it.
    """
    return BackgroundLoop(tick, interval=interval, name=name, logger=logger)


async def for_each_tenant_scoped(
    items: Iterable[T],
    handle: Callable[[T], Awaitable[None]],
    *,
    tenant_id_of: Callable[[T], Optional[int]],
    logger: Optional[logging.Logger] = None,
    describe: Callable[[T], object] = repr,
) -> None:
    """Run ``handle(item)`` for each item inside its own ``tenant_scope``.

    Items whose ``tenant_id_of`` is ``None`` are skipped; a per-item failure is
    logged (with ``describe(item)`` for context) and isolated so the rest of the
    batch still runs. This is the fan-out shape shared by the tenant-scoped ticks.
    """
    log = logger or _default_logger
    for item in items:
        tenant_id = tenant_id_of(item)
        if tenant_id is None:
            continue
        try:
            with tenant_scope(tenant_id):
                await handle(item)
        except Exception:
            log.exception('scoped work failed for %s', describe(item))
