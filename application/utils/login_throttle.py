"""A light, in-process limit on failed password sign-ins.

Single worker, so a module-level window is enough. Counted per sign-in name
(guessing one account's password) and per browser (trying many names). There
is deliberately no per-IP limit: venue Wi-Fi puts a whole event behind one
address, and one person's typos must not lock the room out.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

WINDOW_SECONDS = 300.0
MAX_FAILURES_PER_NAME = 10
MAX_FAILURES_PER_BROWSER = 20
_MAX_KEYS = 10_000

_failures: Dict[str, Deque[float]] = defaultdict(deque)


def _prune(key: str, now: float) -> Deque[float]:
    hits = _failures[key]
    while hits and hits[0] < now - WINDOW_SECONDS:
        hits.popleft()
    return hits


def _keys(login_name: str, browser_id: Optional[str]) -> list[tuple[str, int]]:
    keys = [(f'name:{login_name}', MAX_FAILURES_PER_NAME)]
    if browser_id:
        keys.append((f'browser:{browser_id}', MAX_FAILURES_PER_BROWSER))
    return keys


def is_blocked(login_name: str, browser_id: Optional[str]) -> bool:
    now = time.monotonic()
    return any(len(_prune(key, now)) >= limit for key, limit in _keys(login_name, browser_id))


def record_failure(login_name: str, browser_id: Optional[str]) -> None:
    now = time.monotonic()
    if len(_failures) > _MAX_KEYS:
        for key in [k for k, v in _failures.items() if not v or v[-1] < now - WINDOW_SECONDS]:
            del _failures[key]
        if len(_failures) > _MAX_KEYS:
            _failures.clear()
    for key, _ in _keys(login_name, browser_id):
        _prune(key, now).append(now)


def record_success(login_name: str) -> None:
    _failures.pop(f'name:{login_name}', None)


def reset() -> None:
    _failures.clear()
