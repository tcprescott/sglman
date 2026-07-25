"""Helper for detecting whether the mock racetime.gg layer is enabled.

The mock layer lets local development exercise the full racetime account-linking
flow (link, unlink) without registering a real racetime OAuth application. It
must never be active in production: the link page would record a fake verified
racetime identity. As with ``MOCK_DISCORD``/``MOCK_TWITCH`` we refuse to start in
that case.

``MOCK_RACETIME`` also gates the bot runtime added in a later PR; this module
covers the identity half — both share the one production-refusal switch.
"""

from application.utils.environment import env_flag, is_production


def is_mock_racetime() -> bool:
    """Return True when MOCK_RACETIME is enabled (and not in production)."""
    enabled = env_flag('MOCK_RACETIME')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_RACETIME must not be enabled in production: it fakes the '
            'racetime OAuth link. Unset MOCK_RACETIME or change ENVIRONMENT.'
        )
    return enabled
