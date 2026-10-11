"""Tool modules, grouped by domain.

Each module exposes ``register_tools(mcp)`` and registers only through
``mcpserver.registry.register``, so every tool carries an explicit gate.

``match_writes`` and ``event_writes`` are the modules that change data, kept
apart from the read modules rather than filed by domain: whether a tool writes is the property that
decides its annotation, its gate and whether a read-only connection is even
shown it, so it is the property the layout should make obvious.
"""

from mcp.server.mcpserver import MCPServer

from mcpserver.tools import (
    analytics,
    check_in,
    competition,
    equipment,
    event_writes,
    match_writes,
    matches,
    observability,
    online_play,
    orientation,
    people,
    tournaments,
    volunteers,
)


def register_all(mcp: MCPServer) -> None:
    """Register every tool module onto the server."""
    orientation.register_tools(mcp)
    tournaments.register_tools(mcp)
    matches.register_tools(mcp)
    people.register_tools(mcp)
    volunteers.register_tools(mcp)
    equipment.register_tools(mcp)
    observability.register_tools(mcp)
    analytics.register_tools(mcp)
    competition.register_tools(mcp)
    online_play.register_tools(mcp)
    check_in.register_tools(mcp)
    match_writes.register_tools(mcp)
    event_writes.register_tools(mcp)
