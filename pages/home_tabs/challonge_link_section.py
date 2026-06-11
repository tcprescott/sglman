"""Self-contained 'Link Challonge' section for the player profile tab.

Lets a player verify-link their Challonge identity (one-time OAuth, scope
``me``) so they can be matched to bracket participants for scheduling. The
section hides itself entirely when the Challonge integration isn't configured.
"""

from nicegui import ui

from application.services import ChallongeService
from models import User


async def render_challonge_link_section(user: User) -> None:
    service = ChallongeService()
    if not service.is_configured():
        return

    with ui.card().classes('card-full-width'):
        ui.label('Challonge').classes('section-title')
        ui.label(
            'Link your Challonge account so we can find your bracket matches and let you '
            'schedule them here.'
        ).classes('text-caption text-grey-7')

        @ui.refreshable
        def status() -> None:
            if user.challonge_user_id:
                with ui.row().classes('items-center'):
                    ui.icon('link', color='positive')
                    ui.label(f"Linked as {user.challonge_username or user.challonge_user_id}").classes('text-bold')
                ui.button('Unlink', icon='link_off', on_click=unlink).props('flat color=negative')
            else:
                ui.label('Not linked.').classes('text-muted')
                ui.button(
                    'Link Challonge account', icon='link',
                    on_click=lambda: ui.navigate.to('/challonge/link'),
                ).props('color=primary')

        async def unlink() -> None:
            try:
                await service.unlink_player(user, actor=user)
                ui.notify('Challonge account unlinked.', color='positive')
            except ValueError as e:
                ui.notify(str(e), color='warning')
            status.refresh()

        status()
