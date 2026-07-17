"""Serial Discord-notification queue.

A single instance of the shared ``CoroutineQueue`` — the one chokepoint every
Discord notification flows through. ``enqueue`` puts a send coroutine on the
queue; the lone worker awaits them in order and logs (never swallows silently)
any failure so it reaches logs + Sentry.
"""

import logging
from collections.abc import Coroutine

from application.utils.coroutine_queue import CoroutineQueue, bind_module_state

logger = logging.getLogger(__name__)

_q = CoroutineQueue(
    'discord_queue',
    logger=logger,
    drop_warning='discord_queue stopping with %d item(s) still queued — they will not be sent',
)
bind_module_state(__name__, _q)


def start() -> None:
    _q.start()


async def stop() -> None:
    await _q.stop()


def enqueue(coro: Coroutine) -> None:
    _q.enqueue(coro)
