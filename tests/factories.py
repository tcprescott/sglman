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
"""

from datetime import datetime, timezone

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
