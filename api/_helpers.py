"""Shared load-or-404 helpers for the REST routers.

``load_user_or_404`` was byte-identical in three routers (``users``,
``async_qualifiers``, ``tournament_actions``). It lives here once instead.

Only genuinely *shared* lookups belong here: a router whose load-or-404 is
specific to its own resource keeps it local. The 404 itself still comes from
``require_found`` raising ``NotFoundError``, which ``ServiceErrorRoute`` maps —
this is a naming convenience, not a second error path.
"""

from application.errors import require_found
from application.services import UserService
from models import User


async def load_user_or_404(user_id: int) -> User:
    """The global ``User`` for ``user_id``, or a 404 via ``NotFoundError``."""
    return require_found(await UserService().get_user_by_id(user_id), "User")
