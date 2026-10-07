"""Sentry error-monitoring initialization.

Wires the Sentry Python SDK into the application. Initialization is a no-op
unless ``SENTRY_DSN`` is set, so local development and tests are unaffected.

The SDK auto-instruments FastAPI/Starlette and the stdlib ``logging`` module,
so once initialized it captures unhandled exceptions across the request path,
the NiceGUI pages, and the Discord bot (all run in the same process), plus any
``logger.error``/``logger.exception`` records emitted anywhere in the codebase.

Three things on top of the SDK defaults make an event diagnosable mid-event:

* **Release** (``SENTRY_RELEASE``, else ``GIT_SHA`` baked into the image) so a
  regression points at the deploy that introduced it.
* **Sentry Logs** at INFO and up (``SENTRY_LOGS_LEVEL``), so the lines around an
  error are readable in Sentry without shell access to the container. DEBUG and
  TRACE, which a super-admin can switch on per module from ``/platform``, stay
  in the container log.
* **Ambient tags** on every event and log: the tenant in scope and, inside a
  NiceGUI websocket handler where the request-scoped user is gone, the signed-in
  user. Workers, queues and bot handlers add their own with :func:`sentry_tags`.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger_for_sentry_logs

from application.tenant_context import get_current_tenant_id
from application.utils.environment import get_environment, is_production
from application.utils.log_levels import level_number
from application.utils.timer_teardown import is_timer_teardown_race

logger = logging.getLogger(__name__)

# Request headers that must never leave the process in an error report.
_SENSITIVE_HEADERS = {'authorization', 'cookie', 'set-cookie', 'x-api-key'}

#: Production's default share of requests traced when SENTRY_TRACES_SAMPLE_RATE
#: is unset: enough to see slow pages and slow DB/HTTP calls at event load.
_PRODUCTION_TRACES_SAMPLE_RATE = 0.1

#: One line per HTTP request or outbound call: useful in the container log,
#: pure quota burn in Sentry Logs.
_NOISY_FOR_SENTRY_LOGS = ('uvicorn.access', 'httpx', 'httpcore')


def _scrub_event(event: Dict[str, Any], hint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip auth headers and cookies from outgoing Sentry events.

    Defense in depth alongside ``send_default_pii=False``: ensures bearer
    tokens / session cookies are never transmitted even if an integration
    attaches request data.
    """
    request = event.get('request')
    if isinstance(request, dict):
        headers = request.get('headers')
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = '[Filtered]'
        request.pop('cookies', None)
    return event


def _session_user() -> Optional[Dict[str, Any]]:
    """The signed-in user from the NiceGUI session, or None outside one.

    ``AuthMiddleware`` sets the Sentry user on the HTTP request's scope, but a
    button click arrives over the websocket after that scope is gone, so an
    error in a UI handler would otherwise carry no user at all.
    """
    try:
        from nicegui import app
        storage = app.storage.user
        discord_id = storage.get('discord_id')
    except Exception:
        return None
    if discord_id is None:
        return None
    return {'id': str(discord_id), 'username': storage.get('username')}


def _enrich_event(event: Dict[str, Any]) -> Dict[str, Any]:
    tenant_id = get_current_tenant_id()
    if tenant_id is not None:
        tags = event.get('tags')
        if isinstance(tags, dict):
            tags.setdefault('tenant_id', str(tenant_id))
        elif tags is None:
            event['tags'] = {'tenant_id': str(tenant_id)}
    if not event.get('user'):
        user = _session_user()
        if user is not None:
            event['user'] = user
    return event


def _before_send(event: Dict[str, Any], hint: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Drop the NiceGUI timer-teardown race, then enrich and scrub what's left.

    The ``nicegui`` logger filter already stops it reaching the logging hook;
    this catches the same exception arriving by any other integration.
    """
    exc_info = (hint or {}).get('exc_info')
    if exc_info and exc_info[1] is not None and is_timer_teardown_race(exc_info[1]):
        return None
    try:
        _enrich_event(event)
    except Exception:
        pass
    return _scrub_event(event, hint)


def _before_send_log(log: Dict[str, Any], hint: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Stamp the tenant on each Sentry Log so they filter like events do."""
    try:
        tenant_id = get_current_tenant_id()
        if tenant_id is not None:
            log.setdefault('attributes', {})['tenant_id'] = tenant_id
    except Exception:
        pass
    return log


def _traces_sample_rate() -> float:
    raw = (os.environ.get('SENTRY_TRACES_SAMPLE_RATE') or '').strip()
    if not raw:
        return _PRODUCTION_TRACES_SAMPLE_RATE if is_production() else 0.0
    try:
        return min(max(float(raw), 0.0), 1.0)
    except ValueError:
        return 0.0


def _sentry_logs_level() -> Optional[int]:
    """The minimum level shipped to Sentry Logs; ``None`` turns them off."""
    raw = (os.environ.get('SENTRY_LOGS_LEVEL') or 'INFO').strip()
    if raw.lower() in ('off', 'none', 'false', '0'):
        return None
    try:
        return level_number(raw)
    except ValueError:
        return logging.INFO


def _release() -> Optional[str]:
    explicit = (os.environ.get('SENTRY_RELEASE') or '').strip()
    if explicit:
        return explicit
    sha = (os.environ.get('GIT_SHA') or '').strip()
    return f'wizzrobe@{sha[:12]}' if sha else None


def init_sentry() -> None:
    """Initialize Sentry when ``SENTRY_DSN`` is configured; otherwise do nothing.

    Must be called before the FastAPI app and middleware are constructed so the
    SDK's instrumentation wraps them.
    """
    dsn = (os.environ.get('SENTRY_DSN') or '').strip()
    if not dsn:
        logger.debug('SENTRY_DSN not set — Sentry reporting disabled.')
        return

    logs_level = _sentry_logs_level()
    for name in _NOISY_FOR_SENTRY_LOGS:
        ignore_logger_for_sentry_logs(name)

    sentry_sdk.init(
        dsn=dsn,
        environment=get_environment(),
        release=_release(),
        send_default_pii=False,
        before_send=_before_send,  # type: ignore[arg-type]
        traces_sample_rate=_traces_sample_rate(),
        enable_logs=logs_level is not None,
        before_send_log=_before_send_log,  # type: ignore[arg-type]
        integrations=[
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
                sentry_logs_level=logs_level,
            ),
        ],
    )
    logger.info(
        'Sentry initialized (environment=%s, release=%s, traces=%s, logs=%s).',
        get_environment(), _release() or 'unset', _traces_sample_rate(),
        logging.getLevelName(logs_level) if logs_level is not None else 'off',
    )


@contextmanager
def sentry_tags(**tags: Any) -> Iterator[None]:
    """Tag every Sentry event raised or logged inside the block.

    Forks the current scope, so the tags vanish when the block exits and never
    leak onto the next unrelated event (a worker's next tick, the queue's next
    item). ``None`` values are skipped. Safe with Sentry disabled.
    """
    with sentry_sdk.new_scope() as scope:
        for key, value in tags.items():
            if value is not None:
                scope.set_tag(key, str(value))
        yield


def tag_current_scope(**tags: Any) -> None:
    """Add tags to the scope already in effect, for a value learned mid-block.

    Meant for use inside :func:`sentry_tags`, whose forked scope bounds them.
    """
    scope = sentry_sdk.get_current_scope()
    for key, value in tags.items():
        if value is not None:
            scope.set_tag(key, str(value))
