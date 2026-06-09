import asyncio
from collections.abc import Coroutine
from typing import Optional

_queue: asyncio.Queue[Coroutine] = asyncio.Queue()
_worker_task: Optional[asyncio.Task] = None


async def _worker() -> None:
    while True:
        coro = await _queue.get()
        try:
            await coro
        except Exception as e:
            print(f"[discord_queue] worker error: {e}")
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
        print(f"[discord_queue] stopping with {pending} item(s) still queued — they will not be sent")
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None


def enqueue(coro: Coroutine) -> None:
    _queue.put_nowait(coro)
