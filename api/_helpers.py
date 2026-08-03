"""Shared load-or-404 helpers for the REST routers.

``load_user_or_404`` was byte-identical in three routers (``users``,
``async_qualifiers``, ``tournament_actions``). It lives here once instead.

Only genuinely *shared* lookups belong here: a router whose load-or-404 is
specific to its own resource keeps it local. The 404 itself still comes from
``require_found`` raising ``NotFoundError``, which ``ServiceErrorRoute`` maps —
this is a naming convenience, not a second error path.

**Two loaders, and picking the wrong one is a cross-community leak.** ``User`` is
global while nearly everything a community owns is not, so a bare id lookup
reaches every account on the platform. Use
:func:`load_community_user_or_404` for anything that *reads or edits the person*
— their profile, their active flag — and :func:`load_user_or_404` only where
reaching a non-member is the point, which is the routes that grant authority
(they are how someone becomes a member in the first place).
"""

from application.errors import require_found
from application.services import TenantService, UserService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from models import User


async def load_user_or_404(user_id: int) -> User:
    """The global ``User`` for ``user_id``, or a 404 via ``NotFoundError``.

    Deliberately unscoped, for the routes that *confer* something: granting a
    role or naming a tournament admin is how a person joins a community, so the
    target is a non-member by definition and ``UserService.grant_role`` creates
    the membership as it goes. Nothing here discloses the person — the caller
    already had to know the id, and the response says what was granted.

    For anything that reads or edits the person themselves, use
    :func:`load_community_user_or_404`.
    """
    return require_found(await UserService().get_user_by_id(user_id), "User")


async def load_community_user_or_404(user_id: int, actor: User) -> User:
    """``user_id`` if they belong to the token's community, else a 404.

    ``User`` is global; belonging to a community is ``TenantMembership``, which
    is the same basis the access gate and the person pickers use — holding any
    role in a tenant implies membership in it.

    Without this the by-id routes walked the whole platform: staff of any
    community could read every account's username, ``discord_id``, display name
    and pronouns by counting upwards, and — through the admin route — clear
    ``is_active``, which is a *global* account disable. The sibling
    ``list_users`` was already narrowed for exactly this ("returning the
    platform's whole user table was a leak"); by-id reopened it behind a loop.

    404, not 403, so the response cannot be used to tell "no such id" from "not
    in your community" — the same hidden-not-forbidden posture the feature gate
    and the room tokens take.

    The actor always resolves themselves: a token whose owner has somehow fallen
    out of membership should still be able to read and edit its own profile
    rather than 404 on ``/users/<own id>``. A super-admin resolves anyone, as
    they do everywhere else.
    """
    user = require_found(await UserService().get_user_by_id(user_id), "User")
    if user.id == actor.id:
        return user
    if await AuthService.is_super_admin(actor):
        return user
    if not await TenantService.is_member(user.id, require_tenant_id()):
        require_found(None, "User")
    return user
