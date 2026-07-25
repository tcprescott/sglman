"""Helper for detecting whether the mock seed-generation layer is enabled.

The mock layer lets local development and the browser-validation loop exercise
the full seed-rolling flow (a qualifier pool's ``Roll seeds`` action, and any
other :meth:`SeedGenerationService.generate_seed` caller) without reaching a
live randomizer service — most of which need credentials, are slow, or are
simply unreachable from a dev sandbox. It returns a believable permalink URL
instead of calling the backend. It must never be active in production, where a
real seed is required for an actual race; as with ``MOCK_DISCORD`` and
``MOCK_CHALLONGE`` we refuse to start in that case.
"""

from application.utils.environment import env_flag, is_production


def is_mock_seedgen() -> bool:
    """Return True when MOCK_SEEDGEN is enabled (and not in production)."""
    enabled = env_flag('MOCK_SEEDGEN')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_SEEDGEN must not be enabled in production: it returns fake seed '
            'permalinks instead of rolling a real seed. Unset MOCK_SEEDGEN or '
            'change ENVIRONMENT.'
        )
    return enabled
