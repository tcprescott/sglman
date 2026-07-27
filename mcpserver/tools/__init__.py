"""Tool modules, grouped by domain.

Each module exposes ``register_tools(mcp)`` and registers only through
``mcpserver.registry.register``, so every tool carries an explicit gate.
"""

from mcp.server.fastmcp import FastMCP

from mcpserver.tools import orientation


def register_all(mcp: FastMCP) -> None:
    """Register every tool module onto the server."""
    orientation.register_tools(mcp)
