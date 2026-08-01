"""The tappable icon that opens a help or event-information snippet.

A hover tooltip is unreachable on a touch screen, and most of the people this
help is for are reading it on a phone in a loud room. So this is a real button
with a ``q-menu``: it opens on tap and on click alike, stays open until
dismissed, and its content is selectable.

The snippet it shows is a region of an article, not a second copy of the words —
the popup and the article cannot drift apart, and "Read more" deep-links to the
heading the region sits under.

**It resolves across both article sections.** Help owns the app mechanics; the
per-community event handbook owns the floor procedure that used to sit in the
player and proctor articles. An icon names a snippet, not a section, so moving a
region from one to the other keeps every icon working — the popup simply starts
linking to ``/event-info/…`` instead of ``/help/…``.
"""

from typing import Optional

from nicegui import app, ui

from application.services import (
    EventInfoService,
    FeatureFlagService,
    HelpService,
    get_user_from_discord_id,
)
from models import FeatureFlag, User
from theme.help.render import render_blocks

__all__ = ['help_icon']


async def _event_info_snippet(snippet_name: str, user: Optional[User], user_given: bool):
    """Look ``snippet_name`` up in this community's handbook, or ``None``.

    Resolves the flag here rather than letting the service raise: this helper is
    called from surfaces that are *not* themselves gated on ``EVENT_INFO``, and a
    community without the feature must get a missing snippet, not an exception
    that takes the page down.
    """
    if FeatureFlag.EVENT_INFO not in await FeatureFlagService().enabled_flags():
        return None
    if not user_given:
        # Only for a caller that had no user to hand: role-gated snippets are the
        # minority, and this costs a lookup the flag check has already earned.
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    return await EventInfoService.get_snippet(snippet_name, user)


async def help_icon(
    snippet_name: str,
    *,
    label: str = '',
    size: str = 'xs',
    user: Optional[User] = None,
) -> None:
    """Render a help icon for ``snippet_name``, or nothing if it is unavailable.

    Pass ``label`` where a surface carries **two** of these: two bare
    ``help_outline`` icons side by side are indistinguishable, and the reader has
    to open both to find out which one answers their question.

    Pass ``user`` from any surface that already has one. It only matters for a
    role-gated event-information snippet, and without it this has to resolve the
    viewer itself — which is a query a page that already knows who it is drawing
    for should not pay.

    Renders nothing when the snippet does not exist, its article is gated off for
    this community, or the reader holds none of its roles — an icon that opens an
    empty popup is worse than no icon, and a missing snippet is an authoring slip
    that should not break a page.
    """
    snippet = await HelpService.get_snippet(snippet_name)
    if snippet is None:
        snippet = await _event_info_snippet(snippet_name, user, user is not None)
    if snippet is None:
        return

    button = (
        ui.button(label, icon='help_outline').props(f'flat dense no-caps size={size}')
        if label else
        ui.button(icon='help_outline').props(f'flat round dense size={size}')
    )
    with button.classes('wiz-help-icon'):
        with ui.menu().props('max-width=26rem').classes('wiz-help-menu'):
            with ui.column().classes('wiz-help-menu-body'):
                # Block flow, not the enclosing flex column: a height-capped flex
                # parent shrinks its children, which crushed a snippet's table to
                # half its rows instead of letting the popup scroll.
                with ui.element('div').classes('wiz-help-prose'):
                    # Demoted so a snippet that opens on its own heading does not
                    # render it at article-title scale inside a small popup.
                    render_blocks(snippet.blocks, heading_offset=2)
                ui.link('Read more', snippet.href).classes('wiz-help-more')
