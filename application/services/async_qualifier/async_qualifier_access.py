"""Shared access helpers for the async-qualifier services.

The self-paced service and the live-race service repeat the same two idioms
dozens of times: load-or-not-found a qualifier/pool/permalink/run, and gate the
caller on :meth:`AuthService.can_admin_qualifier`. Extracting them here keeps the
not-found messages and the admin gate identical across both services (a single
place the API's ``NotFoundError`` → 404 mapping and the authz message live).

The ``require_*`` helpers are repository-agnostic: they take any object exposing
``async get_by_id(id)`` (the qualifier services' repositories) and raise
:class:`~application.errors.NotFoundError` when the row is missing.
"""

from typing import Optional, Protocol

from application.errors import require_found
from application.services.auth_service import AuthService
from models import (
    AsyncQualifier,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierRun,
    User,
)


class _ByIdRepository(Protocol):
    async def get_by_id(self, entity_id: int): ...


async def require_qualifier(repository: _ByIdRepository, qualifier_id: int) -> AsyncQualifier:
    return require_found(await repository.get_by_id(qualifier_id), "Qualifier")


async def require_pool(repository: _ByIdRepository, pool_id: int) -> AsyncQualifierPool:
    return require_found(await repository.get_by_id(pool_id), "Pool")


async def require_permalink(
    repository: _ByIdRepository, permalink_id: int
) -> AsyncQualifierPermalink:
    return require_found(await repository.get_by_id(permalink_id), "Permalink")


async def require_run(repository: _ByIdRepository, run_id: int) -> AsyncQualifierRun:
    return require_found(await repository.get_by_id(run_id), "Run")


async def ensure_qualifier_admin(
    actor: Optional[User],
    qualifier: Optional[AsyncQualifier] = None,
    *,
    message: str = "Cannot administer qualifier",
) -> None:
    """Raise ``PermissionError`` unless ``actor`` may administer ``qualifier``.

    Wraps :meth:`AuthService.can_admin_qualifier` (STAFF/super-admin, the global
    ``QUALIFIER_ADMIN`` role, or a per-qualifier admin). ``message`` lets callers
    keep their context-specific wording (e.g. the reviewer-facing variant).
    """
    await AuthService.ensure(await AuthService.can_admin_qualifier(actor, qualifier), message)
