"""Sentry error-monitoring initialization.

Wires the Sentry Python SDK into the application. Initialization is a no-op
unless ``SENTRY_DSN`` is set, so local development and tests are unaffected.

The SDK auto-instruments FastAPI/Starlette and the stdlib ``logging`` module,
so once initialized it captures unhandled exceptions across the request path,
the NiceGUI pages, and the Discord bot (all run in the same process), plus any
``logger.error``/``logger.exception`` records emitted anywhere in the codebase.
"""

import logging
import os
from typing import Any, Dict, Optional

import sentry_sdk

from application.utils.environment import get_environment

logger = logging.getLogger(__name__)

# Request headers that must never leave the process in an error report.
_SENSITIVE_HEADERS = {'authorization', 'cookie', 'set-cookie', 'x-api-key'}


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


def init_sentry() -> None:
    """Initialize Sentry when ``SENTRY_DSN`` is configured; otherwise do nothing.

    Must be called before the FastAPI app and middleware are constructed so the
    SDK's instrumentation wraps them.
    """
    dsn = (os.environ.get('SENTRY_DSN') or '').strip()
    if not dsn:
        logger.debug('SENTRY_DSN not set — Sentry reporting disabled.')
        return

    # Errors-only by default; tracing can be enabled later purely via env var.
    try:
        traces_sample_rate = float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0') or '0')
    except ValueError:
        traces_sample_rate = 0.0

    sentry_sdk.init(
        dsn=dsn,
        environment=get_environment(),
        send_default_pii=False,
        before_send=_scrub_event,
        traces_sample_rate=traces_sample_rate,
    )
    logger.info('Sentry initialized (environment=%s).', get_environment())
