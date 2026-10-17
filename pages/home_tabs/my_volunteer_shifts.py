"""Your volunteer shifts, as a My Schedule section.

My Schedule answers "what am I doing at this event?", and for anyone who
volunteers, the shifts were the one commitment it left out: they lived only on
Volunteer → My Shifts. This is the agenda of what is still ahead, grouped by
day, one row per shift with the one thing to do about it (I'm here, or
Acknowledge) and the rest behind ⋮. My Shifts keeps the full cards and the
finished shifts; the section links there.
"""

from datetime import datetime, timezone
from typing import Optional

from nicegui import ui

from application.services import (
    AuthService,
    SystemConfigService,
    VolunteerArrivalService,
)
from application.services.volunteer import can_self_check_in, can_undo_check_in, describe_late
from application.services.volunteer.volunteer_hours import VolunteerHoursService
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from application.utils.app_links import volunteer_my_shifts_url
from application.utils.timezone import format_local_display, format_local_time, to_local
from models import User
from pages.volunteer_tabs.my_shifts import (
    hours_message,
    open_release_dialog,
    render_shift_brief,
    shift_actions,
    shift_title,
)
from theme.dialog._helpers import form_dialog
from theme.menu import menu_action, more_menu
from theme.notify import notify_error
from theme.section import section_panel
from theme.shift_arrival_banner import arrival_changed, on_arrival_change
from theme.steady import steady_refreshable

#: The section's DOM id, so a link can scroll to it.
SHIFTS_SECTION_ID = 'my-shifts'


def shift_status(assignment, now: datetime) -> tuple[str, str, str]:
    """(chip kind, icon, text) for one row.

    Module-level and pure so the precedence is testable: arriving says more
    than running late, which says more than the shift being under way, which
    says more than having acknowledged it.
    """
    shift = assignment.shift
    if assignment.checked_in_at is not None:
        return 'ok', 'how_to_reg', f'Arrived {format_local_time(assignment.checked_in_at)}'
    late = describe_late(assignment)
    if late:
        return 'pending', 'schedule', late
    if shift.starts_at <= now < shift.ends_at:
        return 'live', 'radio_button_checked', 'On now'
    if assignment.acknowledged_at is not None:
        return 'ok', 'check', 'Acknowledged'
    return 'pending', 'error_outline', 'Needs your OK'


def primary_action(assignment, now: datetime) -> Optional[str]:
    """The row's one button: ``'arrive'``, ``'ack'`` or None.

    "I'm here" wins once check-in opens, because by then acknowledging is moot.
    """
    if can_self_check_in(assignment, now):
        return 'arrive'
    if shift_actions(assignment, now)[0]:
        return 'ack'
    return None


def day_heading(starts_at: datetime) -> str:
    local = to_local(starts_at) or starts_at
    return f'{local:%A, %B} {local.day}'


async def my_volunteer_shifts_section(user: User) -> None:
    """Build the panel; the caller has already checked ``FeatureFlag.VOLUNTEERS``.

    Nothing renders for someone with no upcoming shifts: most players never
    volunteer, and an empty panel would sit on every one of their schedules.
    """
    service = VolunteerScheduleService()
    arrival_service = VolunteerArrivalService()
    assignments = await service.assignments_for_user(
        user, upcoming_after=datetime.now(timezone.utc), with_shiftmates=True,
    )
    if not assignments:
        return

    summary = await VolunteerHoursService().for_user(user)
    lead_minutes = await SystemConfigService.get_volunteer_reminder_lead_minutes()
    hub = await AuthService.can_view_volunteer(user)

    panel = await section_panel(
        'Your volunteer shifts',
        icon='volunteer_activism',
        subtitle=hours_message(summary),
        help_topics=[('my-shifts', 'Your shifts'), 'shift-release'],
        user=user,
    )
    panel.body.props(f'id={SHIFTS_SECTION_ID}')

    async def arrive(assignment) -> None:
        try:
            await arrival_service.check_in_self(assignment.id, user)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify("You're checked in. Thanks!", color='positive')
        await arrival_changed()

    async def undo(assignment) -> None:
        try:
            await arrival_service.undo_check_in(assignment.id, user)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Check-in taken back.', color='info')
        await arrival_changed()

    async def acknowledge(assignment) -> None:
        try:
            await service.acknowledge(assignment.id, user)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Shift acknowledged. Thanks!', color='positive')
        await rows.refresh()

    async def release(assignment) -> None:
        async def released() -> None:
            await rows.refresh()
        await open_release_dialog(assignment, user, lead_minutes, released)

    def details(assignment) -> None:
        shift = assignment.shift
        with form_dialog(shift_title(shift), card_classes='dialog-card dialog-card--sm') as dialog:
            with ui.column().classes('q-pa-md gap-0 full-width'):
                ui.label(
                    f'{format_local_display(shift.starts_at)} → '
                    f'{format_local_display(shift.ends_at)}'
                ).classes('text-caption')
                render_shift_brief(assignment)
        dialog.open()

    def render_row(assignment, now: datetime) -> None:
        shift = assignment.shift
        title = shift_title(shift)
        kind, icon, text = shift_status(assignment, now)
        _, can_release = shift_actions(assignment, now)
        with ui.element('div').classes('wiz-shift-row'):
            with ui.column().classes('wiz-shift-row__time gap-0'):
                ui.label(format_local_time(shift.starts_at)).classes('text-weight-medium')
                ui.label(f'to {format_local_time(shift.ends_at)}').classes('text-caption text-muted')
            with ui.column().classes('wiz-shift-row__main gap-1'):
                ui.label(title).classes('text-weight-medium')
                with ui.element('span').classes(f'wiz-chip wiz-chip--{kind}'):
                    ui.icon(icon, size='14px')
                    ui.label(text)
            with ui.row().classes('wiz-shift-row__actions items-center no-wrap gap-1'):
                action = primary_action(assignment, now)
                if action == 'arrive':
                    ui.button("I'm here", icon='place',
                              on_click=lambda a=assignment: arrive(a)).props('color=primary no-caps')
                elif action == 'ack':
                    ui.button('Acknowledge', icon='check',
                              on_click=lambda a=assignment: acknowledge(a)).props('color=primary no-caps')
                with more_menu(title):
                    menu_action('info', 'Shift details', lambda a=assignment: details(a))
                    if can_undo_check_in(assignment, user, now):
                        menu_action('undo', 'Undo check-in', lambda a=assignment: undo(a))
                    if can_release:
                        ui.separator()
                        menu_action('event_busy', "Can't make it…",
                                    lambda a=assignment: release(a), negative=True)

    @steady_refreshable
    async def rows() -> None:
        now = datetime.now(timezone.utc)
        current = await service.assignments_for_user(user, upcoming_after=now, with_shiftmates=True)
        if not current:
            ui.label('No upcoming shifts.').classes('text-muted')
        day = None
        for assignment in current:
            heading = day_heading(assignment.shift.starts_at)
            if heading != day:
                day = heading
                ui.label(heading).classes('wiz-shift-day')
            render_row(assignment, now)

    with panel.body:
        with ui.column().classes('gap-0 full-width'):
            await rows()
        if hub:
            ui.link('All your shifts on the Volunteer page', volunteer_my_shifts_url())
    on_arrival_change(rows.refresh)
