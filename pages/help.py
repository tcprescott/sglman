"""The in-app help section.

**Anonymous-readable.** Both routes are :func:`public_page`: help has to work for
someone who cannot get in, which is exactly when they most need it. There is no
user-specific content on either page, and the article set is filtered only by the
community's live feature flags.

Presentation only — it reads through :class:`HelpService` and renders parsed
blocks with :func:`theme.help.render_blocks`. Nothing here touches the ORM.
"""

from nicegui import app, ui

from application.help import HelpArticle
from application.services import AuthService, HelpService, get_user_from_discord_id
from middleware.auth import public_page
from theme.base import BaseLayout
from theme.help.render import render_blocks

__all__ = ['create']


def _article_card(article: HelpArticle) -> None:
    with ui.card().classes('wiz-help-card cursor-pointer') \
            .on('click', lambda slug=article.slug: ui.navigate.to(f'/help/{slug}')):
        with ui.row().classes('items-center no-wrap gap-3'):
            ui.icon(article.icon).props('size=sm').classes('text-primary')
            with ui.column().classes('gap-0 col min-w-0'):
                ui.label(article.title).classes('text-weight-bold')
                if article.summary:
                    ui.label(article.summary).classes('text-caption text-grey-7')


async def _render_chrome() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    await BaseLayout(
        user=user, show_admin=await AuthService.can_view_admin(user),
    ).render()


def create() -> None:
    @public_page('/help')
    async def help_index() -> None:
        ui.page_title('Help')
        await _render_chrome()

        articles = await HelpService.list_articles()
        state = {'query': ''}

        with ui.column().classes('page-container-narrow w-full'):
            with ui.row().classes('header-row items-center'):
                ui.label('Help').classes('page-title')
            ui.label(
                'How the app works for players, crew and volunteers. '
                'Search, or pick a topic.'
            ).classes('text-muted')

            search = ui.input(placeholder='Search help') \
                .props('outlined dense clearable autofocus') \
                .classes('full-width q-mt-md')
            with search.add_slot('prepend'):
                ui.icon('search')

            @ui.refreshable
            async def results() -> None:
                matches = await HelpService.search(state['query'])
                if not matches:
                    ui.label(
                        f'Nothing matches "{state["query"]}". Try fewer words.'
                    ).classes('text-muted q-mt-md')
                    return
                for article in matches:
                    _article_card(article)

            async def on_search(event) -> None:
                # `clearable` sets the value to None, not ''.
                state['query'] = (event.value or '').strip()
                await results.refresh()

            search.on_value_change(on_search)

            with ui.column().classes('full-width gap-2 q-mt-md'):
                await results()

            if not articles:
                ui.label('No help articles are available.').classes('text-muted')

    @public_page('/help/{slug}')
    async def help_article(slug: str) -> None:
        await _render_chrome()

        article = await HelpService.get_article(slug)
        if article is None:
            ui.page_title('Help')
            with ui.column().classes('page-container-narrow w-full'):
                ui.label('That help article does not exist.').classes('page-title')
                ui.link('Back to help', '/help')
            return

        ui.page_title(f'Help — {article.title}')
        articles = await HelpService.list_articles()

        with ui.row().classes('wiz-help-layout no-wrap w-full items-start'):
            # Article list, then the current article's own headings. Ordered that
            # way so the narrow-screen stack puts the reader's own contents last,
            # right above the body it indexes.
            with ui.column().classes('wiz-help-nav gap-1'):
                ui.link('← All help', '/help').classes('text-caption')
                for other in articles:
                    link = ui.link(other.title, f'/help/{other.slug}') \
                        .classes('wiz-help-nav-item')
                    if other.slug == article.slug:
                        link.classes(add='wiz-help-nav-item--active')
                headings = article.headings
                if headings:
                    ui.separator().classes('q-my-sm')
                    ui.label('On this page').classes('text-caption text-grey-7')
                    for anchor, text in headings:
                        ui.link(text, f'/help/{article.slug}#{anchor}') \
                            .classes('wiz-help-nav-sub')

            with ui.column().classes('wiz-help-body col min-w-0'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.icon(article.icon).props('size=sm').classes('text-primary')
                    ui.label(article.title).classes('page-title')
                if article.summary:
                    ui.label(article.summary).classes('text-muted')
                ui.separator().classes('separator-spacing')
                render_blocks(article.blocks)
