"""Actor resolution and per-call authorization for MCP tools.

Two halves, deliberately split:

* The **connection** identifies a user. ``mcpserver/asgi.py`` authenticates the
  bearer token once per HTTP request and stashes the result in ``_actor_var``.
* The **call** names a community. Every tenant-scoped tool takes a ``tenant``
  slug, and :func:`require_actor` resolves it, binds it, and runs the
  authorization gate inside that binding.

That split is forced by the credential: an OAuth token is platform-wide
(``tenant=NULL``), so there is no community to bind at connection time. It is
also what makes a single ``/mcp`` endpoint able to serve a user who staffs
several communities without reconnecting.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from application.errors import NotFoundError
from application.services.auth_service import AuthService
from application.services.feature_flag_service import FeatureFlagService
from application.services.tenant_service import TenantService
from models import ApiToken, FeatureFlag, Tenant, User


@dataclass(frozen=True)
class McpActor:
    """Who is behind the current MCP request."""

    user: User
    token: ApiToken


_actor_var: ContextVar[Optional[McpActor]] = ContextVar('mcp_actor', default=None)


def set_actor(actor: McpActor) -> Token:
    return _actor_var.set(actor)


def reset_actor(token: Token) -> None:
    _actor_var.reset(token)


def optional_actor() -> Optional[McpActor]:
    """The actor, or ``None`` when there is none.

    Only for the places where absence is a real state rather than a bug — the
    tool listing, which the SDK also builds outside a request while wiring the
    server up. Tools use :func:`current_actor`.
    """
    return _actor_var.get()


def current_actor() -> McpActor:
    """The authenticated actor for this request.

    Raises rather than returning ``None``: reaching a tool with no actor means
    the ASGI wrapper did not run, which is a wiring bug, not a permission
    outcome. Failing loudly here is the same instinct as ``require_tenant_id()``.
    """
    actor = _actor_var.get()
    if actor is None:
        raise RuntimeError(
            'No MCP actor in context — a tool ran outside McpEndpoint. '
            'Tools must be reached through the /mcp route, which authenticates first.'
        )
    return actor


class Gate(Enum):
    """The authorization each tool requires, mirroring its REST counterpart.

    ``GLOBAL`` is not a weaker ``ACTOR`` — it marks a tool that names no
    community at all (``whoami``, ``list_tenants``), so there is nothing to
    scope and no tenant-scoped role to check.
    """

    GLOBAL = 'global'
    ACTOR = 'actor'
    ADMIN = 'admin'
    STAFF = 'staff'


async def resolve_tenant(slug: Optional[str]) -> Optional[Tenant]:
    """Resolve a tool's ``tenant`` slug argument to a community.

    An unknown slug, an inactive one, and a missing argument all produce the
    same ``NotFoundError`` text on purpose: a caller must not be able to probe
    which communities exist by diffing error messages.
    """
    if not slug:
        raise NotFoundError(
            'This tool needs a community: pass tenant=<slug> from list_tenants.'
        )
    tenant = await TenantService.get_by_slug(slug)
    if tenant is None or not tenant.is_active:
        raise NotFoundError(f"No community '{slug}' is available.")
    return tenant


async def authorize(
    actor: McpActor,
    gate: Gate,
    feature: Optional[FeatureFlag],
    slug: str = '',
    *,
    write: bool = False,
) -> None:
    """Run the feature gate, the connection gate, then the role gate.

    Order matters and matches ``@protected_page``: a subsystem the community has
    not enabled is hidden from *everyone*, so the flag is checked before the
    role. Otherwise a 403 would tell an unauthorized caller that the feature
    exists here, and a staff member would get a different answer than a player
    for a feature that is simply off.
    """
    if feature is not None and not await FeatureFlagService().is_enabled(feature):
        raise NotFoundError('This feature is not enabled for this community.')

    # Membership floor, checked before any specific gate.
    #
    # A REST PAT is bound to one community, so `require_api_actor` — "any valid
    # token" — can never reach another one. An OAuth token is platform-wide and
    # names its community per call, so without this an ACTOR-gated tool would
    # let any authenticated user read any community's tournaments, matches and
    # schedule. That is a cross-community disclosure the REST surface does not
    # permit, so the floor restores parity: a token reaches a community only
    # where its user actually holds a role.
    #
    # NotFoundError, not PermissionError, and worded identically to an unknown
    # slug: "hidden, not forbidden" is the posture used throughout the app, and
    # a distinguishable refusal would turn error text into a directory of every
    # community on the platform.
    # GLOBAL tools are exempt: they name no community, and they are how a caller
    # discovers that they have access to none. Refusing them would leave a
    # role-less user unable to learn anything at all, including *that* fact.
    if gate is not Gate.GLOBAL and not await AuthService.is_super_admin(actor.user):
        if not await AuthService.get_roles(actor.user):
            raise NotFoundError(f"No community '{slug}' is available.")

    # What the *connection* may do, checked after the community is established
    # so a read-only token learns no more about a community than a writing one
    # would. Before the role gate because the two failures need different
    # answers from the user: reconnect with the box ticked, versus ask someone
    # for a role. A read-only grant is the default, so this is the common path.
    if write and actor.token.read_only:
        raise PermissionError(
            'This connection was approved for reading only. Reconnect from your '
            'MCP client and tick "Let it make changes" to use this tool.'
        )

    if gate is Gate.ADMIN:
        await AuthService.ensure(
            await AuthService.can_view_admin(actor.user), 'Admin access required'
        )
    elif gate is Gate.STAFF:
        await AuthService.ensure(
            await AuthService.is_staff(actor.user), 'Staff access required'
        )
    # Gate.ACTOR and Gate.GLOBAL need no further check — holding a live token is
    # the bar, exactly as `require_api_actor` is for the REST API.


# Read-only tokens are rejected per *tool*, never per connection. A read-only
# grant is the consent screen's default and by far the common case, so a blanket
# rejection here would refuse most legitimate callers; what a read-only token
# must not reach is the tools registered with ``write=True``, which is exactly
# what the check above covers.
