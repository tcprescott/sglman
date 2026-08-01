"""Volunteer My Shifts tab."""

from datetime import datetime, timezone
from typing import Optional

from nicegui import app, ui

from application.services import SystemConfigService, get_user_from_discord_id
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import format_local_display
from theme.help import help_icon
from theme.notify import notify_error


def release_warning(starts_at: datetime, lead_minutes: int) -> Optional[str]:
    """Warn when giving this shift back leaves the coordinator little time.

    Module-level and pure so the copy decision is testable without a slot
    context. The window is the tenant's reminder lead or 24 hours, whichever is
    longer — inside either, "your coordinator has been told" is not the same as
    "someone will cover it".
    """
    hours_out = (starts_at - datetime.now(timezone.utc)).total_seconds() / 3600.0
    if hours_out <= 0:
        return ('This shift has already started. Your coordinator will be told '
                'right away, but may not find cover.')
    window_hours = max(24.0, (lead_minutes or 0) / 60.0)
    if hours_out > window_hours:
        return None
    return (f'This shift starts in about {round(hours_out)} hour(s). Your coordinator '
            'will be told right away, but may not find cover.')


async def my_shifts_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = VolunteerScheduleService()
    state = {'upcoming_only': True}
    lead_minutes = await SystemConfigService.get_volunteer_reminder_lead_minutes()

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row items-center full-width'):
            ui.label('My Shifts').classes('page-title')
            await help_icon('my-shifts')
            ui.space()

        ui.separator().classes('separator-spacing')

        async def confirm_release(assignment) -> None:
            shift = assignment.shift
            position = shift.position.name if shift.position else 'Volunteer'
            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                with ui.row().classes('items-center no-wrap q-pa-sm'):
                    ui.label('Give this shift back?').classes('text-subtitle1')
                    await help_icon('shift-release')
                ui.separator()
                with ui.column().classes('q-pa-md gap-2 full-width'):
                    ui.label(
                        position + (f' — {shift.label}' if shift.label else '')
                    ).classes('text-body2 text-weight-medium')
                    ui.label(
                        f'{format_local_display(shift.starts_at)} → '
                        f'{format_local_display(shift.ends_at)}'
                    ).classes('text-caption')
                    warning = release_warning(shift.starts_at, lead_minutes)
                    if warning:
                        ui.label(warning).classes('text-caption text-warning')
                    reason_input = ui.textarea('Reason (optional)').classes('full-width')
                    reason_input.props('hint="Your coordinator sees this."')

                async def do_release() -> None:
                    dialog.close()
                    try:
                        await service.release(assignment.id, user, reason_input.value)
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify('Shift released. Your coordinator has been told.', color='info')
                    shift_list.refresh()

                ui.separator()
                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Keep it', on_click=dialog.close).props('flat')
                    ui.button('Give it back', on_click=do_release).props('color=negative')
            dialog.open()

        def _render_brief(assignment) -> None:
            """What the shift actually involves — the two fields the coordinator
            writes and nothing used to render."""
            shift = assignment.shift
            description = getattr(shift.position, 'description', None) if shift.position else None
            if description:
                ui.label(description).classes('text-body2 q-mt-sm')
            if shift.notes:
                with ui.column().classes('q-mt-sm q-pa-sm gap-0') \
                        .style('border: 1px solid var(--q-primary); border-radius: 4px;'):
                    ui.label('For this shift').classes('text-caption text-weight-medium')
                    ui.label(shift.notes).classes('text-body2')
            # Drafts are excluded: naming someone who has not been told would leak
            # the draft invariant out sideways.
            others = sorted(
                a.user.preferred_name
                for a in shift.assignments
                if a.user_id != assignment.user_id and not a.auto_generated and a.user
            )
            ui.label(
                f"With: {', '.join(others)}" if others
                else 'You are the only one scheduled for this slot.'
            ).classes('text-caption text-grey q-mt-sm')

        @ui.refreshable
        async def shift_list() -> None:
            after = datetime.now(timezone.utc) if state['upcoming_only'] else None
            assignments = await service.assignments_for_user(
                user, upcoming_after=after, with_shiftmates=True,
            )
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
                    with ui.column().classes('gap-0 full-width'):
                        title = position + (f' — {shift.label}' if shift.label else '')
                        ui.label(title).classes('text-subtitle1')
                        ui.label(
                            f'{format_local_display(shift.starts_at)} → '
                            f'{format_local_display(shift.ends_at)}'
                        ).classes('text-caption')
                        assigned_by = assignment.assigned_by
                        provenance = 'Scheduled'
                        if assigned_by is not None:
                            provenance = f'Scheduled by {assigned_by.preferred_name}'
                        provenance += f' · {format_local_display(assignment.created_at)}'
                        if assignment.acknowledged_at:
                            provenance += (
                                f' · you acknowledged '
                                f'{format_local_display(assignment.acknowledged_at)}'
                            )
                        ui.label(provenance).classes('text-caption text-grey')
                        _render_brief(assignment)
                    # Actions wrap in their own row: the header row could not hold
                    # two buttons plus the badge stack at 390px.
                    with ui.row().classes('items-center gap-2 full-width q-mt-sm') \
                            .style('flex-wrap: wrap;'):
                        if checked_in:
                            ui.badge('Checked in', color='teal')
                        if acked:
                            ui.badge('Acknowledged', color='positive')
                        ui.space()
                        if not acked:
                            async def ack(a_id=assignment.id) -> None:
                                try:
                                    await service.acknowledge(a_id, user)
                                    ui.notify('Thanks — shift acknowledged.', color='positive')
                                except (ValueError, PermissionError) as e:
                                    notify_error(e)
                                shift_list.refresh()
                            ui.button('Acknowledge', icon='check', on_click=ack).props('color=primary')
                        # Offered whether or not it is acknowledged — agreeing to a
                        # shift is not a commitment you cannot revise.
                        ui.button("Can't make this", icon='event_busy',
                                  on_click=lambda a=assignment: confirm_release(a)) \
                            .props('flat color=negative')

        def on_toggle(e) -> None:
            state['upcoming_only'] = not e.value
            shift_list.refresh()

        ui.switch('Show all shifts', on_change=on_toggle)
        await shift_list()
