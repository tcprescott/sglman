"""Tool modules, grouped by domain.

Each module exposes ``register_tools(mcp)`` and registers only through
``mcpserver.registry.register``, so every tool carries an explicit gate.
"""

from mcp.server.fastmcp import FastMCP

from mcpserver.tools import (
    competition,
    matches,
    observability,
    orientation,
    people,
    tournaments,
    volunteers,
)


def register_all(mcp: FastMCP) -> None:
    """Register every tool module onto the server."""
    orientation.register_tools(mcp)
    tournaments.register_tools(mcp)
    matches.register_tools(mcp)
    people.register_tools(mcp)
    volunteers.register_tools(mcp)
    observability.register_tools(mcp)
    competition.register_tools(mcp)
