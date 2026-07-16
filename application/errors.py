"""Shared service-layer error types.

These are raised by services and understood by the entry surfaces (web
presentation, REST API, Discord handlers). Keeping them in a leaf module
(no imports of services/repositories) lets every layer depend on them
without creating an import cycle.
"""

from typing import Optional, TypeVar

T = TypeVar('T')


class NotFoundError(ValueError):
    """Raised by services when a requested entity does not exist.

    Subclasses :class:`ValueError` so existing ``pytest.raises(ValueError)``
    assertions and UI ``except ValueError`` handlers keep working unchanged.
    The REST API maps it to ``404`` ahead of the generic ``ValueError`` → ``400``.
    """


def require_found(obj: Optional[T], label: str) -> T:
    """Return ``obj`` if present, otherwise raise :class:`NotFoundError`.

    Collapses the ubiquitous ``x = await repo.get(...); if x is None: raise``
    pattern into a single call. ``label`` names the entity for the message.
    """
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj
