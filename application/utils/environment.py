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
        if not (os.environ.get('DB_USERNAME') or '').strip():
            raise RuntimeError('DB_USERNAME must be set in production.')
        if not (os.environ.get('DB_PASSWORD') or '').strip():
            raise RuntimeError('DB_PASSWORD must be set in production.')
