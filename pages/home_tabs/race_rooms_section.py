"""Your race room is open: the way into it, on My Schedule.

An online player's match happens in a racetime.gg room. The room-open DM carries
a button into it, but a player who missed or muted the DM looks for their match
here, so the room leads the page while it is open or running: an open room means
the match is close.
"""

from typing import Optional

from nicegui import ui

from application.services import FeatureFlagService, RaceRoomService
from application.utils.timezone import format_local_display
from models import FeatureFlag, User


async def render_race_rooms(viewer: Optional[User]) -> None:
    """The open race rooms on this player's matches, each with a Join button."""
    if viewer is None:
        return
    # The tab isn't flag-gated, and the service refuses without the feature.
    if not await FeatureFlagService().is_enabled(FeatureFlag.RACETIME_ROOMS):
        return
    rooms = await RaceRoomService().open_rooms_for_player(viewer)
    if not rooms:
        return
    with ui.card().classes('wiz-subcard'):
        ui.label(
            'Your race room is open' if len(rooms) == 1 else 'Your race rooms are open'
        ).classes('wiz-subcard__title')
        for room in rooms:
            match = room.match
            if match is None:
                continue
            opponents = [
                p.user.preferred_name for p in match.players if p.user_id != viewer.id
            ]
            with ui.row().classes('items-center justify-between full-width q-my-xs gap-2'):
                with ui.column().classes('col-12 col-sm min-w-0 gap-0'):
                    ui.label(match.tournament.name).classes('text-bold ellipsis')
                    if opponents:
                        ui.label(f"vs {', '.join(opponents)}").classes('ellipsis')
                    if match.scheduled_at is not None:
                        ui.label(format_local_display(match.scheduled_at)) \
                            .classes('text-caption text-grey-7 ellipsis')
                ui.button('Join the room', icon='open_in_new') \
                    .props(f'color=primary no-caps href="{room.url}" target=_blank') \
                    .tooltip(room.slug)
