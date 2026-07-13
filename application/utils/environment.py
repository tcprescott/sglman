"""Environment detection and startup security-config validation.

Centralizes the "are we in production?" check and the fail-fast validation of
security-critical configuration (session secret, DB credentials) so the app
refuses to start in an insecure state rather than silently degrading.
"""

import os


def get_environment() -> str:
    """Return the configured environment name (default: 'development')."""
    return os.environ.get('ENVIRONMENT', 'development').strip().lower()


def is_production() -> bool:
    return get_environment() == 'production'


def get_base_url() -> str:
    """Return the app's external base URL (no trailing slash).

    Single source of truth for links, QR codes, and OAuth redirect building —
    read lazily so tests and tooling can override BASE_URL per call.
    """
    return os.getenv('BASE_URL', 'http://localhost:8000').rstrip('/')


def get_platform_host() -> str:
    """Return the shared platform host (bare ``host[:port]``, no scheme/path).

    This is the host that serves the tenant-agnostic surface (landing page,
    ``/platform``) and every path-mode tenant at ``/t/<slug>``. Defaults to the
    network location of :func:`get_base_url` when ``PLATFORM_HOST`` is unset, so a
    single ``BASE_URL`` configures both in the common single-host deployment.
    Read lazily so tests can override per call.
    """
    explicit = (os.getenv('PLATFORM_HOST') or '').strip()
    if explicit:
        return explicit.lower()
    from urllib.parse import urlparse
    return (urlparse(get_base_url()).netloc or 'localhost:8000').lower()


def telemetry_enabled() -> bool:
    """Whether engagement telemetry capture is on (default: on).

    A kill-switch for the behavioral capture path (page views, interactions,
    and the domain-event mirror). Set ``TELEMETRY_ENABLED`` to a falsey value
    (``0``/``false``/``no``/``off``) to disable capture without a redeploy of
    code — reads are unaffected, they just show whatever was already recorded.
    """
    raw = os.environ.get('TELEMETRY_ENABLED')
    if raw is None:
        return True
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def racetime_bot_enabled() -> bool:
    """Master switch for the racetime bot runtime (default: off).

    The connection loop only spins up when ``RACETIME_BOT_ENABLED`` is truthy.
    Off by default so a deployment without configured racetime bots — the common
    case — never opens outbound connections. Independent of ``MOCK_RACETIME``:
    the switch says "run the runtime", the mock flag says "run it against a
    scripted fake instead of live racetime".
    """
    return os.environ.get('RACETIME_BOT_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')


def speedgaming_sync_enabled() -> bool:
    """Master switch for the SpeedGaming ETL sync worker (default: off).

    The background poll loop only spins up when ``SPEEDGAMING_SYNC_ENABLED`` is
    truthy. Off by default so a deployment with no configured SG event links —
    the common case — never opens outbound polls. Independent of
    ``MOCK_SPEEDGAMING``: the switch says "run the worker", the mock flag says
    "run it against scripted fixtures instead of the live SG API".
    """
    return os.environ.get('SPEEDGAMING_SYNC_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')


def discord_events_sync_enabled() -> bool:
    """Master switch for the Discord Scheduled Events reconciler worker (default: off).

    The background reconcile loop only spins up when ``DISCORD_EVENTS_SYNC_ENABLED``
    is truthy. Off by default so a deployment with no opted-in tournaments — the
    common case — never touches Discord on a timer. The reconciler still runs
    on-demand from the admin UI regardless of this switch; this only gates the
    periodic worker. Independent of ``MOCK_DISCORD`` (which swaps the transport).
    """
    return os.environ.get('DISCORD_EVENTS_SYNC_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')


def validate_security_config() -> None:
    """Fail fast when security-critical configuration is missing.

    Always requires STORAGE_SECRET (it signs the session that the entire
    authorization model trusts). In production it additionally requires
    non-empty DB credentials. Raising here aborts startup before any request
    can be served with an insecure session store.
    """
    storage_secret = (os.environ.get('STORAGE_SECRET') or '').strip()
    if not storage_secret:
        raise RuntimeError(
            'STORAGE_SECRET is required: it signs the NiceGUI session store that '
            'holds authentication state. Set a strong random value.'
        )

    if is_production():
        if len(storage_secret) < 32:
            raise RuntimeError(
                'STORAGE_SECRET must be at least 32 characters in production: it '
                'signs the session store the entire authorization model trusts. '
                'Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.'
            )
        if not (os.environ.get('DB_USERNAME') or '').strip():
            raise RuntimeError('DB_USERNAME must be set in production.')
        if not (os.environ.get('DB_PASSWORD') or '').strip():
            raise RuntimeError('DB_PASSWORD must be set in production.')
