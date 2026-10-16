"""The article page shared by ``/help/{slug}`` and ``/event-info/{slug}``.

Two columns at desktop width: a sticky sidebar (back link, every article, this
article's own headings) and the body. Below 1024px they stack with the body
first, because the sidebar is ~550px of links and in source order it pushed the
title below the fold. That left the reader's *own* contents — "On this page" and
the way back — at the foot of a long article, so on a phone those two move to a
compact strip above the body, and the stacked sidebar keeps only the article
list as a "more" footer. ``static/css/styles.css`` owns which copy shows where.
"""

from typing import Callable, Mapping, Optional

from nicegui import ui

from application.content import ContentArticle
from theme.help.render import render_blocks
from theme.page_header import page_title

__all__ = ['render_article']


def _contents(article: ContentArticle, base: str) -> None:
    for anchor, text in article.headings:
        ui.link(text, f'{base}/{article.slug}#{anchor}').classes('wiz-help-nav-sub')


def render_article(
    article: ContentArticle,
    articles: list[ContentArticle],
    *,
    base: str,
    back_label: str,
    for_staff: Optional[Callable[[ContentArticle], bool]] = None,
    embeds: Optional[Mapping[str, Callable[[], None]]] = None,
    intro_extra: Optional[Callable[[], None]] = None,
) -> None:
    """Render ``article`` with its sidebar; ``articles`` is the reader's list.

    ``for_staff`` marks the articles that go under a "For staff" label. Help
    passes it, and ``HelpService.list_articles`` orders that group last; the
    event handbook passes nothing, because its role-gated pages are not staff's.
    """
    with ui.row().classes('wiz-help-layout no-wrap w-full items-start'):
        with ui.column().classes('wiz-help-nav gap-1'):
            ui.link(f'← {back_label}', base).classes('text-caption wiz-help-wide-only')
            staff_label_shown = False
            for other in articles:
                if for_staff is not None and for_staff(other) and not staff_label_shown:
                    staff_label_shown = True
                    ui.label('For staff').classes('text-caption text-grey-7 q-mt-sm')
                link = ui.link(other.title, f'{base}/{other.slug}') \
                    .classes('wiz-help-nav-item')
                if other.slug == article.slug:
                    link.classes(add='wiz-help-nav-item--active')
            if article.headings:
                with ui.column().classes('gap-1 wiz-help-wide-only'):
                    ui.separator().classes('q-my-sm')
                    ui.label('On this page').classes('text-caption text-grey-7')
                    _contents(article, base)

        with ui.column().classes('wiz-help-body col min-w-0'):
            with ui.column().classes('gap-1 wiz-help-narrow-only w-full'):
                ui.link(f'← {back_label}', base).classes('text-caption')
                if article.headings:
                    with ui.expansion('On this page').props('dense') \
                            .classes('wiz-help-toc w-full'):
                        with ui.column().classes('gap-1'):
                            _contents(article, base)
            with ui.row().classes('items-center gap-2 no-wrap'):
                ui.icon(article.icon).props('size=sm').classes('text-primary')
                page_title(article.title)
            if article.summary:
                ui.label(article.summary).classes('text-muted')
            if intro_extra is not None:
                intro_extra()
            ui.separator().classes('separator-spacing')
            # Block flow rather than the enclosing flex column, so the blocks'
            # own margins set the rhythm instead of a uniform flex gap.
            with ui.element('div').classes('wiz-help-prose'):
                render_blocks(article.blocks, embeds=embeds)
