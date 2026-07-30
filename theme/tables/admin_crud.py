"""Shared building blocks for admin CRUD tabs.

Presentation-only: NiceGUI widgets and a thin actor lookup. No business logic or
ORM writes. Inline dialogs use :func:`theme.dialog._helpers.form_dialog` for the
standard chrome.
"""

from typing import Awaitable, Callable, Optional

from nicegui import app, background_tasks, ui

from application.services import get_user_from_discord_id
from application.tenant_context import get_current_tenant_id, tenant_scope
from application.timezone_context import current_timezone_name, tz_scope
from models import User


def capture_render_context() -> tuple[Optional[int], str]:
    """Snapshot the ambient tenant and display zone during a page build.

    Call at build time, use with :func:`scoped_background`. A detached task has
    neither the contextvars nor the client stash — NiceGUI keys its slot stack by
    asyncio task id, so ``app.storage.client`` raises inside one — and both
    values must therefore be carried in by hand.
    """
    return get_current_tenant_id(), current_timezone_name()


def scoped_background(context: tuple[Optional[int], str], coro) -> None:
    """Run ``coro`` as a background task with a captured context rebound.

    The tenant alone is not enough: without the zone the task repaints the same
    rows on the fallback clock, so a table silently changes timezone the moment
    you paginate or switch tabs.
    """
    tenant_id, tz = context

    async def _run():
        with tenant_scope(tenant_id), tz_scope(tz):
            await coro

    background_tasks.create(_run())

__all__ = [
    'current_actor',
    'wire_tab_refresh',
]


async def current_actor() -> Optional[User]:
    """The logged-in ``User`` (or ``None``)."""
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


def wire_tab_refresh(tab_name: str, refresh: Callable[..., Awaitable[None]]) -> None:
    """Refresh when the parent admin page emits ``selected_tab`` for ``tab_name``.

    ``tab_name`` must match the tab label registered in ``pages/admin.py``.

    The render context is captured **here** (this runs during the page build,
    where the request context is live) and rebound around the refresh:
    ``selected_tab`` is a client event, so its handler spawns a detached
    background task that has lost the tenant contextvar *and* the client stash —
    a scoped read inside ``refresh`` would otherwise raise ``require_tenant_id()``
    (swallowed) and never repaint, and every time it renders would silently fall
    back to the default zone.
    """
    context = capture_render_context()

    def _fire() -> None:
        scoped_background(context, refresh())

    ui.on('selected_tab', lambda e: _fire() if e.args == tab_name else None)
