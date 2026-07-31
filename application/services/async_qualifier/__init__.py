"""Async-qualifier services — self-serve qualifying runs against a seed pool.

``AsyncQualifierService`` is the lifecycle surface; ``async_qualifier_draw``
hands a player a permalink from the pool, ``async_qualifier_scoring`` ranks the
submitted runs, ``async_qualifier_access`` decides who may see a run before the
window closes, and ``async_qualifier_config``/``_rules`` validate the
per-qualifier settings, and ``async_qualifier_worker`` forfeits runs a player
drew and abandoned. Gated by ``FeatureFlag.ASYNC_QUALIFIERS``.
"""

from application.services.async_qualifier import (
    async_qualifier_access,
    async_qualifier_notifications,
    async_qualifier_reads,
    async_qualifier_scoring,
    async_qualifier_worker,
)
from application.services.async_qualifier.async_qualifier_config import (
    AsyncQualifierConfig,
    validate_async_qualifier_config,
)
from application.services.async_qualifier.async_qualifier_draw import AsyncQualifierDraw
from application.services.async_qualifier.async_qualifier_live_race_service import (
    AsyncQualifierLiveRaceService,
)
from application.services.async_qualifier.async_qualifier_rules import (
    validate_counts,
    validate_window,
)
from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService

__all__ = [
    'AsyncQualifierConfig',
    'AsyncQualifierDraw',
    'AsyncQualifierLiveRaceService',
    'AsyncQualifierService',
    'async_qualifier_access',
    'async_qualifier_notifications',
    'async_qualifier_reads',
    'async_qualifier_scoring',
    'async_qualifier_worker',
    'validate_async_qualifier_config',
    'validate_counts',
    'validate_window',
]
