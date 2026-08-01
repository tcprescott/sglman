"""The per-community event information section.

**Anonymous-readable.** Both routes are :func:`public_page`: most of what this
section answers — when doors open, what to bring, where to go — is wanted
*before* someone has signed in, and a spectator may never sign in at all.

Unlike ``/help``, the article set here *does* vary by reader: an article may name
roles, and the floor procedure the room staff work from is written for them. The
page stays public because that filter subtracts — a signed-out reader gets the
public articles, never an empty page or a redirect to ``/login``.

Where ``/help`` explains the app, this explains one community's event, so the
whole section is behind ``EVENT_INFO`` and 404s where that is not granted.

Presentation only — it reads through :class:`EventInfoService` and renders parsed
blocks with :func:`theme.help.render_blocks`, the same closed-vocabulary renderer
the help section uses. Nothing here touches the ORM.
"""

from nicegui import app, ui

from application.content import ContentArticle
from application.services import AuthService, EventInfoService, get_user_from_discord_id
from middleware.auth import public_page
from models import FeatureFlag
from theme.base import BaseLayout
from theme.help.render import render_blocks

__all__ = ['create']


def _article_card(article: ContentArticle) -> None:
    with ui.card().classes('wiz-help-card cursor-pointer') \
            .on('click', lambda slug=article.slug: ui.navigate.to(f'/event-info/{slug}')):
        with ui.row().classes('items-center no-wrap gap-3'):
            ui.icon(article.icon).props('size=sm').classes('text-primary')
            with ui.column().classes('gap-0 col min-w-0'):
                ui.label(article.title).classes('text-weight-bold')
                if article.summary:
                    ui.label(article.summary).classes('text-caption text-grey-7')


async def _render_chrome():
    """Draw the frame and hand back the viewer — the articles are role-filtered."""
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    await BaseLayout(
        user=user, show_admin=await AuthService.can_view_admin(user),
    ).render()
    return user


def _nothing_published() -> None:
    """The state a community sees between being granted the feature and writing.

    Reachable and deliberately plain: the flag being on says the community has
    the section, not that anyone has filled it in yet.
    """
    ui.label('Nothing has been published here yet.').classes('text-muted')
    ui.link('How the app works →', '/help').classes('q-mt-sm')


def create() -> None:
    @public_page('/event-info', feature=FeatureFlag.EVENT_INFO)
    async def event_info_index() -> None:
        ui.page_title('Event Information')
        user = await _render_chrome()

        articles = await EventInfoService.list_articles(user)

        with ui.column().classes('page-container-narrow w-full'):
            with ui.row().classes('header-row items-center'):
                ui.label('Event Information').classes('page-title')
            ui.label(
                'Everything about this event: what is on, attending on the day, '
                'and who to ask.'
            ).classes('text-muted')

            if not articles:
                _nothing_published()
                return

            with ui.column().classes('full-width gap-2 q-mt-md'):
                for article in articles:
                    _article_card(article)

            # The boundary between the two sections, stated where a reader who
            # came looking for the wrong one will see it.
            ui.separator().classes('separator-spacing')
            with ui.row().classes('items-center gap-1 no-wrap'):
                ui.label('Looking for how the app works?').classes('text-muted')
                ui.link('Help', '/help')

    @public_page('/event-info/{slug}', feature=FeatureFlag.EVENT_INFO)
    async def event_info_article(slug: str) -> None:
        user = await _render_chrome()

        article = await EventInfoService.get_article(slug, user)
        if article is None:
            ui.page_title('Event Information')
            with ui.column().classes('page-container-narrow w-full'):
                ui.label('That page does not exist.').classes('page-title')
                ui.link('Back to event information', '/event-info')
            return

        ui.page_title(f'Event Information — {article.title}')
        articles = await EventInfoService.list_articles(user)

        with ui.row().classes('wiz-help-layout no-wrap w-full items-start'):
            # Article list, then this article's own headings — ordered so the
            # narrow-screen stack puts the reader's contents last, right above
            # the body it indexes.
            with ui.column().classes('wiz-help-nav gap-1'):
                ui.link('← All event information', '/event-info').classes('text-caption')
                for other in articles:
                    link = ui.link(other.title, f'/event-info/{other.slug}') \
                        .classes('wiz-help-nav-item')
                    if other.slug == article.slug:
                        link.classes(add='wiz-help-nav-item--active')
                headings = article.headings
                if headings:
                    ui.separator().classes('q-my-sm')
                    ui.label('On this page').classes('text-caption text-grey-7')
                    for anchor, text in headings:
                        ui.link(text, f'/event-info/{article.slug}#{anchor}') \
                            .classes('wiz-help-nav-sub')

            with ui.column().classes('wiz-help-body col min-w-0'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.icon(article.icon).props('size=sm').classes('text-primary')
                    ui.label(article.title).classes('page-title')
                if article.summary:
                    ui.label(article.summary).classes('text-muted')
                ui.separator().classes('separator-spacing')
                # Block flow rather than the enclosing flex column, so the
                # blocks' own margins set the rhythm instead of a uniform gap.
                with ui.element('div').classes('wiz-help-prose'):
                    render_blocks(article.blocks)
