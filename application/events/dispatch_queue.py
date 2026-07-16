"""Background worker that runs async event subscribers off the request path.

A dedicated instance of the shared ``CoroutineQueue`` owned by the events package
(so the package imports no service), and separate so a slow webhook endpoint can
never delay Discord DMs. ``publish`` enqueues each async subscriber's coroutine
here; the single worker awaits them in order and logs any failure without dying.
"""

import logging
from collections.abc import Coroutine

from application.utils.coroutine_queue import CoroutineQueue, bind_module_state

logger = logging.getLogger(__name__)

_q = CoroutineQueue(
    'event dispatch',
    logger=logger,
    drop_warning=(
        'event dispatch queue stopping with %d item(s) still queued — '
        'they will not run'
    ),
)
bind_module_state(__name__, _q)


def start() -> None:
    _q.start()


async def stop() -> None:
    await _q.stop()


def enqueue(coro: Coroutine) -> None:
    _q.enqueue(coro)
