"""Shared building blocks for admin CRUD tabs.

The newer admin tabs (`admin_presets`, `admin_racetime`, `admin_speedgaming`,
`admin_discord_events`, `admin_webhooks`, `admin_discord_roles`, …) repeat the
same eight blocks: a page-header scaffold, a ``_current()`` actor helper, a
fetch→rows→update refresh, a toolbar refresh button, the ``selected_tab`` refresh
wiring, a ``body-cell-actions`` slot, per-row handlers, and an inline add/edit
dialog. This module centralizes the reusable pieces so those tabs converge onto
one copy (audit §2C.1). Inline dialogs should use
:func:`theme.dialog._helpers.form_dialog` for the standard chrome.

Presentation-only: NiceGUI widgets, Vue slot strings, and a thin actor lookup.
No business logic or ORM writes.
"""

from contextlib import contextmanager
from typing import Awaitable, Callable, Iterable, Optional, Sequence

from nicegui import app, background_tasks, ui

from application.services import get_user_from_discord_id
from models import User

__all__ = [
    'current_actor',
    'admin_page_container',
    'refresh_icon_button',
    'wire_tab_refresh',
    'action_button',
    'actions_slot',
    'ServiceTableView',
]


async def current_actor() -> Optional[User]:
    """The logged-in ``User`` (or ``None``) — the ``_current()`` one-liner copied
    across 43 admin files, in one place."""
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


@contextmanager
def admin_page_container(title: str, *, narrow: bool = True):
    """Page-header scaffold: outer column + header row + title + separator.

    Yields the outer ``ui.column`` so the caller nests the rest of the tab
    (subtitles, tables, dialogs) inside it. ``narrow`` picks
    ``page-container-narrow`` vs ``page-container``.
    """
    container_class = 'page-container-narrow' if narrow else 'page-container'
    with ui.column().classes(container_class) as column:
        with ui.row().classes('header-row'):
            ui.label(title).classes('page-title')
        ui.separator().classes('separator-spacing')
        yield column


def refresh_icon_button(refresh: Callable[..., Awaitable[None]]):
    """The toolbar refresh icon-button that kicks ``refresh`` as a background task."""
    return ui.button(
        icon='refresh',
        on_click=lambda: background_tasks.create(refresh()),
    ).props('flat color=primary').tooltip('Refresh table')


def wire_tab_refresh(tab_name: str, refresh: Callable[..., Awaitable[None]]) -> None:
    """Refresh when the parent admin page emits ``selected_tab`` for ``tab_name``.

    ``tab_name`` must match the tab label registered in ``pages/admin.py``.
    """
    ui.on(
        'selected_tab',
        lambda e: background_tasks.create(refresh()) if e.args == tab_name else None,
    )


def action_button(icon: str, event: str, *, tooltip: str, color: str = 'primary',
                  vif: Optional[str] = None) -> str:
    """One row-action ``q-btn`` that emits ``event`` with the row. ``vif`` is an
    optional client-side condition (e.g. ``props.row.is_active``)."""
    cond = f' v-if="{vif}"' if vif else ''
    return (
        f'<q-btn{cond} flat round dense icon="{icon}" color="{color}" '
        f"@click=\"$parent.$emit('{event}', props.row)\">"
        f'<q-tooltip>{tooltip}</q-tooltip></q-btn>'
    )


def actions_slot(buttons: Iterable[str]) -> str:
    """Wrap :func:`action_button` strings in a ``body-cell-actions`` table slot."""
    return '<q-td :props="props">' + ''.join(b for b in buttons if b) + '</q-td>'


class ServiceTableView:
    """A generic admin table: build once, ``refresh()`` fetches through a service,
    maps each item to a row dict, and updates the table.

    Wires the toolbar (optional Add button + refresh icon), the actions slot, the
    per-row event handlers, and the ``selected_tab`` refresh — the boilerplate the
    admin tabs repeat. The page supplies the dialogs and mutation handlers.
    """

    def __init__(
        self,
        *,
        columns: Sequence[dict],
        fetch: Callable[[], Awaitable[Iterable]],
        to_row: Callable[[object], dict],
        row_key: str = 'id',
        table_classes: str = 'w-full',
        grid_breakpoint: Optional[str] = None,
        action_buttons: Optional[Sequence[str]] = None,
        handlers: Optional[dict] = None,
        add_label: Optional[str] = None,
        on_add: Optional[Callable] = None,
        refresh_tab: Optional[str] = None,
        extra_slots: Optional[dict] = None,
    ) -> None:
        self.columns = columns
        self.fetch = fetch
        self.to_row = to_row
        self.row_key = row_key
        self.table_classes = table_classes
        self.grid_breakpoint = grid_breakpoint
        self.action_buttons = action_buttons
        self.handlers = handlers or {}
        self.add_label = add_label
        self.on_add = on_add
        self.refresh_tab = refresh_tab
        self.extra_slots = extra_slots or {}
        self.table = None

    def build(self) -> 'ServiceTableView':
        """Render the toolbar + table into the current slot. Returns self."""
        with ui.row().classes('full-width'):
            if self.add_label and self.on_add is not None:
                ui.button(self.add_label, icon='add', on_click=self.on_add).props('color=primary')
            ui.space()
            refresh_icon_button(self.refresh)

        self.table = ui.table(
            columns=list(self.columns), rows=[], row_key=self.row_key,
        ).classes(self.table_classes)
        if self.grid_breakpoint:
            self.table.props(f':grid="Quasar.Screen.{self.grid_breakpoint}"')

        if self.action_buttons:
            self.table.add_slot('body-cell-actions', actions_slot(self.action_buttons))
        for slot_name, slot_template in self.extra_slots.items():
            self.table.add_slot(slot_name, slot_template)
        for event, handler in self.handlers.items():
            self.table.on(event, handler)

        if self.refresh_tab:
            wire_tab_refresh(self.refresh_tab, self.refresh)
        return self

    async def refresh(self, *_, **__) -> None:
        items = await self.fetch()
        self.table.rows = [self.to_row(item) for item in items]
        self.table.update()
