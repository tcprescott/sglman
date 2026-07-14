"""Racetime bot runtime — the connection layer for racetime.gg race rooms.

A peer of ``discordbot/``: an entry surface (presentation layer) that calls
services and never imports repositories. It stands up one long-lived connection
per active :class:`~models.RacetimeBot` category, tracks each connection's health
as first-class state, and routes inbound room events to the tenant-scoped
business layer. Gated by ``RACETIME_BOT_ENABLED`` and fully mockable via
``MOCK_RACETIME``.

The public functions are defined here as thin lazy wrappers so that importing a
leaf module (``racetimebot.transport`` — imported by the service layer for its
value types) does **not** pull in ``racetimebot.manager`` and, through it, the
whole service package. That indirection is what keeps the runtime and the
services free of an import cycle.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from racetimebot.manager import RacetimeBotManager

__all__ = [
    'close_racetime_bot',
    'get_racetime_manager',
    'init_racetime_bot',
]


def get_racetime_manager() -> 'RacetimeBotManager':
    from racetimebot.manager import get_racetime_manager as _impl

    return _impl()


async def init_racetime_bot() -> None:
    from racetimebot.manager import init_racetime_bot as _impl

    await _impl()


async def close_racetime_bot() -> None:
    from racetimebot.manager import close_racetime_bot as _impl

    await _impl()
