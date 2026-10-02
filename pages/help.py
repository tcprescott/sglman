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
from application.services import (
    AuthService,
    HelpService,
    TenantService,
    get_user_from_discord_id,
)
from middleware.auth import public_page
from theme.base import BaseLayout
from theme.error_page import render_not_found
from theme.help.article import render_article

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


async def _viewer():
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


async def _render_chrome(user) -> None:
    await BaseLayout(
        user=user, show_admin=await AuthService.can_view_admin(user),
    ).render()


async def _title(*parts: str) -> str:
    """A tab title that says which community's help this is."""
    community = await TenantService.current_community_name() or 'Wizzrobe'
    return ' — '.join((*parts, community))


def create() -> None:
    @public_page('/help')
    async def help_index() -> None:
        ui.page_title(await _title('Help'))
        await _render_chrome(await _viewer())

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
        user = await _viewer()
        article = await HelpService.get_article(slug, user)
        if article is None:
            await render_not_found(
                user=user, actions=[('All help', 'help_outline', '/help')],
            )
            return

        ui.page_title(await _title(article.title, 'Help'))
        await _render_chrome(user)
        render_article(
            article, await HelpService.list_articles(), base='/help', back_label='All help',
        )
