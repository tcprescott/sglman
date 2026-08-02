"""The player's ask: move this match, or call it off.

Deliberately not a scheduling control. Everything in it says the change is a
*request* — the title, the kind picker's captions, the submit button, and the
confirmation — because a form that takes a date and a time reads as booking one
unless it keeps saying otherwise.
"""

from typing import Callable, Optional

from nicegui import ui

from application.services import MatchRescheduleService
from application.utils.timezone import (
    format_local_display,
    parse_local_datetime,
    to_local,
)
from models import Match, RescheduleRequestKind, User
from theme.dialog._helpers import (
    dialog_actions,
    form_dialog,
    native_date_input,
    native_time_input,
)
from theme.notify import notify_error

KIND_OPTIONS = {
    RescheduleRequestKind.RESCHEDULE.value: 'Move it to another time',
    RescheduleRequestKind.CANCEL.value: 'Call it off — it does not need playing',
}


class RescheduleRequestDialog:
    """Ask staff to move or cancel a match you are playing in."""

    def __init__(
        self,
        match: Match,
        actor: User,
        *,
        on_submit: Optional[Callable] = None,
    ) -> None:
        self.match = match
        self.actor = actor
        self.on_submit = on_submit
        self.service = MatchRescheduleService()

    async def open(self) -> None:
        match = self.match
        current = format_local_display(match.scheduled_at)
        # Prefill the pickers with the slot the match already has, so a player
        # nudging it by an hour edits two characters instead of typing a date.
        local = to_local(match.scheduled_at)
        default_date = local.strftime('%Y-%m-%d') if local else ''
        default_time = local.strftime('%H:%M') if local else ''

        with form_dialog('Ask staff to change this match') as dialog:
            with ui.column().classes('q-pa-md gap-3 full-width'):
                ui.label(
                    'Staff decide on this. Nothing changes until they do, so keep '
                    'playing to the current time until you hear back.'
                ).classes('text-caption text-grey-7')
                ui.label(f'Currently: {current}').classes('text-bold')

                kind_input = ui.select(
                    options=KIND_OPTIONS,
                    value=RescheduleRequestKind.RESCHEDULE.value,
                    label='What are you asking for?',
                ).classes('full-width')

                with ui.column().classes('gap-2 full-width') as when_block:
                    ui.label(
                        'Leave the time blank if you only know you cannot make '
                        'the current slot — staff will pick one.'
                    ).classes('text-caption text-grey-7')
                    with ui.row().classes('gap-2 full-width no-wrap'):
                        date_input = native_date_input(
                            'Preferred date', default_date,
                        ).classes('col')
                        time_input = native_time_input(
                            'Preferred time', default_time,
                        ).classes('col')

                # The time block is meaningless for a cancellation, and leaving
                # it on screen invites someone to fill it in and expect it to
                # mean something.
                when_block.bind_visibility_from(
                    kind_input, 'value',
                    backward=lambda v: v == RescheduleRequestKind.RESCHEDULE.value,
                )

                reason_input = ui.textarea(
                    label='Why',
                    placeholder="Staff read this and nothing else, so say enough to decide on.",
                ).props('required autofocus').classes('full-width')
                ui.label('* required').classes('required-legend')

            async def submit() -> None:
                reason = (reason_input.value or '').strip()
                if not reason:
                    ui.notify('Say why you need the change.', color='warning')
                    return

                kind = RescheduleRequestKind(kind_input.value)
                proposed_at = None
                if kind is RescheduleRequestKind.RESCHEDULE:
                    date_value = (date_input.value or '').strip()
                    time_value = (time_input.value or '').strip()
                    if bool(date_value) != bool(time_value):
                        ui.notify(
                            'Give both a date and a time, or leave both blank to '
                            'let staff pick.', color='warning',
                        )
                        return
                    if date_value:
                        try:
                            proposed_at = parse_local_datetime(date_value, time_value)
                        except ValueError as e:
                            ui.notify(str(e), color='warning')
                            return

                try:
                    await self.service.submit(
                        self.match.id, self.actor,
                        kind=kind, reason=reason, proposed_at=proposed_at,
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return

                ui.notify(
                    'Sent. Staff have been notified, and your opponent has been '
                    'asked whether it works for them.', color='positive',
                )
                dialog.close()
                if self.on_submit:
                    await self.on_submit()

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                send = ui.button('Send request', on_click=submit).props('color=primary')
                send.bind_enabled_from(
                    reason_input, 'value', backward=lambda v: bool((v or '').strip()),
                )

        dialog.open()
