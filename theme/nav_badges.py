"""Counts on navigation items, such as the matches waiting on a player on My Schedule.

A tab declares its starting count with ``'badge': n`` in its BaseLayout tab
dict. BaseLayout draws one badge in the drawer and one on the bottom-nav tab and
registers both here, so a section that changes the count (booking a match takes
it off the list) can update them without a reference to the layout.

Keyed per client in a ``WeakKeyDictionary``, never shared module state: each
browser tab has its own badges, and they go when its client does.
"""

from weakref import WeakKeyDictionary

from nicegui import context, ui
from nicegui.client import Client

_badges: 'WeakKeyDictionary[Client, dict[str, list[ui.badge]]]' = WeakKeyDictionary()


def nav_count_badge(label: str, count: int) -> ui.badge:
    """Draw one count badge for the nav item ``label`` and register it."""
    badge = ui.badge(str(count), color=None).classes('wiz-nav-count')
    badge.set_visibility(count > 0)
    _badges.setdefault(context.client, {}).setdefault(label, []).append(badge)
    return badge


def drawer_tab_badge(tab: dict) -> None:
    """The drawer item's count, as a side section, when the tab declares one."""
    if 'badge' in tab:
        with ui.item_section().props('side'):
            nav_count_badge(tab['label'], tab['badge'])


def bottom_nav_tab(tab: dict) -> ui.tab:
    """One bottom-bar tab, with its count floating on the icon when it declares one."""
    with ui.tab(tab['label'], icon=tab.get('icon', 'circle')) as nav_tab:
        if 'badge' in tab:
            nav_count_badge(tab['label'], tab['badge']).props('floating')
    return nav_tab


def set_nav_count(label: str, count: int) -> None:
    """Update every badge on the nav item ``label`` for the current client."""
    try:
        client = context.client
    except RuntimeError:
        return
    for badge in _badges.get(client, {}).get(label, []):
        badge.set_text(str(count))
        badge.set_visibility(count > 0)
