"""Helper for detecting whether the mock Twitch layer is enabled.

The mock layer lets local development exercise the full Twitch account-linking
flow (link, unlink) without registering a real Twitch OAuth application. It must
never be active in production: the link page would record a fake verified Twitch
identity. As with ``MOCK_DISCORD`` we refuse to start in that case.
"""

from application.utils.environment import env_flag, is_production


def is_mock_twitch() -> bool:
    """Return True when MOCK_TWITCH is enabled (and not in production)."""
    enabled = env_flag('MOCK_TWITCH')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_TWITCH must not be enabled in production: it fakes the Twitch '
            'OAuth link. Unset MOCK_TWITCH or change ENVIRONMENT.'
        )
    return enabled
