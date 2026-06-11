"""Helper for detecting whether the mock Challonge layer is enabled.

The mock layer lets local development exercise the full Challonge flow
(connect, link, sync, schedule, push results) without registering a real
Challonge OAuth application or owning a real bracket. It must never be active
in production: the connect/link pages would grant a fake authenticated
connection. As with ``MOCK_DISCORD`` we refuse to start in that case.
"""

import os

from application.utils.environment import is_production


def is_mock_challonge() -> bool:
    """Return True when MOCK_CHALLONGE is enabled (and not in production)."""
    enabled = os.environ.get('MOCK_CHALLONGE', '').lower() in ('1', 'true', 'yes')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_CHALLONGE must not be enabled in production: it fakes the '
            'Challonge OAuth connection. Unset MOCK_CHALLONGE or change ENVIRONMENT.'
        )
    return enabled
