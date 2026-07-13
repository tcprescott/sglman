"""Racetime bot runtime — the connection layer for racetime.gg race rooms.

A peer of ``discordbot/``: an entry surface (presentation layer) that calls
services and never imports repositories. It stands up one long-lived connection
per active :class:`~models.RacetimeBot` category, tracks each connection's health
as first-class state, and routes inbound room events to the tenant-scoped
business layer. Gated by ``RACETIME_BOT_ENABLED`` and fully mockable via
``MOCK_RACETIME``.

Public surface (used by ``main.py``'s lifespan and ``/platform``):
    init_racetime_bot / close_racetime_bot / get_racetime_manager
"""

from racetimebot.manager import (
    RacetimeBotManager,
    close_racetime_bot,
    get_racetime_manager,
    init_racetime_bot,
)

__all__ = [
    'RacetimeBotManager',
    'close_racetime_bot',
    'get_racetime_manager',
    'init_racetime_bot',
]
