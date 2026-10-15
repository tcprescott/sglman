"""Tests for the event-loop watchdog and the runtime snapshot built on it."""

import asyncio
import logging
import time

import pytest

from application.utils import loop_watchdog as wd
from application.utils import runtime_stats
from application.utils.background_loop import BackgroundLoop, worker_stats


def _block_the_loop(seconds: float) -> None:
    time.sleep(seconds)


@pytest.fixture
def fast_watchdog(monkeypatch):
    monkeypatch.setattr(wd, 'WARN_SECONDS', 0.1)
    monkeypatch.setattr(wd, 'ERROR_SECONDS', 0.3)
    monkeypatch.setattr(wd, '_BEAT_SECONDS', 0.02)
    dog = wd.LoopWatchdog()
    yield dog
    dog.stop()


async def _settle(dog: wd.LoopWatchdog, stalls: int) -> None:
    for _ in range(100):
        if dog.snapshot()['stalls_since_start'] >= stalls:
            return
        await asyncio.sleep(0.02)


class TestLoopWatchdog:
    async def test_a_quiet_loop_records_lag_but_no_stall(self, fast_watchdog):
        fast_watchdog.start()
        await asyncio.sleep(0.2)
        snap = fast_watchdog.snapshot()
        assert snap['running']
        assert snap['lag_ms_p95'] is not None
        assert snap['stalls_since_start'] == 0

    async def test_a_block_names_the_function_that_did_it(self, fast_watchdog, caplog):
        fast_watchdog.start()
        await asyncio.sleep(0.05)
        with caplog.at_level(logging.WARNING, logger=wd.__name__):
            _block_the_loop(0.2)
            await _settle(fast_watchdog, 1)
        stall = fast_watchdog.snapshot()['recent_stalls'][0]
        assert '_block_the_loop' in stall['culprit']
        assert 'tests/utils/test_loop_watchdog.py' in stall['culprit']
        record = next(r for r in caplog.records if 'Event loop was blocked' in r.getMessage())
        assert record.levelno == logging.WARNING

    async def test_a_long_block_is_an_error(self, fast_watchdog, caplog):
        fast_watchdog.start()
        await asyncio.sleep(0.05)
        with caplog.at_level(logging.WARNING, logger=wd.__name__):
            _block_the_loop(0.4)
            await _settle(fast_watchdog, 1)
        record = next(r for r in caplog.records if 'Event loop was blocked' in r.getMessage())
        assert record.levelno == logging.ERROR

    async def test_start_is_idempotent_and_stop_ends_the_thread(self, fast_watchdog):
        fast_watchdog.start()
        thread = fast_watchdog._thread
        fast_watchdog.start()
        assert fast_watchdog._thread is thread
        fast_watchdog.stop()
        assert not fast_watchdog.running


class TestWorkerStats:
    async def test_ticks_are_timed_and_failures_counted(self):
        calls = []

        async def tick():
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('boom')

        loop = BackgroundLoop(tick, interval=0.01, name='zz test worker')
        loop.start()
        for _ in range(100):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.01)
        await loop.stop()
        stats = next(s for s in worker_stats() if s['name'] == 'zz test worker')
        assert stats['ticks'] >= 3
        assert stats['failures'] == 1
        assert stats['last_tick_seconds'] is not None
        assert stats['running'] is False


class TestRuntimeSnapshot:
    async def test_collect_never_raises_and_has_every_section(self):
        snap = runtime_stats.collect()
        for key in ('uptime_seconds', 'rss_mb', 'clients', 'db_pool', 'event_loop', 'workers'):
            assert key in snap
        assert snap['asyncio_tasks'] >= 1
