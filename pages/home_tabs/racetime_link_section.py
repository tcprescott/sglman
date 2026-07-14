"""Self-contained 'Link racetime.gg' section for the player profile tab.

Lets a user verify-link their racetime.gg identity via a one-time OAuth login.
The section hides itself entirely when the racetime integration isn't configured.
"""

from nicegui import ui

from application.services import RacetimeService
from models import User


async def render_racetime_link_section(user: User) -> None:
    service = RacetimeService()
    if not service.is_configured():
        return

    with ui.card().classes('card-full-width'):
        ui.label('racetime.gg').classes('section-title')
        ui.label(
            'Link your racetime.gg account so we can attribute your race results and '
            'check auto-open eligibility.'
        ).classes('text-caption text-grey-7')

        @ui.refreshable
        def status() -> None:
            if user.racetime_user_id:
                with ui.row().classes('items-center'):
                    ui.icon('link', color='positive')
                    ui.label(f"Linked as {user.racetime_username or user.racetime_user_id}").classes('text-bold')
                ui.button('Unlink', icon='link_off', on_click=unlink).props('flat color=negative')
            else:
                ui.label('Not linked.').classes('text-muted')
                ui.button(
                    'Link racetime.gg account', icon='link',
                    on_click=lambda: ui.navigate.to('/racetime/link'),
                ).props('color=primary')

        async def unlink() -> None:
            try:
                await service.unlink_player(user, actor=user)
                ui.notify('racetime.gg account unlinked.', color='positive')
            except ValueError as e:
                ui.notify(str(e), color='warning')
            status.refresh()

        status()
