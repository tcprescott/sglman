"""A titled block on a page that stacks several of them.

My Schedule puts four independent things on one scroll — the matches you are
playing, the crew slots you signed up for, the hours you told staff you can play,
and the gear you are still holding. Rendered as bare headings joined by hairline
separators they read as one continuous document with no obvious boundary, while
each section's own ``page-container`` + ``header-row`` + ``separator-spacing``
stacked roughly four ems of dead space between a title and the content under it.
The result was ~3,500px of desktop scroll in which nothing looked like a thing.

A panel gives each block one visible edge, one compact header, and one padding
rule. ``aside`` is the header's right-hand slot for the section's own controls
(a scope switch, a column-preferences gear) so they stop floating above the
content they belong to.
"""

from typing import NamedTuple, Optional, Sequence, Union

from nicegui import ui

from models import User
from theme.help import help_icon

__all__ = ['SectionPanel', 'section_panel']

#: A help topic to hang off the header: a bare snippet name, or ``(name, label)``
#: where the section carries more than one and they need telling apart.
HelpTopic = Union[str, tuple[str, str]]


class SectionPanel(NamedTuple):
    """The three slots a caller fills in."""

    panel: ui.element
    #: Header's right-hand slot, for this section's own controls.
    aside: ui.row
    #: The content.
    body: ui.column


async def section_panel(
    title: str,
    *,
    icon: str,
    subtitle: str = '',
    help_topics: Sequence[HelpTopic] = (),
    user: Optional[User] = None,
) -> SectionPanel:
    """Render one section's chrome and hand back its slots.

    ``help_topics`` render as a wrapped group at the right of the header rather
    than glued to the title. Six of them beside "Your matches" was the single
    most cluttered thing on the tab: the title and the topics were one run of
    text, and each topic was small enough to be unreadable.

    Pass ``user`` where the caller already has one — ``help_icon`` only needs it
    for a role-gated handbook snippet, and without it every topic looks the
    viewer up again.
    """
    panel = ui.element('section').classes('wiz-panel')
    with panel:
        with ui.element('div').classes('wiz-panel__head'):
            with ui.row().classes('wiz-panel__head-row items-center no-wrap'):
                ui.icon(icon).classes('wiz-panel__icon')
                ui.label(title).classes('wiz-panel__title')
                aside = ui.row().classes('wiz-panel__aside items-center')
            if subtitle:
                ui.label(subtitle).classes('wiz-panel__sub')
            # After the subtitle, so the topics do not come between a title and
            # the line explaining it.
            if help_topics:
                with ui.row().classes('wiz-panel__help items-center'):
                    for topic in help_topics:
                        name, label = topic if isinstance(topic, tuple) else (topic, '')
                        await help_icon(name, label=label, size='sm', user=user)
        body = ui.column().classes('wiz-panel__body')
    return SectionPanel(panel=panel, aside=aside, body=body)
