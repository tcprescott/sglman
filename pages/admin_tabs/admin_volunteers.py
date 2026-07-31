"""Admin Volunteers management page (coordinator schedule grid)."""

from datetime import timedelta
from typing import List, Optional

from nicegui import app, ui

from application.services import AuthService, SystemConfigService, get_user_from_discord_id
from application.services.volunteer.volunteer_autoschedule_service import VolunteerAutoscheduleService
from application.services.volunteer.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer.volunteer_position_service import VolunteerPositionService
from application.services.volunteer.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer.volunteer_qualification_service import VolunteerQualificationService
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from application.utils.timezone import (
    format_local_time,
    parse_local_datetime,
)
from models import VolunteerAssignment, VolunteerAvailabilityStatus
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.dialog.volunteer_autofill_dialog import VolunteerAutofillDialog
from theme.dialog.volunteer_export_dialog import VolunteerExportDialog
from theme.dialog.volunteer_position_dialog import VolunteerPositionDialog
from theme.dialog.volunteer_shift_dialog import VolunteerShiftDialog
from theme.notify import notify_error

# Standard four 4-hour shift blocks, in the community's own timezone (the
# generator resolves them against it), matching the 2025 schedule.
STANDARD_BLOCKS = [
    ('Shift 1', '08:00', '12:00'),
    ('Shift 2', '12:00', '16:00'),
    ('Shift 3', '16:00', '20:00'),
    ('Shift 4', '20:00', '00:00'),
]

# Namespaced like the match board's filter keys, and tenant-scoped, so a
# coordinator working two communities does not carry day 3 of one into the other.
_DAY_KEY = 'volunteers:day'


def stored_or_default_day(
    stored: Optional[str], day_options: List[str], fallback: str,
) -> str:
    """The day to open on. A stored day from a previous event is not a day of this one."""
    return stored if stored in day_options else fallback


