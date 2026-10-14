"""Counts on navigation items, such as the matches waiting on a player on My Schedule.

A tab declares its starting count with ``'badge': n`` in its BaseLayout tab
dict. The side menu draws a badge on each copy of that item (its section row,
its pin, its bottom-bar tab) and registers every one here, so a section that
changes the count (booking a match takes it off the list) can update them all
without a reference to the layout.

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


def set_nav_count(label: str, count: int) -> None:
    """Update every badge on the nav item ``label`` for the current client."""
    try:
        client = context.client
    except RuntimeError:
        return
    for badge in _badges.get(client, {}).get(label, []):
        if badge.is_deleted:
            continue
        badge.set_text(str(count))
        badge.set_visibility(count > 0)
