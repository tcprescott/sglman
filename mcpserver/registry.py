"""The single registration path for MCP tools.

Every tool is registered through :func:`register`, never through
``@mcp.tool()`` directly. That is the point: a tool cannot ship without an
explicit gate, because there is no other way to get one onto the server.
``tests/mcp/test_mcp_catalogue.py`` asserts the listed tools and
:data:`TOOL_GATES` agree, so a tool added the wrong way fails the suite rather
than quietly serving unauthenticated data.

The wrapper is also where the tenant is bound and where service exceptions are
translated — both need to happen inside the tool call, and doing them here means
no individual tool can forget either.
"""

import functools
import inspect
from typing import Callable, Dict, Optional, Tuple

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from application.services.timezone_service import TimezoneService
from application.tenant_context import tenant_scope
from application.timezone_context import tz_scope
from models import FeatureFlag
from mcpserver.auth import Gate, authorize, current_actor, resolve_tenant
from mcpserver.errors import map_service_error

# name -> (gate, feature). Read by the catalogue test and by whoami.
TOOL_GATES: Dict[str, Tuple[Gate, Optional[FeatureFlag]]] = {}


def register(
    mcp: FastMCP,
    fn: Callable,
    *,
    gate: Gate,
    feature: Optional[FeatureFlag] = None,
    title: Optional[str] = None,
) -> None:
    """Register ``fn`` as a gated, read-only MCP tool.

    The wrapper resolves the actor, resolves and binds the community named by
    the call's ``tenant`` argument, authorizes inside that binding, and maps any
    service exception to a machine-readable tool error.

    Binding happens here — around the tool body, in one ``with`` — rather than
    in the ASGI layer, because an OAuth token is platform-wide and each call
    picks its own community. Using ``tenant_scope`` means set and reset are the
    same statement, so no tool can leak a community into the next call.
    """
    name = fn.__name__

    @functools.wraps(fn)
    async def wrapped(**kwargs):
        try:
            actor = current_actor()
            if gate is Gate.GLOBAL:
                await authorize(actor, gate, feature)
                return await fn(**kwargs)
            tenant = await resolve_tenant(kwargs.get('tenant'))
            with tenant_scope(tenant.id):
                await authorize(actor, gate, feature, slug=tenant.slug)
                # An MCP caller has no browser and is not "a viewer", so there is
                # no personal clock to resolve — but tools still take and derive
                # calendar dates (``get_schedule(date=…)``), and those must land
                # on the community's day. Bound here, alongside the tenant, so no
                # tool can be written that forgets it.
                with tz_scope(await TimezoneService.tenant_timezone_name(tenant.id)):
                    return await fn(**kwargs)
        except Exception as exc:
            raise map_service_error(exc) from exc

    # func_metadata builds the JSON schema from inspect.signature(func,
    # eval_str=True), which follows __wrapped__ back to fn — so the schema comes
    # from the real signature even though the callable takes **kwargs. Assert it
    # rather than trusting it: a functools change here would silently publish an
    # empty schema and every tool would start accepting anything.
    assert inspect.signature(wrapped).parameters == inspect.signature(fn).parameters

    TOOL_GATES[name] = (gate, feature)
    mcp.add_tool(
        wrapped,
        name=name,
        title=title,
        # Advertised on every tool: the surface is read-only, so a client need
        # never prompt for confirmation before a call.
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
