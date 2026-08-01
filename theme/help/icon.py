"""The tappable help icon that opens a snippet.

A hover tooltip is unreachable on a touch screen, and most of the people this
help is for are reading it on a phone in a loud room. So this is a real button
with a ``q-menu``: it opens on tap and on click alike, stays open until
dismissed, and its content is selectable.

The snippet it shows is a region of a help article, not a second copy of the
words — the popup and the article cannot drift apart, and "Read more" deep-links
to the heading the region sits under.
"""

from nicegui import ui

from application.services import HelpService
from theme.help.render import render_blocks

__all__ = ['help_icon']


async def help_icon(snippet_name: str, *, label: str = '', size: str = 'xs') -> None:
    """Render a help icon for ``snippet_name``, or nothing if it is unavailable.

    Pass ``label`` where a surface carries **two** of these: two bare
    ``help_outline`` icons side by side are indistinguishable, and the reader has
    to open both to find out which one answers their question.

    Renders nothing when the snippet does not exist or its article is gated off
    for this community — an icon that opens an empty popup is worse than no icon,
    and a missing snippet is an authoring slip that should not break a page.
    """
    snippet = await HelpService.get_snippet(snippet_name)
    if snippet is None:
        return

    href = f'/help/{snippet.article_slug}'
    if snippet.anchor:
        href = f'{href}#{snippet.anchor}'

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
                ui.link('Read more', href).classes('wiz-help-more')
