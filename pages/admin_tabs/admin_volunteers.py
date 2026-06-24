"""Admin Volunteers management page (coordinator schedule grid)."""

from datetime import timedelta

from nicegui import ui

from application.services import AuthService, SystemConfigService, current_user_from_storage
from application.services.volunteer_autoschedule_service import VolunteerAutoscheduleService
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_position_service import VolunteerPositionService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_time,
    parse_eastern_datetime,
)
from models import VolunteerAssignment, VolunteerAvailabilityStatus
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.dialog.volunteer_position_dialog import VolunteerPositionDialog
from theme.dialog.volunteer_profile_dialog import VolunteerProfileDialog
from theme.dialog.volunteer_shift_dialog import VolunteerShiftDialog


# Standard four 4-hour shift blocks (Eastern), matching the 2025 schedule.
STANDARD_BLOCKS = [
    ('Shift 1', '08:00', '12:00'),
    ('Shift 2', '12:00', '16:00'),
    ('Shift 3', '16:00', '20:00'),
    ('Shift 4', '20:00', '00:00'),
]


async def admin_volunteers_page() -> None:
    actor = await current_user_from_storage()
    if not await AuthService.can_manage_volunteers(actor):
        ui.label('You do not have permission to manage volunteers.').classes('text-error')
        return

    position_service = VolunteerPositionService()
    schedule_service = VolunteerScheduleService()
    autoschedule_service = VolunteerAutoscheduleService()
    availability_service = VolunteerAvailabilityService()
    profile_service = VolunteerProfileService()

    event_start, event_end = await SystemConfigService.get_event_window()
    day_options = []
    d = event_start
    while d <= event_end:
        day_options.append(d.isoformat())
        d += timedelta(days=1)
    state = {'day': day_options[0] if day_options else event_start.isoformat()}

    def _day_window(day_str: str):
        start = parse_eastern_datetime(day_str, '00:00')
        return start, start + timedelta(hours=30)

    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            ui.label('Volunteer Scheduling').classes('page-title')
        ui.separator().classes('separator-spacing')

        # --- Controls ----------------------------------------------------
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                day_select = ui.select(
                    day_options, value=state['day'], label='Event day',
                ).classes('w-48')

                def on_day_change(e):
                    state['day'] = e.value
                    grid.refresh()
                day_select.on_value_change(on_day_change)

                ui.button('Auto-fill from availability', icon='smart_toy',
                          on_click=lambda: auto_fill()).props('flat color=primary')
                ui.button('Clear draft', icon='clear_all',
                          on_click=lambda: clear_draft()).props('flat color=negative')
                ui.button('Volunteer roster', icon='people',
                          on_click=lambda: open_volunteer_roster_dialog()).props('flat')
                ui.button('Manage positions', icon='badge',
                          on_click=lambda: open_positions_dialog()).props('flat')
                ui.button('Reset all volunteer data', icon='delete_forever',
                          on_click=lambda: open_reset_dialog()).props('flat color=negative')

        # --- Grid --------------------------------------------------------
        grid_container = ui.column().classes('full-width')

        @ui.refreshable
        async def grid() -> None:
            win_start, win_end = _day_window(state['day'])
            positions = await position_service.list_active()
            if not positions:
                ui.label('No active positions yet. Use "Manage positions" to add one.') \
                    .classes('italic-note')
                return

            shifts = await schedule_service.list_shifts_for_window(win_start, win_end)
            by_position: dict = {}
            for shift in shifts:
                by_position.setdefault(shift.position_id, []).append(shift)

            for position in positions:
                with ui.card().classes('full-width q-pa-sm q-mb-sm'):
                    with ui.row().classes('items-center justify-between full-width'):
                        ui.label(position.name).classes('text-subtitle1')
                        with ui.row().classes('gap-1'):
                            ui.button('Generate standard shifts', icon='auto_awesome_motion',
                                      on_click=lambda p=position: generate_shifts(p)) \
                                .props('flat dense color=primary')
                            ui.button('Add shift', icon='add',
                                      on_click=lambda p=position: open_shift_dialog(position=p)) \
                                .props('flat dense color=primary')
                    pos_shifts = by_position.get(position.id, [])
                    if not pos_shifts:
                        ui.label('No shifts for this day yet.').classes('italic-note q-pa-sm')
                        continue
                    with ui.row().classes('gap-2 items-stretch').style('flex-wrap: wrap;'):
                        for shift in sorted(pos_shifts, key=lambda s: s.starts_at):
                            _render_shift_card(shift)

        def _render_shift_card(shift) -> None:
            filled = len(shift.assignments)
            understaffed = filled < shift.slots_needed
            with ui.card().classes('q-pa-sm').style('min-width: 220px; flex: 0 0 auto;'):
                header = shift.label or f'{format_eastern_time(shift.starts_at)}'
                with ui.row().classes('items-center justify-between full-width'):
                    ui.label(header).classes('text-weight-medium')
                    ui.badge(f'{filled}/{shift.slots_needed}',
                             color='warning' if understaffed else 'positive')
                ui.label(
                    f'{format_eastern_time(shift.starts_at)}–{format_eastern_time(shift.ends_at)} ET'
                ).classes('text-caption')
                for assignment in shift.assignments:
                    _render_assignment_chip(shift, assignment)
                with ui.row().classes('items-center gap-1'):
                    ui.button('Assign', icon='person_add',
                              on_click=lambda s=shift: open_assign_dialog(s)).props('flat dense color=primary')
                    ui.space()
                    ui.button(icon='edit',
                              on_click=lambda s=shift: open_shift_dialog(shift=s)) \
                        .props('flat dense').tooltip('Edit shift')
                    ui.button(icon='delete', color='negative',
                              on_click=lambda s=shift: confirm_delete_shift(s)) \
                        .props('flat dense').tooltip('Delete shift')

        def _render_assignment_chip(shift, assignment: VolunteerAssignment) -> None:
            name = assignment.user.preferred_name if assignment.user else 'Unknown'
            with ui.row().classes('items-center gap-1 no-wrap'):
                chip = ui.chip(name, removable=True).props('dense')
                if assignment.auto_generated:
                    chip.props('outline color=secondary').tooltip('Auto-generated draft')
                elif assignment.acknowledged_at:
                    chip.props('color=positive')

                async def remove(a=assignment) -> None:
                    await schedule_service.unassign(actor, a)
                    ui.notify('Removed assignment.', color='info')
                    grid.refresh()
                chip.on('remove', lambda a=assignment: remove(a))

                if assignment.checked_in_at:
                    ui.icon('how_to_reg', color='teal', size='sm').tooltip('Checked in')
                else:
                    async def do_check_in(a_id=assignment.id) -> None:
                        try:
                            await schedule_service.check_in(a_id, actor)
                            ui.notify('Volunteer checked in.', color='positive')
                        except (ValueError, PermissionError) as e:
                            ui.notify(str(e), color='warning')
                        grid.refresh()
                    ui.button(icon='login', on_click=do_check_in) \
                        .props('flat dense color=teal').tooltip('Check in volunteer')

        # --- Assignment picker ------------------------------------------
        async def open_assign_dialog(shift) -> None:
            pool = await profile_service.assignable_volunteers()
            avail_map = await availability_service.availability_map(
                [u.id for u in pool], shift.starts_at, shift.ends_at,
            )
            assigned_ids = {a.user_id for a in shift.assignments}

            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                title = shift.position.name if shift.position else 'Shift'
                ui.label(f'Assign to {title} '
                         f'({format_eastern_time(shift.starts_at)}–{format_eastern_time(shift.ends_at)} ET)') \
                    .classes('text-subtitle1 q-pa-sm')
                ui.separator()
                if not pool:
                    ui.label('No volunteers in pool. Users must have the Volunteer role assigned.') \
                        .classes('italic-note q-pa-md')
                with ui.column().classes('q-pa-sm gap-1').style('max-height: 50vh; overflow-y: auto;'):
                    for volunteer in pool:
                        if volunteer.id in assigned_ids:
                            continue
                        status = VolunteerAvailabilityService.covers(
                            avail_map.get(volunteer.id, []), shift.starts_at, shift.ends_at,
                        )
                        _render_picker_row(dialog, shift, volunteer, status)
                with ui.row().classes('justify-end q-pa-sm'):
                    ui.button('Close', on_click=dialog.close).props('flat')
                dialog.open()

        def _render_picker_row(dialog, shift, volunteer, status) -> None:
            with ui.row().classes('items-center justify-between full-width'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(volunteer.preferred_name)
                    if status == VolunteerAvailabilityStatus.PREFERRED:
                        ui.badge('Preferred', color='positive')
                    elif status == VolunteerAvailabilityStatus.AVAILABLE:
                        ui.badge('Available', color='positive').props('outline')
                    elif status == VolunteerAvailabilityStatus.UNAVAILABLE:
                        ui.badge('Unavailable', color='negative')

                async def do_assign(u=volunteer) -> None:
                    try:
                        _, warnings = await schedule_service.assign(actor, shift, u)
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    for w in warnings:
                        ui.notify(w, color='warning')
                    ui.notify(f'Assigned {u.preferred_name}.', color='positive')
                    dialog.close()
                    grid.refresh()
                ui.button('Assign', on_click=do_assign).props('dense flat color=primary')

        # --- Actions -----------------------------------------------------
        async def generate_shifts(position) -> None:
            await schedule_service.generate_day_shifts(
                actor, state['day'], [position.id], STANDARD_BLOCKS,
            )
            ui.notify(f'Generated shifts for {position.name} (staggered where configured).',
                      color='positive')
            grid.refresh()

        async def open_shift_dialog(shift=None, position=None) -> None:
            async def after(_):
                grid.refresh()
            await VolunteerShiftDialog(
                shift=shift, position=position, default_day=state['day'], on_submit=after,
            ).open()

        async def confirm_delete_shift(shift) -> None:
            assigned = len(shift.assignments)
            message = 'Delete this shift?'
            if assigned:
                message = (f'This shift has {assigned} assigned volunteer(s). '
                           'Deleting it removes those assignments. Continue?')

            async def on_confirm() -> None:
                confirm.dialog.close()
                try:
                    await schedule_service.delete_shift(actor, shift)
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify('Shift deleted.', color='info')
                grid.refresh()

            confirm = ConfirmationDialog(message=message, on_confirm=on_confirm, confirm_text='Delete')
            confirm.open()

        async def auto_fill() -> None:
            win_start, win_end = _day_window(state['day'])
            result = await autoschedule_service.generate_draft(actor, win_start, win_end)
            unfilled = sum(u['open'] for u in result['unfilled'])
            ui.notify(
                f"Draft created: {result['created']} assignment(s), "
                f"{unfilled} slot(s) still open (pool of {result['pool_size']}).",
                color='positive' if result['created'] else 'warning',
            )
            grid.refresh()

        async def clear_draft() -> None:
            win_start, win_end = _day_window(state['day'])
            removed = await autoschedule_service.clear_draft(actor, win_start, win_end)
            ui.notify(f'Cleared {removed} draft assignment(s).', color='info')
            grid.refresh()

        def open_reset_dialog() -> None:
            CONFIRM_PHRASE = 'yes please delete all shifts'
            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                ui.label('Reset all volunteer data').classes('text-subtitle1 q-pa-sm text-negative')
                ui.separator()
                with ui.column().classes('q-pa-md gap-3'):
                    ui.label(
                        'This will permanently delete ALL shifts and assignments across every day. '
                        'This cannot be undone.'
                    ).classes('text-body2')
                    ui.label(f'Type "{CONFIRM_PHRASE}" to confirm:').classes('text-caption')
                    confirm_input = ui.input().classes('full-width')

                    async def do_reset() -> None:
                        if confirm_input.value.strip().lower() != CONFIRM_PHRASE:
                            ui.notify('Confirmation text does not match.', color='warning')
                            return
                        dialog.close()
                        try:
                            deleted = await schedule_service.reset_all_shifts(actor)
                        except (ValueError, PermissionError) as e:
                            ui.notify(str(e), color='warning')
                            return
                        ui.notify(f'Deleted {deleted} shift(s) and all assignments.', color='negative')
                        grid.refresh()

                ui.separator()
                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    ui.button('Delete everything', on_click=do_reset).props('color=negative')
            dialog.open()

        # --- Volunteer roster -------------------------------------------
        async def open_volunteer_roster_dialog() -> None:
            pool = await profile_service.assignable_volunteers()
            positions = await position_service.list_active()

            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                ui.label('Volunteer Roster').classes('text-subtitle1 q-pa-sm')
                ui.separator()
                with ui.column().classes('q-pa-sm gap-1').style('max-height: 60vh; overflow-y: auto; min-width: 360px;'):
                    if not pool:
                        ui.label('No volunteers in pool.').classes('italic-note q-pa-md')
                    for volunteer in pool:
                        with ui.row().classes('items-center justify-between full-width q-px-sm'):
                            ui.label(volunteer.preferred_name)

                            async def open_profile(u=volunteer) -> None:
                                await VolunteerProfileDialog(
                                    user=u, positions=positions,
                                ).open()

                            ui.button(icon='manage_accounts', on_click=open_profile) \
                                .props('flat dense').tooltip('View availability & qualifications')

                with ui.row().classes('justify-end q-pa-sm'):
                    ui.button('Close', on_click=dialog.close).props('flat')
            dialog.open()

        # --- Positions manager ------------------------------------------
        async def open_positions_dialog() -> None:
            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                ui.label('Volunteer Positions').classes('text-subtitle1 q-pa-sm')
                ui.separator()

                @ui.refreshable
                async def position_list() -> None:
                    positions = await position_service.list_all()
                    if not positions:
                        ui.label('No positions yet.').classes('italic-note q-pa-sm')
                    for position in positions:
                        with ui.row().classes('items-center justify-between full-width q-px-sm'):
                            label = position.name + ('' if position.is_active else ' (inactive)')
                            ui.label(label)
                            async def edit(p=position) -> None:
                                async def after(_):
                                    position_list.refresh()
                                    grid.refresh()
                                await VolunteerPositionDialog(position=p, on_submit=after).open()
                            ui.button(icon='edit', on_click=edit).props('flat dense')

                with ui.column().classes('q-pa-sm gap-1').style('max-height: 50vh; overflow-y: auto;'):
                    await position_list()

                async def add_position() -> None:
                    async def after(_):
                        position_list.refresh()
                        grid.refresh()
                    await VolunteerPositionDialog(on_submit=after).open()

                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Add position', icon='add', on_click=add_position).props('flat color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')
                dialog.open()

        with grid_container:
            await grid()
