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


class FeatureDisabledError(NotFoundError):
    """Raised when a service is asked to act on a feature the tenant lacks.

    Subclasses :class:`NotFoundError` (and so ``ValueError``) deliberately: a
    feature a community has not enabled is *hidden*, not forbidden, which is the
    posture every other gate already takes — ``@protected_page(feature=…)`` and
    ``require_feature`` both 404 rather than 403, so role has no bearing and an
    unreleased feature never leaks its existence. Inheriting from
    ``NotFoundError`` means the REST layer maps it to 404 with no new plumbing and
    UI ``except ValueError`` handlers keep showing it as a notification.
    """


class MissingCredentialError(ValueError):
    """Raised when a roll needs a randomizer credential this tenant has not set.

    A plain :class:`ValueError` (400 over REST, a UI notification on the web), and
    a distinct type so ``MatchScheduleService.generate_seed`` can surface *this*
    message while still hiding raw randomizer/HTTP failures behind its generic
    "check the server logs". The distinction is safe to show: it names a
    credential the reader is authorized to configure, never an upstream response.
    """


def require_found(obj: Optional[T], label: str) -> T:
    """Return ``obj`` if present, otherwise raise :class:`NotFoundError`.

    Collapses the ubiquitous ``x = await repo.get(...); if x is None: raise``
    pattern into a single call. ``label`` names the entity for the message.
    """
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj
