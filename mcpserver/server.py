"""FastMCP server construction.

Kept in a function rather than at module scope for a non-obvious reason:
``FastMCP.__init__`` calls ``configure_logging()``, which calls
``logging.basicConfig``. Constructing the server at import time would win the
race against ``main.py``'s own ``basicConfig`` and strip timestamps, levels and
logger names from every log line in the process. Building it from ``mount()``,
which runs after logging is configured, keeps our format.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcpserver.tools import register_all

INSTRUCTIONS = """\
Read-only access to Wizzrobe, a tournament management platform. You can look up \
tournaments, matches, schedules, brackets and qualifiers, people, crew and \
volunteer assignments, equipment, seed presets, racetime and SpeedGaming \
integrations, audit history, engagement telemetry, and operational reports. \
Nothing here modifies data.

Start with `whoami`. It reports which communities you belong to, what role you \
hold in each, and which optional features each has enabled — so you can avoid \
calling tools that would be refused.

Wizzrobe hosts many independent communities. Every tool except `whoami` and \
`list_tenants` takes a required `tenant` argument: the community's slug, as \
returned by `list_tenants`. A tool that reports `not_found` for a feature means \
that community has not enabled it, not that you asked incorrectly.

All times are returned in UTC. Each community chooses the timezone its \
members read them in, so convert before quoting a time to a person.\
"""


def build_server() -> FastMCP:
    """Construct the MCP server with every tool registered."""
    mcp = FastMCP(
        name='Wizzrobe',
        instructions=INSTRUCTIONS,
        # CORRECTNESS, not scaling. In stateful mode the MCP server task is
        # spawned once per session and snapshots the context of whichever request
        # created it — so a second request on that session would run tools under
        # the first request's identity. Stateless mode spawns a task per HTTP
        # request, which inherits that request's actor. Do not change this.
        stateless_http=True,
        # Plain JSON responses instead of SSE. The app's BaseHTTPMiddleware stack
        # (security headers, fun facts) wraps /mcp, and BaseHTTPMiddleware around
        # a long-lived SSE stream is a known source of hangs on client disconnect.
        json_response=True,
        # We serve the path ourselves from mcpserver/__init__.py; leaving this at
        # its '/mcp' default would put the real endpoint at '/mcp/mcp'.
        streamable_http_path='/',
        # Off because TLS and Host both terminate at the reverse proxy. The
        # default would auto-enable it (host defaults to 127.0.0.1) and then
        # reject every production request with 421 Invalid Host header.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
    register_all(mcp)
    # Called for its side effect only: it lazily constructs the session manager
    # that mcpserver/asgi.py drives. The Starlette app it returns is discarded —
    # we need the bare path, and a Mount would answer /mcp with a 307 to /mcp/.
    mcp.streamable_http_app()
    return mcp
