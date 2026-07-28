"""Shared building blocks for admin CRUD tabs.

Presentation-only: NiceGUI widgets and a thin actor lookup. No business logic or
ORM writes. Inline dialogs use :func:`theme.dialog._helpers.form_dialog` for the
standard chrome.
"""

from typing import Awaitable, Callable, Optional

from nicegui import app, background_tasks, ui

from application.services import get_user_from_discord_id
from application.tenant_context import get_current_tenant_id, tenant_scope
from models import User

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

    The tenant is captured **here** (this runs during the page build, where the
    request context is live) and rebound around the refresh: ``selected_tab`` is
    a client event, so its handler spawns a detached background task that has lost
    the tenant contextvar and the client stash — a scoped read inside ``refresh``
    would otherwise raise ``require_tenant_id()`` (swallowed) and never repaint.
    """
    tenant_id = get_current_tenant_id()

    def _fire() -> None:
        async def _run():
            with tenant_scope(tenant_id):
                await refresh()
        background_tasks.create(_run())

    ui.on('selected_tab', lambda e: _fire() if e.args == tab_name else None)
