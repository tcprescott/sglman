"""Small helpers shared by the dev-seed modules.

``backfill`` exists because ``get_or_create`` defaults only apply on the
*create*: a field added to a fixture spec today stays NULL forever on every dev
database that already holds the row, so the fixture silently means something
different depending on when the database was made. It writes only the attributes
that are still unset, which converges an older fixture without overwriting
anything a developer changed by hand.
"""

from typing import Any

from tortoise.models import Model


async def backfill(instance: Model, **values: Any) -> bool:
    """Set each attribute that is currently ``None``; save once if any changed.

    Returns whether anything was written, so a caller can fold the save into its
    own dirty tracking. Deliberately ignores falsey-but-set values (``False``,
    ``0``, ``''``) — only ``None`` counts as "never filled in".
    """
    dirty = [
        key for key, value in values.items()
        if value is not None and getattr(instance, key) is None
    ]
    for key in dirty:
        setattr(instance, key, values[key])
    if dirty:
        await instance.save()
    return bool(dirty)
