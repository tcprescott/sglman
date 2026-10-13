"""Submit or edit a community event."""

from typing import Awaitable, Callable, Optional

from nicegui import ui

from application.services import CommunityEventService, EventDraft
from application.services.community_event_service import (
    DESCRIPTION_MAX_LENGTH,
    LOCATION_MAX_LENGTH,
    MAX_RSVP_CAPACITY,
    TITLE_MAX_LENGTH,
)
from models import CommunityEvent, CommunityEventStatus, User
from theme.dialog._helpers import (
    datetime_to_local_input,
    dialog_actions,
    form_dialog,
    local_input_to_datetime,
    native_datetime_input,
)
from theme.markdown_editor import MarkdownEditor
from theme.notify import notify_error

DISCLAIMER = (
    'Community events are run by attendees, not by event staff. Listing one here '
    "doesn't mean staff endorse it; the listing is just for convenience."
)


class CommunityEventDialog:
    """The submit/edit form. ``event`` set means edit; ``on_saved`` runs after a save."""

    def __init__(
        self,
        user: User,
        event: Optional[CommunityEvent] = None,
        *,
        is_staff: bool = False,
        needs_review: bool = True,
        on_saved: Optional[Callable[[CommunityEvent], Awaitable[None]]] = None,
    ) -> None:
        self.user = user
        self.event = event
        self.is_staff = is_staff
        self.needs_review = needs_review
        self.on_saved = on_saved
        self.service = CommunityEventService()

    def _hint(self) -> str:
        if self.event is None:
            if self.is_staff:
                return 'You are staff, so this goes straight onto the listing.'
            if self.needs_review:
                return 'Staff review each event before it shows up for everyone else.'
            return 'This goes straight onto the listing.'
        return 'Changes go live straight away.' if self.event.status is CommunityEventStatus.APPROVED else ''

    def open(self) -> None:
        event = self.event
        hours, minutes = divmod(event.duration_minutes if event else 60, 60)
        title_text = 'Edit community event' if event else 'Submit a community event'

        with form_dialog(title_text) as dialog:
            with ui.column().classes('gap-3 full-width'):
                ui.label(DISCLAIMER).classes('text-caption text-muted')
                title = ui.input(
                    'Title', value=event.title if event else '',
                    validation={f'{TITLE_MAX_LENGTH} characters at most': lambda v: len(v or '') <= TITLE_MAX_LENGTH},
                ).props(f'required maxlength={TITLE_MAX_LENGTH}').classes('full-width')
                starts = native_datetime_input(
                    'Starts', datetime_to_local_input(event.starts_at) if event else '', required=True,
                ).classes('full-width')
                with ui.row().classes('form-pair gap-2'):
                    hours_input = ui.number('Length (hours)', value=hours, min=0, max=72, format='%d')
                    minutes_input = ui.number('and minutes', value=minutes, min=0, max=59, step=5, format='%d')
                location = ui.input(
                    'Where', value=(event.location or '') if event else '',
                    placeholder='Board game room, 2nd floor',
                ).props(f'maxlength={LOCATION_MAX_LENGTH}').classes('full-width')
                description = MarkdownEditor(
                    'Description', value=event.description if event else '',
                    placeholder="What's happening, who it's for, and anything people should bring.",
                )
                with ui.column().classes('gap-1 full-width'):
                    rsvp_switch = ui.switch(
                        'Take RSVPs', value=bool(event and event.rsvp_enabled),
                    ).props('dense')
                    with ui.row().classes('items-center gap-3 full-width') as cap_row:
                        cap_input = ui.number(
                            'Cap (optional)', value=event.rsvp_capacity if event else None,
                            min=1, max=MAX_RSVP_CAPACITY, format='%d',
                        ).classes('grow')
                        ui.label('Leave blank for no limit.').classes('text-caption text-muted')
                    cap_row.bind_visibility_from(rsvp_switch, 'value')
                    ui.label(
                        "Attendees can say they're coming, and you'll see who. RSVPing also gets them the reminder."
                    ).classes('text-caption text-muted')
                ui.label(f'* required · description up to {DESCRIPTION_MAX_LENGTH:,} characters') \
                    .classes('required-legend')
                hint = self._hint()
                if hint:
                    ui.label(hint).classes('text-caption text-muted')

            async def save() -> None:
                with dialog:
                    try:
                        starts_at = local_input_to_datetime(starts.value)
                        if starts_at is None:
                            raise ValueError('Pick when the event starts.')
                        duration = int(hours_input.value or 0) * 60 + int(minutes_input.value or 0)
                        draft = EventDraft(
                            title=title.value or '',
                            description=description.value or '',
                            starts_at=starts_at,
                            duration_minutes=duration,
                            location=location.value,
                            rsvp_enabled=bool(rsvp_switch.value),
                            rsvp_capacity=int(cap_input.value) if cap_input.value else None,
                        )
                        if event is None:
                            saved = await self.service.submit(self.user, draft)
                            message = (
                                'Your event is listed.' if saved.status is CommunityEventStatus.APPROVED
                                else 'Thanks! Staff will review your event and you will get a DM when they do.'
                            )
                        else:
                            saved = await self.service.update(self.user, event.id, draft)
                            message = (
                                'Sent back to staff for review.' if saved.status is CommunityEventStatus.PENDING
                                else 'Event saved.'
                            )
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify(message, color='positive')
                    dialog.close()
                if self.on_saved is not None:
                    await self.on_saved(saved)

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Submit' if event is None else 'Save', on_click=save).props('color=primary')
        dialog.open()
