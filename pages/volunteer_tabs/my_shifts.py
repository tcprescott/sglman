"""Volunteer My Shifts tab."""

from datetime import datetime, timezone

from nicegui import ui

from application.services import current_user_from_storage
from application.services.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import format_eastern_display


async def my_shifts_tab() -> None:
    user = await current_user_from_storage()
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = VolunteerScheduleService()

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('My Shifts').classes('page-title')
        ui.separator().classes('separator-spacing')

        @ui.refreshable
        async def shift_list() -> None:
            assignments = await service.assignments_for_user(
                user, upcoming_after=datetime.now(timezone.utc),
            )
            if not assignments:
                ui.label('You have no upcoming shifts.').classes('italic-note')
                return
            for assignment in assignments:
                shift = assignment.shift
                position = shift.position.name if shift.position else 'Volunteer'
                acked = assignment.acknowledged_at is not None
                with ui.card().classes('full-width q-pa-md q-mb-sm'):
                    with ui.row().classes('items-center justify-between full-width'):
                        with ui.column().classes('gap-0'):
                            title = position + (f' — {shift.label}' if shift.label else '')
                            ui.label(title).classes('text-subtitle1')
                            ui.label(
                                f'{format_eastern_display(shift.starts_at)} → '
                                f'{format_eastern_display(shift.ends_at)}'
                            ).classes('text-caption')
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

        await shift_list()
