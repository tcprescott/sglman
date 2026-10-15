"""A point-in-time picture of this process's load, for diagnosing a slow app.

Read by :class:`~application.services.runtime_stats_service.RuntimeStatsService`
and served through the super-admin ``runtime_stats`` MCP tool, so a Claude
session can see live load without shell access to the host. Every probe is
best-effort: a figure the platform cannot provide comes back ``None`` rather
than failing the whole snapshot.
"""

from __future__ import annotations

import asyncio
import os
import resource
import sys
import time
from typing import Any, Dict, Optional

from application.utils import live_audience
from application.utils.background_loop import worker_stats
from application.utils.loop_watchdog import watchdog

_PROCESS_STARTED = time.time()


def _rss_mb() -> Optional[float]:
    try:
        with open('/proc/self/status') as status:
            for line in status:
                if line.startswith('VmRSS:'):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    try:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 * 1024 if sys.platform == 'darwin' else 1024), 1)
    except Exception:
        return None


def _clients() -> Dict[str, Optional[int]]:
    try:
        from nicegui import Client
        instances = list(Client.instances.values())
    except Exception:
        return {'total': None, 'connected': None}
    return {
        'total': len(instances),
        'connected': sum(1 for c in instances if c.has_socket_connection),
    }


def _db_pool() -> Dict[str, Optional[int]]:
    try:
        from tortoise import Tortoise
        pool = getattr(Tortoise.get_connection('default'), '_pool', None)
        if pool is None:
            return {'size': None, 'idle': None, 'max': None}
        return {'size': pool.get_size(), 'idle': pool.get_idle_size(), 'max': pool.get_max_size()}
    except Exception:
        return {'size': None, 'idle': None, 'max': None}


def _watch_pages() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for tenant_id in live_audience.tenant_ids():
        snap = live_audience.snapshot(tenant_id)
        out[str(tenant_id)] = {
            'live_viewers': snap.live_viewers,
            'static_readers': snap.static_readers,
            'arrivals_last_minute': snap.arrivals_last_minute,
            'static_mode_tripped': snap.tripped,
        }
    return out


def collect() -> Dict[str, Any]:
    try:
        tasks: Optional[int] = len(asyncio.all_tasks())
    except RuntimeError:
        tasks = None
    return {
        'collected_at': time.time(),
        'uptime_seconds': round(time.time() - _PROCESS_STARTED),
        'release': os.environ.get('SENTRY_RELEASE') or os.environ.get('GIT_SHA') or None,
        'rss_mb': _rss_mb(),
        'asyncio_tasks': tasks,
        'clients': _clients(),
        'db_pool': _db_pool(),
        'event_loop': watchdog.snapshot(),
        'workers': worker_stats(),
        'watch_pages_by_tenant_id': _watch_pages(),
    }
