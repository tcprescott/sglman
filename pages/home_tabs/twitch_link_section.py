"""Self-contained 'Link Twitch' section for the player profile tab.

Lets a user verify-link their Twitch identity via a one-time OAuth login. The
section hides itself entirely when the Twitch integration isn't configured.
"""

from nicegui import ui

from application.services import TwitchService
from models import User


async def render_twitch_link_section(user: User) -> None:
    service = TwitchService()
    if not service.is_configured():
        return

    with ui.card().classes('card-full-width'):
        ui.label('Twitch').classes('section-title')
        ui.label(
            'Link your Twitch account so we can associate your verified Twitch identity '
            'with your profile.'
        ).classes('text-caption text-grey-7')

        @ui.refreshable
        def status() -> None:
            if user.twitch_user_id:
                with ui.row().classes('items-center'):
                    ui.icon('link', color='positive')
                    ui.label(f"Linked as {user.twitch_username or user.twitch_user_id}").classes('text-bold')
                ui.button('Unlink', icon='link_off', on_click=unlink).props('flat color=negative')
            else:
                ui.label('Not linked.').classes('text-muted')
                ui.button(
                    'Link Twitch account', icon='link',
                    on_click=lambda: ui.navigate.to('/twitch/link'),
                ).props('color=primary')

        async def unlink() -> None:
            try:
                await service.unlink_player(user, actor=user)
                ui.notify('Twitch account unlinked.', color='positive')
            except ValueError as e:
                ui.notify(str(e), color='warning')
            status.refresh()

        status()
