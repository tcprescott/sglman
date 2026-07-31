"""Canonical test factories/helpers shared across the suite.

Two helpers were copy-pasted (with drifting signatures) across dozens of test
modules; they live here now so a single definition is imported everywhere.

- ``utc(y, mo, d, h=0, mi=0)`` builds a UTC-aware ``datetime``. This is the
  majority signature; a couple of modules previously used incompatible
  positional conventions and have been converted to this one.
- ``make_user(...)`` creates a real ``User`` row (requires the ``db`` fixture).
  Many modules keep their own bespoke ``make_user``/``_user`` — some build
  ``SimpleNamespace``/``MagicMock`` stand-ins (no DB), some set extra fields
  like ``display_name`` or add roles. Those are intentionally left in place;
  this factory covers the plain "create a user row" case.
- ``make_audit_double()`` stands in for ``AuditService`` on a hand-built
  service under test, without silencing the event bus.
"""

from datetime import datetime, timezone
from functools import partial
from unittest.mock import AsyncMock, MagicMock

from models import User

UTC = timezone.utc


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """A timezone-aware UTC ``datetime`` for the given calendar fields."""
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


async def make_user(discord_id: int = 1, username: str | None = None, **kwargs) -> User:
    """Create and return a real ``User`` (needs the ``db`` fixture).

    ``username`` defaults to ``f'user{discord_id}'``. Extra model fields
    (``display_name``, ``is_active`` …) pass through via ``kwargs``.
    """
    if username is None:
        username = f'user{discord_id}'
    return await User.create(discord_id=discord_id, username=username, **kwargs)


def make_audit_double() -> MagicMock:
    """An ``AuditService`` stand-in that still publishes on the real event bus.

    A blanket ``MagicMock()`` swallows ``write_and_publish`` whole, so a service
    converted from the hand-rolled ``write_log`` + ``event_bus.publish`` pair
    would stop emitting events *under test only* — the failure mode that kept
    the conversion backlogged. Here ``write_and_publish`` runs its real body
    bound to this double: it calls the mocked ``write_log`` (so the existing
    call-args assertions keep working, and nothing touches the database) and
    then publishes for real.
    """
    from application.services.audit_service import AuditService

    double = MagicMock()
    double.write_log = AsyncMock()
    double.write_and_publish = partial(AuditService.write_and_publish, double)
    return double
