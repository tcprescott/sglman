"""Helper for detecting whether the mock Discord layer is enabled."""

from application.utils.environment import env_flag, is_production


def is_mock_discord() -> bool:
    """Return True when MOCK_DISCORD is enabled.

    The mock layer turns ``/login`` into a public, unauthenticated user picker
    that can impersonate any user (including STAFF) or mint new privileged
    users. That is a complete authentication bypass, so it must never be active
    in production: if MOCK_DISCORD is set truthy while ENVIRONMENT=production we
    refuse to start rather than silently expose the bypass.
    """
    enabled = env_flag('MOCK_DISCORD')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_DISCORD must not be enabled in production: it bypasses Discord '
            'OAuth and allows anyone to log in as any user. Unset MOCK_DISCORD or '
            'change ENVIRONMENT.'
        )
    return enabled
