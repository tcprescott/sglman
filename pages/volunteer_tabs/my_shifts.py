"""Volunteer My Shifts tab."""

from datetime import datetime, timezone

from nicegui import app, ui

from application.services import get_user_from_discord_id
from application.services.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import format_eastern_display


async def my_shifts_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = VolunteerScheduleService()
    state = {'upcoming_only': True}

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row items-center justify-between full-width'):
            ui.label('My Shifts').classes('page-title')

        ui.separator().classes('separator-spacing')

        @ui.refreshable
        async def shift_list() -> None:
            after = datetime.now(timezone.utc) if state['upcoming_only'] else None
            assignments = await service.assignments_for_user(user, upcoming_after=after)
            if not assignments:
                msg = 'You have no upcoming shifts.' if state['upcoming_only'] else 'You have no assigned shifts.'
                ui.label(msg).classes('italic-note')
                return
            for assignment in assignments:
                shift = assignment.shift
                position = shift.position.name if shift.position else 'Volunteer'
                acked = assignment.acknowledged_at is not None
                checked_in = assignment.checked_in_at is not None
                with ui.card().classes('full-width q-pa-md q-mb-sm'):
                    with ui.row().classes('items-center justify-between full-width'):
                        with ui.column().classes('gap-0'):
                            title = position + (f' — {shift.label}' if shift.label else '')
                            ui.label(title).classes('text-subtitle1')
                            ui.label(
                                f'{format_eastern_display(shift.starts_at)} → '
                                f'{format_eastern_display(shift.ends_at)}'
                            ).classes('text-caption')
                        with ui.row().classes('items-center gap-2'):
                            if checked_in:
                                ui.badge('Checked in', color='teal')
                            if acked:
                                ui.badge('Acknowledged', color='positive')
                            else:
                                async def ack(a_id=assignment.id) -> None:
                                    try:
                                        await service.acknowledge(a_id, user)
                                        ui.notify('Shift acknowledged.', color='positive')
                                    except ValueError as e:
                                        ui.notify(str(e), color='warning')
                                    shift_list.refresh()
                                ui.button('Acknowledge', icon='check', on_click=ack).props('color=primary')

        def on_toggle(e) -> None:
            state['upcoming_only'] = not e.value
            shift_list.refresh()

        ui.switch('Show all shifts', on_change=on_toggle)
        await shift_list()
