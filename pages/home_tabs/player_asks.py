"""Two things on My Schedule that are waiting on the player but are not a booking.

Each is a card above the board rather than a column on it, for the same reason
the "Waiting on you to pick a time" card is: it is the reader's next action, and
a cell on a ten-column board is where actions go to be scrolled past.

* **Your opponent asked to move a match.** The opponent DM asks them to press
  Agree. The web had no Agree at all, so the push notification copy of that DM,
  which has no Discord button under it, asked for something nobody could do.
* **Your race room is open.** An online player's match happens in a racetime
  room, and nothing on the site named it: the room was reachable only from
  racetime.gg itself.
"""

from typing import Awaitable, Callable, Optional

from nicegui import ui

from application.services import (
    FeatureFlagService,
    MatchRescheduleService,
    RacetimeRoomService,
)
from application.services.match_reschedule_service import (
    AGREE_DECIDED,
    AGREE_DONE,
    AGREE_OPEN,
)
from application.utils.timezone import format_local_display
from models import FeatureFlag, User
from theme.dialog.reschedule_agree_dialog import (
    AGREE_NOTE,
    RescheduleAgreeDialog,
    agree,
    render_agreement_summary,
)

# What a stale "Open the request" link says instead of opening nothing.
_STALE_AGREE = {
    AGREE_DONE: ("You've already agreed to that request. Staff still decide.", 'info'),
    AGREE_DECIDED: (
        "That request is closed: staff answered it or it was withdrawn.", 'warning',
    ),
}
_NOT_YOURS = ("That request isn't one waiting on you.", 'warning')


def _notify(notice: tuple[str, str]) -> None:
    message, color = notice
    ui.notify(message, color=color)


async def render_opponent_requests(
    viewer: Optional[User],
    *,
    agree_request_id: Optional[int] = None,
    on_agreed: Optional[Callable[[], Awaitable[None]]] = None,
) -> None:
    """The requests this player's opponent made, each with an Agree button.

    ``agree_request_id`` arrives from the opponent DM's link button
    (``?agree=<id>``) and opens that request's dialog, or says why it can't.
    """
    if viewer is None:
        if agree_request_id is not None:
            _notify(_NOT_YOURS)
        return
    service = MatchRescheduleService()

    @ui.refreshable
    async def section() -> None:
        rows = await service.list_awaiting_agreement(viewer)
        if not rows:
            return
        with ui.card().classes('wiz-subcard'):
            ui.label('Your opponent asked to reschedule').classes('wiz-subcard__title')
            ui.label(AGREE_NOTE).classes('text-caption text-grey-7')
            for row in rows:
                with ui.column().classes('full-width gap-1 q-my-sm'):
                    render_agreement_summary(row)
                    if row.opponent_agreed_at is not None:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('check_circle', size='18px').classes('text-positive')
                            ui.label('You agreed. Waiting on staff.') \
                                .classes('text-caption text-positive')
                    else:
                        async def do_agree(_=None, request=row) -> None:
                            if await agree(request, viewer):
                                await after()

                        ui.button('Agree', icon='thumb_up', on_click=do_agree) \
                            .props('color=positive no-caps')

    async def after() -> None:
        section.refresh()
        if on_agreed is not None:
            await on_agreed()

    await section()

    if agree_request_id is None:
        return
    state = await service.agreement_link_state(int(agree_request_id), viewer)
    if state == AGREE_OPEN:
        request = await service.get_by_id(int(agree_request_id))
        if request is not None:
            await RescheduleAgreeDialog(request, viewer, on_agreed=after).open()
            return
    _notify(_STALE_AGREE.get(state, _NOT_YOURS))


async def render_race_rooms(viewer: Optional[User]) -> None:
    """The open race rooms for this player's matches, each with a way in."""
    if viewer is None:
        return
    if not await FeatureFlagService().is_enabled(FeatureFlag.RACETIME_ROOMS):
        return
    rooms = await RacetimeRoomService().open_rooms_for_player(viewer)
    if not rooms:
        return
    with ui.card().classes('wiz-subcard'):
        ui.label(
            'Your race room is open' if len(rooms) == 1 else 'Your race rooms are open'
        ).classes('wiz-subcard__title')
        for room in rooms:
            match = room.match
            opponents = [
                p.user.preferred_name for p in match.players if p.user_id != viewer.id
            ]
            with ui.row().classes(
                'items-center justify-between full-width q-my-xs gap-2'
            ):
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
