"""Helper for detecting whether the mock Twitch layer is enabled.

The mock layer lets local development exercise the full Twitch account-linking
flow (link, unlink) without registering a real Twitch OAuth application. It must
never be active in production: the link page would record a fake verified Twitch
identity. As with ``MOCK_DISCORD`` we refuse to start in that case.
"""

import os

from application.utils.environment import is_production


def is_mock_twitch() -> bool:
    """Return True when MOCK_TWITCH is enabled (and not in production)."""
    enabled = os.environ.get('MOCK_TWITCH', '').lower() in ('1', 'true', 'yes')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_TWITCH must not be enabled in production: it fakes the Twitch '
            'OAuth link. Unset MOCK_TWITCH or change ENVIRONMENT.'
        )
    return enabled
