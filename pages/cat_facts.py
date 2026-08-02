"""The cat-facts page — where the easter egg finally lands.

Public, because there is nothing here but trivia. Deliberately absent from the
drawer nav: it's reached from the cat-fact dialog (the Konami code, or five taps
on the wordmark) and from the facts scattered through empty states, waiting
spinners and the 404 page. Finding it should still feel like finding something.
"""

from nicegui import app, ui

from application.services import AuthService, get_user_from_discord_id
from application.utils.easter_eggs import CAT_FACTS, random_cat_fact
from middleware.auth import public_page
from theme.base import BaseLayout

__all__ = ['create']


def create() -> None:
    @public_page('/cat-facts')
    async def cat_facts() -> None:
        ui.page_title('Cat facts')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        await BaseLayout(
            user=user, show_admin=await AuthService.can_view_admin(user),
        ).render()

        state = {'fact': random_cat_fact()}

        @ui.refreshable
        def featured() -> None:
            ui.label(state['fact']).classes('wiz-cat-featured-fact text-center')

        def shuffle() -> None:
            state['fact'] = random_cat_fact(exclude=state['fact'])
            featured.refresh()

        with ui.column().classes('page-container-narrow w-full'):
            with ui.row().classes('header-row items-center'):
                ui.label('Cat facts').classes('page-title')
            ui.label(
                f"You found them. All {len(CAT_FACTS)} of the facts this app "
                "hides in its empty tables, its spinners and its 404 page."
            ).classes('text-muted')

            with ui.card().classes('wiz-cat-featured w-full items-center'):
                ui.icon('pets').props('size=lg').classes('text-primary')
                featured()
                ui.button('Another one', icon='refresh', on_click=shuffle).props('flat')

            ui.label('Every fact').classes('section-title')
            with ui.column().classes('wiz-cat-list w-full'):
                for fact in CAT_FACTS:
                    with ui.row().classes('wiz-cat-list-row items-start no-wrap'):
                        ui.icon('pets').props('size=xs').classes('wiz-cat-list-icon')
                        ui.label(fact)
