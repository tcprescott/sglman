"""Background worker that runs async event subscribers off the request path.

A dedicated clone of ``application.services.discord_queue`` owned by the events
package (so the package imports no service), and separate so a slow webhook
endpoint can never delay Discord DMs. ``publish`` enqueues each async
subscriber's coroutine here; the single worker awaits them in order and logs any
failure without dying.
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Optional

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[Coroutine] = asyncio.Queue()
_worker_task: Optional[asyncio.Task] = None


async def _worker() -> None:
    while True:
        coro = await _queue.get()
        try:
            await coro
        except Exception:
            logger.exception("event dispatch worker error")
        finally:
            _queue.task_done()


def start() -> None:
    global _worker_task
    _worker_task = asyncio.get_event_loop().create_task(_worker())


async def stop() -> None:
    global _worker_task
    if _worker_task is None:
        return
    pending = _queue.qsize()
    if pending:
        logger.warning(
            "event dispatch queue stopping with %d item(s) still queued — they will not run",
            pending,
        )
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None


def enqueue(coro: Coroutine) -> None:
    _queue.put_nowait(coro)
