"""Helper for detecting whether the mock Discord layer is enabled."""

import os


def is_mock_discord() -> bool:
    """Return True when MOCK_DISCORD env var is set to a truthy value."""
    return os.environ.get('MOCK_DISCORD', '').lower() in ('1', 'true', 'yes')
