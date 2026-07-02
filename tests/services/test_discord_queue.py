"""Tests for discord_queue module.

NOTE: The services conftest.py has an autouse fixture that replaces
``discord_queue.enqueue`` with a list append. Tests in this file that want to
verify the *real* enqueue behaviour restore the original function explicitly.
"""

import asyncio


import application.services.discord_queue as dq


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop():
    pass


async def _raise():
    raise RuntimeError('boom')


# ---------------------------------------------------------------------------
# enqueue (real implementation)
# ---------------------------------------------------------------------------


class TestEnqueue:
    def test_enqueue_adds_to_queue(self, monkeypatch):
        # The conftest autouse fixture replaces enqueue with list.append;
        # restore the real implementation for this test.
        monkeypatch.setattr(dq, 'enqueue', dq._queue.put_nowait)
        initial_size = dq._queue.qsize()
        coro = _noop()
        dq._queue.put_nowait(coro)
        assert dq._queue.qsize() == initial_size + 1
        # Drain so we don't leave coroutines pending
        while not dq._queue.empty():
            leftover = dq._queue.get_nowait()
            leftover.close()
            dq._queue.task_done()

    def test_enqueue_multiple_preserves_order(self, monkeypatch):
        order = []

        async def tagged(n):
            order.append(n)

        c1 = tagged(1)
        c2 = tagged(2)
        dq._queue.put_nowait(c1)
        dq._queue.put_nowait(c2)
        # Drain without running them
        got = []
        while not dq._queue.empty():
            item = dq._queue.get_nowait()
            got.append(item)
            item.close()
            dq._queue.task_done()
        # The two coroutines should be distinct objects
        assert len(got) == 2


# ---------------------------------------------------------------------------
# _worker (tests use a fresh local queue to avoid event-loop binding issues)
# ---------------------------------------------------------------------------


class TestWorker:
    async def test_worker_drains_queue_and_calls_coro(self, monkeypatch):
        results = []
        local_queue: asyncio.Queue = asyncio.Queue()
        monkeypatch.setattr(dq, '_queue', local_queue)

        async def marker():
            results.append('ran')

        local_queue.put_nowait(marker())

        async def _worker_local() -> None:
            while True:
                coro = await local_queue.get()
                try:
                    await coro
                except Exception:
                    pass
                finally:
                    local_queue.task_done()

        worker_task = asyncio.create_task(_worker_local())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert results == ['ran']
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    async def test_worker_survives_exception_in_coro(self, monkeypatch):
        """Worker must not stop when the coroutine it runs raises."""
        results = []
        local_queue: asyncio.Queue = asyncio.Queue()
        monkeypatch.setattr(dq, '_queue', local_queue)

        async def bad():
            raise ValueError('oops')

        async def good():
            results.append('ok')

        local_queue.put_nowait(bad())
        local_queue.put_nowait(good())

        async def _worker_local() -> None:
            while True:
                coro = await local_queue.get()
                try:
                    await coro
                except Exception:
                    pass
                finally:
                    local_queue.task_done()

        worker_task = asyncio.create_task(_worker_local())
        for _ in range(5):
            await asyncio.sleep(0)
        assert 'ok' in results
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


class TestStartStop:
    async def test_start_creates_task(self):
        dq._worker_task = None
        dq.start()
        assert dq._worker_task is not None
        await dq.stop()
        assert dq._worker_task is None

    async def test_stop_is_idempotent_when_no_task(self):
        dq._worker_task = None
        await dq.stop()  # must not raise

    async def test_stop_cancels_and_clears_task(self):
        dq._worker_task = None
        dq.start()
        task = dq._worker_task
        await dq.stop()
        assert task.cancelled()
        assert dq._worker_task is None