async def admin_volunteers_page(day: str | None = None) -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if not await AuthService.can_manage_volunteers(actor):
        ui.label('You do not have permission to manage volunteers.').classes('text-error')
        return

    position_service = VolunteerPositionService()
    schedule_service = VolunteerScheduleService()
    autoschedule_service = VolunteerAutoscheduleService()
    availability_service = VolunteerAvailabilityService()
    profile_service = VolunteerProfileService()
    qualification_service = VolunteerQualificationService()

    event_start, event_end = await SystemConfigService.get_event_window()
    day_options = []
    d = event_start
    while d <= event_end:
        day_options.append(d.isoformat())
        d += timedelta(days=1)
    # Per-page state, never module level: NiceGUI shares one process across users.
    # ``last_run`` holds the most recent auto-fill result for the summary panel;
    # the durable record of a run is its audit row, not this.
    #
    # A deep link (``?day=``) is a deliberate destination, so it outranks the
    # remembered day — but only when it names a day this event actually has; an
    # out-of-window or malformed date falls through to the stored one rather
    # than opening an empty grid for a day that isn't real.
    state = {
        'day': stored_or_default_day(
            day if day in day_options else tenant_session_get(_DAY_KEY),
            day_options,
            day_options[0] if day_options else event_start.isoformat(),
        ),
        'last_run': None,
        # Per-position "I opened this fully-staffed one anyway", keyed by id.
        'folds': {},
    }

    def _day_window(day_str: str):
        start = parse_local_datetime(day_str, '00:00')
        return start, start + timedelta(hours=30)

    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            ui.label('Volunteer Scheduling').classes('page-title')
        ui.separator().classes('separator-spacing')

        ui.label(
            'Build the volunteer shift grid: create positions and shifts, auto-fill '
            'from availability, and assign volunteers per shift.'
        ).classes('text-caption text-grey')

        # --- Coverage strip ----------------------------------------------
        # The one number a coordinator wants on-site — how much of today is
        # uncovered — used to require scrolling 5.8 screenfuls and adding up.
        strip_container = ui.row().classes('full-width')

        def refresh_all() -> None:
            """Every handler on this page changes the grid, the strip, the draft
            count or the panel's staleness — so they all refresh together."""
            coverage_strip.refresh()
            draft_banner.refresh()
            result_panel.refresh()
            grid.refresh()

        @ui.refreshable
        async def coverage_strip() -> None:
            win_start, win_end = _day_window(state['day'])
            summary = await schedule_service.day_summary(win_start, win_end)
            if not summary['shifts']:
                ui.label('No shifts on this day yet.').classes('text-caption text-grey')
                return
            with ui.row().classes('items-center gap-2').style('flex-wrap: wrap;'):
                ui.chip(f"{summary['filled']}/{summary['needed']} slots filled") \
                    .props('outline dense')
                if summary['open']:
                    ui.chip(f"{summary['open']} open").props('dense color=warning')
                else:
                    ui.chip('Fully staffed').props('dense color=positive')
                if summary['unacknowledged']:
                    ui.chip(f"{summary['unacknowledged']} awaiting acknowledgment") \
                        .props('outline dense')
                if summary['drafts']:
                    ui.chip(f"{summary['drafts']} draft").props('outline dense color=secondary')

        # --- Controls ----------------------------------------------------
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                day_select = ui.select(
                    day_options, value=state['day'], label='Event day',
                ).classes('w-48')

                def on_day_change(e):
                    state['day'] = e.value
                    tenant_session_set(_DAY_KEY, e.value)
                    refresh_all()
                day_select.on_value_change(on_day_change)

                ui.button('Auto-fill from availability', icon='smart_toy',
                          on_click=lambda: auto_fill()).props('flat color=primary')
                ui.button('Manage positions', icon='badge',
                          on_click=lambda: open_positions_dialog()).props('flat')
                ui.button('Export data', icon='download',
                          on_click=lambda: VolunteerExportDialog().open()) \
                    .props('flat').tooltip('Download the roster, availability and schedule as CSVs')
                ui.button('Reset all volunteer data', icon='delete_forever',
                          on_click=lambda: open_reset_dialog()).props('flat color=negative')

        # --- Draft banner ------------------------------------------------
        banner_container = ui.column().classes('full-width')

        @ui.refreshable
        async def draft_banner() -> None:
            win_start, win_end = _day_window(state['day'])
            pending = await schedule_service.count_drafts(win_start, win_end)
            if not pending:
                return
            with ui.card().classes('full-width q-pa-sm wiz-draft-banner'):
                with ui.row().classes('items-center gap-2 full-width').style('flex-wrap: wrap;'):
                    ui.icon('edit_note', color='secondary')
                    ui.label(
                        f'{pending} draft assignment(s) on this day. '
                        'The volunteers have not been told yet.'
                    ).classes('text-body2')
                    ui.space()
                    ui.button('Publish draft', icon='send',
                              on_click=lambda: confirm_publish(pending)) \
                        .props('color=positive')
                    ui.button('Clear draft', icon='clear_all',
                              on_click=lambda: clear_draft()).props('flat color=negative')

        # --- Last auto-fill result ---------------------------------------
        panel_container = ui.column().classes('full-width')

        @ui.refreshable
        async def result_panel() -> None:
            run = state['last_run']
            if not run:
                return
            policy = run.get('policy')
            open_slots = sum(u['open'] for u in run['unfilled'])
            header = (f"Draft: {run['created']} assigned · {open_slots} slot(s) open "
                      f"· pool of {run['pool_size']}")
            if policy is not None and policy.max_hours:
                header += f" · max {policy.max_hours:g} h/volunteer"

            def dismiss() -> None:
                state['last_run'] = None
                result_panel.refresh()

            with ui.card().classes('full-width q-pa-sm'):
                with ui.row().classes('items-center gap-2 full-width').style('flex-wrap: wrap;'):
                    ui.label(header).classes('text-body2 text-weight-medium')
                    ui.space()
                    ui.button(icon='close', on_click=dismiss) \
                        .props('flat dense round').tooltip('Dismiss this summary')

                if run['unfilled']:
                    ui.label('Open slots').classes('text-caption text-weight-medium q-mt-sm')
                    for row in run['unfilled']:
                        with ui.row().classes('items-center gap-2 full-width') \
                                .style('flex-wrap: wrap;'):
                            ui.label(_slot_title(row)).classes('text-caption')
                            ui.badge(f"{row['open']} open", color='warning')
                            ui.label(row['reason']).classes('text-caption text-grey')
                            ui.space()
                            ui.button('Assign',
                                      on_click=lambda r=row: assign_from_panel(r['shift_id'])) \
                                .props('flat dense color=primary')

                if run.get('outside_availability'):
                    ui.label('Placed outside stated availability') \
                        .classes('text-caption text-weight-medium q-mt-sm')
                    for row in run['outside_availability']:
                        with ui.row().classes('items-center gap-2 full-width') \
                                .style('flex-wrap: wrap;'):
                            ui.label(
                                f"{row['name']} — {_slot_title(row)}"
                            ).classes('text-caption')
                            ui.space()
                            ui.button('Remove',
                                      on_click=lambda r=row: remove_from_panel(r)) \
                                .props('flat dense color=negative')

                if run.get('heavy_loads'):
                    ui.label('Heavy loads').classes('text-caption text-weight-medium q-mt-sm')
                    for row in run['heavy_loads']:
                        ui.label(
                            f"{row['name']} — {row['hours']:g} h across "
                            f"{row['shifts']} shift(s)"
                        ).classes('text-caption text-grey')

        def _slot_title(row) -> str:
            label = f" — {row['label']}" if row.get('label') else ''
            return (f"{row['position']}{label}   "
                    f"{format_local_time(row['starts_at'])} ET")

        async def assign_from_panel(shift_id: int) -> None:
            shift = await schedule_service.get_shift(shift_id)
            if shift is None:
                ui.notify('That shift no longer exists.', color='warning')
                return
            await open_assign_dialog(shift)

        async def remove_from_panel(row) -> None:
            assignment = await schedule_service.find_assignment(
                row['shift_id'], row['user_id'],
            )
            if assignment is None:
                ui.notify('That assignment is already gone.', color='info')
            else:
                try:
                    await schedule_service.unassign(actor, assignment)
                    ui.notify(f"Removed {row['name']}.", color='info')
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
            state['last_run']['outside_availability'] = [
                r for r in state['last_run']['outside_availability']
                if not (r['shift_id'] == row['shift_id'] and r['user_id'] == row['user_id'])
            ]
            refresh_all()

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
                pos_shifts = sorted(
                    by_position.get(position.id, []), key=lambda s: s.starts_at,
                )
                open_slots = sum(
                    max(0, s.slots_needed - len(s.assignments)) for s in pos_shifts
                )
                filled = sum(len(s.assignments) for s in pos_shifts)
                needed = sum(s.slots_needed for s in pos_shifts)
                with ui.card().classes('full-width q-pa-sm q-mb-sm'):
                    # The header always states the position's state, so a collapsed
                    # position hides finished work and never hidden work. The action
                    # buttons stay outside the expansion: they are how an empty day
                    # gets populated.
                    with ui.row().classes('items-center justify-between full-width'):
                        with ui.column().classes('gap-0'):
                            with ui.row().classes('items-center gap-2'):
                                ui.label(position.name).classes('text-subtitle1')
                                if pos_shifts:
                                    ui.badge(f'{filled}/{needed}',
                                             color='warning' if open_slots else 'positive')
                                    if open_slots:
                                        ui.label(f'{open_slots} open') \
                                            .classes('text-caption text-warning')
                            if position.description:
                                ui.label(position.description).classes('text-caption text-grey')
                        with ui.row().classes('gap-1'):
                            ui.button('Generate standard shifts', icon='auto_awesome_motion',
                                      on_click=lambda p=position: generate_shifts(p)) \
                                .props('flat dense color=primary')
                            ui.button('Add shift', icon='add',
                                      on_click=lambda p=position: open_shift_dialog(position=p)) \
                                .props('flat dense color=primary')
                    if not pos_shifts:
                        ui.label('No shifts for this day yet.').classes('italic-note q-pa-sm')
                        continue
                    # A fully-staffed position folds away — on phones only, where
                    # 5.8 screenfuls of finished work is the finding. The fold is a
                    # class our own stylesheet only honours below `md`, so the
                    # cards render once and the desktop layout is provably
                    # untouched; a `ui.expansion` per width would double the DOM
                    # and register every row action twice.
                    folded = not open_slots and not state['folds'].get(position.id)
                    if not open_slots:
                        with ui.row().classes('items-center lt-md q-pt-xs'):
                            ui.button(
                                f"{'Show' if folded else 'Hide'} {len(pos_shifts)} shift(s)",
                                icon='expand_more' if folded else 'expand_less',
                                on_click=lambda p=position: toggle_fold(p.id),
                            ).props('flat dense color=primary')
                    classes = 'gap-2 items-stretch'
                    if folded:
                        classes += ' wiz-position-folded'
                    with ui.row().classes(classes).style('flex-wrap: wrap;'):
                        for shift in pos_shifts:
                            _render_shift_card(shift)

        def toggle_fold(position_id: int) -> None:
            state['folds'][position_id] = not state['folds'].get(position_id)
            grid.refresh()

        def _last_run_reason(shift_id: int):
            """Why the last auto-fill left this shift short, so the grid and the
            summary panel agree without the coordinator holding the mapping."""
            run = state['last_run']
            if not run:
                return None
            return next((u['reason'] for u in run['unfilled']
                         if u['shift_id'] == shift_id), None)

        def _render_shift_card(shift) -> None:
            filled = len(shift.assignments)
            understaffed = filled < shift.slots_needed
            with ui.card().classes('q-pa-sm').style('min-width: 220px; flex: 0 0 auto;'):
                header = shift.label or f'{format_local_time(shift.starts_at)}'
                with ui.row().classes('items-center justify-between full-width'):
                    ui.label(header).classes('text-weight-medium')
                    badge = ui.badge(f'{filled}/{shift.slots_needed}',
                                     color='warning' if understaffed else 'positive')
                    reason = _last_run_reason(shift.id)
                    if understaffed and reason:
                        badge.tooltip(reason)
                    if shift.notes:
                        # The notes field is write-only otherwise; the volunteer
                        # reads it on their card, the coordinator could not.
                        ui.icon('sticky_note_2', size='xs').tooltip(shift.notes)
                ui.label(
                    f'{format_local_time(shift.starts_at)}–{format_local_time(shift.ends_at)} ET'
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
                    chip.props('outline color=secondary') \
                        .tooltip('Draft — this volunteer has not been told')
                elif assignment.acknowledged_at:
                    chip.props('color=positive')

                async def remove(a=assignment) -> None:
                    try:
                        await schedule_service.unassign(actor, a)
                        ui.notify('Removed assignment.', color='info')
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                    finally:
                        # The chip already removed itself client-side; refresh to
                        # re-sync regardless of whether the service call succeeded.
                        refresh_all()
                chip.on('remove', lambda a=assignment: remove(a))

                if assignment.checked_in_at:
                    ui.icon('how_to_reg', color='teal', size='sm').tooltip('Checked in')
                else:
                    async def do_check_in(a_id=assignment.id) -> None:
                        try:
                            await schedule_service.check_in(a_id, actor)
                            ui.notify('Volunteer checked in.', color='positive')
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                        refresh_all()
                    ui.button(icon='login', on_click=do_check_in) \
                        .props('flat dense color=teal').tooltip('Check in volunteer')

        # --- Assignment picker ------------------------------------------
        async def open_assign_dialog(shift) -> None:
            pool = await profile_service.assignable_volunteers()
            avail_map = await availability_service.availability_map(
                [u.id for u in pool], shift.starts_at, shift.ends_at,
            )
            assigned_ids = {a.user_id for a in shift.assignments}
            qualified_ids = await qualification_service.get_qualified_user_ids_for_position(shift.position_id)
            # If no qualifications are defined for this position, treat everyone as eligible.
            has_qualifications = bool(qualified_ids)
            picker_state = {'show_all': not has_qualifications}

            with ui.dialog() as dialog, ui.card().classes('dialog-card'):
                title = shift.position.name if shift.position else 'Shift'
                ui.label(f'Assign to {title} '
                         f'({format_local_time(shift.starts_at)}–{format_local_time(shift.ends_at)} ET)') \
                    .classes('text-subtitle1 q-pa-sm')
                ui.separator()
                if not pool:
                    ui.label('No volunteers in pool. Users must have the Volunteer role assigned.') \
                        .classes('italic-note q-pa-md')

                if has_qualifications:
                    with ui.row().classes('items-center q-px-sm q-pt-xs'):
                        def on_show_all_change(e) -> None:
                            picker_state['show_all'] = e.value
                            picker_list.refresh()
                        ui.checkbox('Show unqualified volunteers', value=False,
                                    on_change=on_show_all_change)

                @ui.refreshable
                def picker_list() -> None:
                    visible = [v for v in pool if v.id not in assigned_ids]
                    if not picker_state['show_all']:
                        visible = [v for v in visible if v.id in qualified_ids]
                    with ui.column().classes('q-pa-sm gap-1').style('max-height: 50vh; overflow-y: auto;'):
                        if not visible:
                            ui.label('No qualified volunteers available.').classes('italic-note')
                        for volunteer in visible:
                            is_qualified = volunteer.id in qualified_ids
                            status = VolunteerAvailabilityService.covers(
                                avail_map.get(volunteer.id, []), shift.starts_at, shift.ends_at,
                            )
                            _render_picker_row(
                                dialog, shift, volunteer, status,
                                show_qualification=picker_state['show_all'] and has_qualifications,
                                is_qualified=is_qualified,
                            )

                picker_list()

                with ui.row().classes('justify-end q-pa-sm'):
                    ui.button('Close', on_click=dialog.close).props('flat')
                dialog.open()

        def _render_picker_row(
            dialog, shift, volunteer, status,
            show_qualification: bool = False,
            is_qualified: bool = True,
        ) -> None:
            with ui.row().classes('items-center justify-between full-width'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(volunteer.preferred_name)
                    if show_qualification:
                        if is_qualified:
                            ui.badge('Qualified', color='primary')
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
                        notify_error(e)
                        return
                    for w in warnings:
                        ui.notify(w, color='warning')
                    ui.notify(f'Assigned {u.preferred_name}.', color='positive')
                    dialog.close()
                    refresh_all()
                ui.button('Assign', on_click=do_assign).props('dense flat color=primary')

        # --- Actions -----------------------------------------------------
        async def generate_shifts(position) -> None:
            try:
                await schedule_service.generate_day_shifts(
                    actor, state['day'], [position.id], STANDARD_BLOCKS,
                )
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify(f'Generated shifts for {position.name} (staggered where configured).',
                      color='positive')
            refresh_all()

        async def open_shift_dialog(shift=None, position=None) -> None:
            async def after(_):
                refresh_all()
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
                    notify_error(e)
                    return
                ui.notify('Shift deleted.', color='info')
                refresh_all()

            confirm = ConfirmationDialog(message=message, on_confirm=on_confirm, confirm_text='Delete')
            confirm.open()

        async def auto_fill() -> None:
            positions = await position_service.list_active()
            await VolunteerAutofillDialog(positions, on_submit=run_auto_fill).open()

        async def run_auto_fill(policy, position_ids) -> None:
            win_start, win_end = _day_window(state['day'])
            try:
                result = await autoschedule_service.generate_draft(
                    actor, win_start, win_end,
                    position_ids=position_ids, policy=policy,
                )
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            state['last_run'] = result
            ui.notify(
                'Draft created — see the summary below.',
                color='positive' if result['created'] else 'warning',
            )
            refresh_all()

        async def clear_draft() -> None:
            win_start, win_end = _day_window(state['day'])
            try:
                removed = await autoschedule_service.clear_draft(actor, win_start, win_end)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify(f'Cleared {removed} draft assignment(s).', color='info')
            refresh_all()

        async def confirm_publish(pending: int) -> None:
            async def on_confirm() -> None:
                confirm.dialog.close()
                win_start, win_end = _day_window(state['day'])
                try:
                    result = await autoschedule_service.publish_draft(actor, win_start, win_end)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify(
                    f"Published {result['published']} assignment(s) to "
                    f"{result['volunteers']} volunteer(s). Each got a Discord DM.",
                    color='positive',
                )
                refresh_all()

            confirm = ConfirmationDialog(
                message=(f'Publish {pending} draft assignment(s)? Each volunteer gets a '
                         'Discord DM asking them to acknowledge. This cannot be undone — '
                         'removing an assignment afterwards notifies them again.'),
                on_confirm=on_confirm, confirm_text='Publish & notify',
            )
            confirm.open()

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
                            notify_error(e)
                            return
                        ui.notify(f'Deleted {deleted} shift(s) and all assignments.', color='negative')
                        refresh_all()

                ui.separator()
                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    ui.button('Delete everything', on_click=do_reset).props('color=negative')
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
                                    refresh_all()
                                await VolunteerPositionDialog(position=p, on_submit=after).open()
                            ui.button(icon='edit', on_click=edit).props('flat dense')

                with ui.column().classes('q-pa-sm gap-1').style('max-height: 50vh; overflow-y: auto;'):
                    await position_list()

                async def add_position() -> None:
                    async def after(_):
                        position_list.refresh()
                        refresh_all()
                    await VolunteerPositionDialog(on_submit=after).open()

                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Add position', icon='add', on_click=add_position).props('flat color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')
                dialog.open()

        with strip_container:
            await coverage_strip()
        with banner_container:
            await draft_banner()
        with panel_container:
            await result_panel()
        with grid_container:
            await grid()
