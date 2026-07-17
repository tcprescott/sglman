"""Serial coroutine worker queue.

A single-consumer FIFO of coroutines drained in order by one background worker
task. A coroutine that raises is logged (traceback preserved so it reaches logs +
Sentry) and swallowed, so the worker never dies. Layer-neutral: both the
notification pipeline (``services.discord_queue``) and the event-dispatch pipeline
(``events.dispatch_queue``) own an instance — one implementation, two queues.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Coroutine
from types import ModuleType
from typing import Optional

_default_logger = logging.getLogger(__name__)


class CoroutineQueue:
    """Owns a queue + its lone worker task.

    ``name`` shapes the worker-error log line (``"{name} worker error"``).
    ``drop_warning`` is the ``stop()`` warning template (one ``%d`` for the count);
    it defaults to a generic message. Pass the owning module's ``logger`` so log
    records are attributed to that module.
    """

    def __init__(
        self,
        name: str,
        *,
        logger: Optional[logging.Logger] = None,
        drop_warning: Optional[str] = None,
    ) -> None:
        self.name = name
        self._logger = logger or _default_logger
        self._drop_warning = drop_warning or (
            f"{name} stopping with %d item(s) still queued — they will not run"
        )
        self._queue: asyncio.Queue[Coroutine] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    async def _worker(self) -> None:
        while True:
            coro = await self._queue.get()
            try:
                await coro
            except Exception:
                self._logger.exception("%s worker error", self.name)
            finally:
                self._queue.task_done()

    def start(self) -> None:
        self._worker_task = asyncio.get_event_loop().create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        pending = self._queue.qsize()
        if pending:
            self._logger.warning(self._drop_warning, pending)
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    def enqueue(self, coro: Coroutine) -> None:
        self._queue.put_nowait(coro)


def bind_module_state(module_name: str, queue: CoroutineQueue) -> None:
    """Expose ``queue``'s ``_queue``/``_worker_task`` as live module globals.

    Both queue modules used to hand-roll module-level ``_queue`` and
    ``_worker_task`` globals; callers and tests reach into them by name. After the
    extraction those live on the ``CoroutineQueue`` instance, so this forwards
    reads and writes of those two names on the module to the instance, keeping the
    pre-extraction surface intact.
    """
    module = sys.modules[module_name]
    proxied = ('_queue', '_worker_task')

    class _BoundModule(ModuleType):
        def __getattr__(self, name: str):
            if name in proxied:
                return getattr(queue, name)
            raise AttributeError(name)

        def __setattr__(self, name: str, value) -> None:
            if name in proxied:
                setattr(queue, name, value)
            else:
                super().__setattr__(name, value)

    module.__class__ = _BoundModule
