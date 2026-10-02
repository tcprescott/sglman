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
from application.services import (
    AuthService,
    EventInfoService,
    TenantService,
    get_user_from_discord_id,
)
from application.utils.tenant_urls import login_path
from middleware.auth import public_page
from models import FeatureFlag
from theme.base import BaseLayout, current_local_url
from theme.error_page import render_not_found
from theme.help.article import render_article

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


async def _viewer():
    """The signed-in reader, or None — the articles are role-filtered."""
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


async def _render_chrome(user) -> None:
    await BaseLayout(
        user=user, show_admin=await AuthService.can_view_admin(user),
    ).render()


async def _title(*parts: str) -> str:
    """A tab title that says which community's handbook this is."""
    community = await TenantService.current_community_name() or 'Wizzrobe'
    return ' — '.join((*parts, community))


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
        ui.page_title(await _title('Event Information'))
        user = await _viewer()
        await _render_chrome(user)

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
        user = await _viewer()
        article = await EventInfoService.get_article(slug, user)
        if article is None:
            back = ('All event information', 'event_note', '/event-info')
            if user is None:
                # Not revealing which role-gated pages exist is deliberate, but
                # a signed-out reader holds no role by definition, so saying
                # some pages need one leaks nothing — and it is the proctor on
                # a borrowed laptop's only way forward.
                await render_not_found(
                    user=None,
                    message=(
                        "We couldn't find that page. Some pages here are only "
                        'for crew and staff, so if you have a role in this '
                        'community, sign in and try again.'
                    ),
                    actions=[('Sign in', 'login', login_path(current_local_url())), back],
                )
            else:
                await render_not_found(user=user, actions=[back])
            return

        ui.page_title(await _title(article.title, 'Event Information'))
        await _render_chrome(user)
        render_article(
            article, await EventInfoService.list_articles(user),
            base='/event-info', back_label='All event information',
        )
