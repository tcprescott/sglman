"""The one help button a heading or dialog title carries.

Every surface gets at most one, always the same round "?", always at the end of
its heading row (in a dialog, beside the close button). It used to be up to six
icons and labelled chips per section, in three different looks, scattered
beside individual controls; on a phone the chips wrapped to two rows above the
content they explained.

A hover tooltip is unreachable on a touch screen, and most of the people this
help is for are reading it on a phone in a loud room. So this is a real button
with a ``q-menu``: it opens on tap and on click alike, stays open until
dismissed, and its content is selectable. With one topic the menu shows that
snippet; with several it lists them by name and each opens in place.

The snippet it shows is a region of an article, not a second copy of the words —
the popup and the article cannot drift apart, and "Read more" deep-links to the
heading the region sits under.

**It resolves across both article sections.** Help owns the app mechanics; the
per-community event handbook owns the floor procedure that used to sit in the
player and proctor articles. An icon names a snippet, not a section, so moving a
region from one to the other keeps every icon working — the popup simply starts
linking to ``/event-info/…`` instead of ``/help/…``.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Union

from nicegui import app, ui

from application.content import article_sections
from application.help import HelpSnippet, all_articles, get_article, get_snippet
from application.services import (
    EventInfoService,
    FeatureFlagService,
    HelpService,
    get_user_from_discord_id,
)
from models import FeatureFlag, User
from theme.help.render import render_blocks

__all__ = ['HelpTopic', 'ResolvedHelp', 'help_button', 'help_icon', 'resolve_help']

#: A snippet name, or ``(name, label)`` where its heading reads badly as a menu item.
HelpTopic = Union[str, tuple[str, str]]


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


def _gated(article) -> bool:
    return article is not None and HelpService.for_staff(article)


def _depends_on_the_reader(snippet_name: str) -> bool:
    """Whether a help snippet reads differently for different viewers.

    True when its own article is staff- or role-gated, when it links into
    ``/event-info`` (handbook pages can be role-gated), or when it links into
    ``/help`` while some help article is gated. Content only, no query.
    """
    raw = get_snippet(snippet_name)
    if raw is None:
        return False
    if _gated(get_article(raw.article_slug)):
        return True
    sections = article_sections(raw.blocks)
    if '/event-info' in sections:
        return True
    return '/help' in sections and any(_gated(article) for article in all_articles())


@dataclass(frozen=True)
class ResolvedHelp:
    """A topic this viewer can read, with the name the menu shows for it."""

    label: str
    snippet: HelpSnippet


async def _resolve_one(snippet_name: str, user: Optional[User]) -> Optional[HelpSnippet]:
    viewer = user
    if viewer is None and _depends_on_the_reader(snippet_name):
        # Judged as signed out, a staff snippet would vanish for staff and links
        # to gated articles would lose their anchors. Only looked up when it
        # matters.
        viewer = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    snippet = await HelpService.get_snippet(snippet_name, viewer)
    if snippet is None:
        snippet = await _event_info_snippet(snippet_name, viewer, viewer is not None)
    return snippet


async def resolve_help(
    topics: Sequence[HelpTopic], *, user: Optional[User] = None,
) -> list[ResolvedHelp]:
    """The topics in ``topics`` this viewer can read, in order.

    For a sync header (``dialog_header``, ``form_dialog``) that takes the
    result as ``help=``. Drops a topic whose snippet does not exist, whose
    article is gated off for this community, or whose roles the reader lacks:
    a menu entry that opens nothing is worse than no entry, and a missing
    snippet is an authoring slip that should not break a page.

    Pass ``user`` from any surface that already has one. It only matters for a
    role-gated snippet, and without it each one looks the viewer up itself.
    """
    resolved: list[ResolvedHelp] = []
    for topic in topics:
        name, label = topic if isinstance(topic, tuple) else (topic, '')
        snippet = await _resolve_one(name, user)
        if snippet is not None:
            resolved.append(ResolvedHelp(label or snippet.heading or snippet.article_title, snippet))
    return resolved


def _snippet_body(snippet: HelpSnippet) -> None:
    # Block flow, not the enclosing flex column: a height-capped flex parent
    # shrinks its children, which crushed a snippet's table to half its rows
    # instead of letting the popup scroll.
    with ui.element('div').classes('wiz-help-prose'):
        # Demoted so a snippet that opens on its own heading does not render it
        # at article-title scale inside a small popup.
        render_blocks(snippet.blocks, heading_offset=2)
    ui.link('Read more', snippet.href).classes('wiz-help-more')


def help_button(topics: Sequence[ResolvedHelp]) -> None:
    """Render the "?" for already-resolved ``topics``, or nothing if there are none.

    Rendered inside a heading row it moves itself to the row's far end (CSS
    ``order``), so a caller can add actions after it without reordering.
    """
    if not topics:
        return
    with ui.button(icon='help_outline').props('flat round dense aria-label=Help') \
            .classes('wiz-help-icon'):
        with ui.menu().props('max-width=26rem').classes('wiz-help-menu'):
            with ui.column().classes('wiz-help-menu-body'):
                if len(topics) == 1:
                    ui.label(topics[0].label).classes('wiz-help-menu-title')
                    _snippet_body(topics[0].snippet)
                else:
                    ui.label('Help').classes('wiz-help-menu-title')
                    for topic in topics:
                        with ui.expansion(topic.label).props('dense').classes('wiz-help-topic'):
                            _snippet_body(topic.snippet)


async def help_icon(*topics: HelpTopic, user: Optional[User] = None) -> None:
    """Resolve ``topics`` and render one "?" for them: the async shorthand.

    One call per heading. Several topics go in the same call and become one menu;
    two buttons on one heading is the clutter this replaced.
    """
    help_button(await resolve_help(topics, user=user))
