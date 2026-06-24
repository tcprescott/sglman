"""Admin Volunteer Roster page — view availability and manage qualifications."""

from nicegui import ui

from application.repositories.volunteer_qualification_repository import VolunteerQualificationRepository
from application.repositories.volunteer_profile_repository import VolunteerProfileRepository
from application.services import AuthService, current_user_from_storage
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_position_service import VolunteerPositionService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.utils.timezone import format_eastern_date, format_eastern_time
from models import VolunteerAvailabilityStatus
from theme.dialog.volunteer_profile_dialog import VolunteerProfileDialog

_STATUS_LABEL = {
    VolunteerAvailabilityStatus.PREFERRED: ('Preferred', 'positive'),
    VolunteerAvailabilityStatus.AVAILABLE: ('Available', 'positive'),
    VolunteerAvailabilityStatus.UNAVAILABLE: ('Unavailable', 'negative'),
}


async def admin_volunteer_roster_page() -> None:
    actor = await current_user_from_storage()
    if not await AuthService.can_manage_volunteers(actor):
        ui.label('You do not have permission to manage volunteers.').classes('text-error')
        return

    profile_service = VolunteerProfileService()
    position_service = VolunteerPositionService()
    availability_service = VolunteerAvailabilityService()
    qual_repo = VolunteerQualificationRepository()
    profile_repo = VolunteerProfileRepository()

    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            ui.label('Volunteer Roster').classes('page-title')
        ui.separator().classes('separator-spacing')

        @ui.refreshable
        async def roster() -> None:
            volunteers = await profile_service.assignable_volunteers()
            if not volunteers:
                ui.label('No volunteers in pool yet.').classes('italic-note')
                return

            positions = await position_service.list_all()
            position_by_id = {p.id: p for p in positions}

            opted_in_ids = set(await profile_repo.opted_in_user_ids())

            all_quals = await qual_repo.list_all()
            qual_map: dict[int, set[int]] = {}
            for q in all_quals:
                qual_map.setdefault(q.user_id, set()).add(q.position_id)

            avail_ids = [u.id for u in volunteers]
            avail_rows = await VolunteerAvailabilityService().availability_map(
                avail_ids, *_wide_window(),
            )

            with ui.column().classes('full-width gap-2'):
                for volunteer in volunteers:
                    vol_qual_ids = qual_map.get(volunteer.id, set())
                    vol_windows = avail_rows.get(volunteer.id, [])
                    opted_in = volunteer.id in opted_in_ids

                    with ui.card().classes('full-width q-pa-sm'):
                        with ui.row().classes('items-start justify-between full-width no-wrap gap-4'):

                            # Left: name + opt-in badge + qualifications
                            with ui.column().classes('gap-1'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.label(volunteer.preferred_name).classes('text-subtitle2')
                                    if opted_in:
                                        ui.badge('Opted in', color='positive').props('outline')
                                    else:
                                        ui.badge('Not opted in', color='grey').props('outline')

                                # Qualification chips
                                if vol_qual_ids:
                                    with ui.row().classes('gap-1 items-center flex-wrap'):
                                        for pid in sorted(vol_qual_ids):
                                            pos = position_by_id.get(pid)
                                            if pos:
                                                ui.chip(pos.name).props('dense outline color=primary')
                                else:
                                    ui.label('No qualifications set').classes('text-caption text-grey')

                                # Availability summary
                                if vol_windows:
                                    with ui.column().classes('gap-0'):
                                        for w in sorted(vol_windows, key=lambda x: x.starts_at):
                                            label_text, badge_color = _STATUS_LABEL.get(
                                                w.status, (str(w.status), 'grey'),
                                            )
                                            date_str = format_eastern_date(w.starts_at)
                                            start_str = format_eastern_time(w.starts_at)
                                            end_str = format_eastern_time(w.ends_at)
                                            with ui.row().classes('items-center gap-1 no-wrap'):
                                                ui.badge(label_text, color=badge_color).props('dense')
                                                ui.label(
                                                    f'{date_str}  {start_str}–{end_str} ET'
                                                ).classes('text-caption')
                                else:
                                    ui.label('No availability declared').classes('text-caption text-grey')

                            # Right: edit button
                            async def open_profile(u=volunteer) -> None:
                                active_positions = await position_service.list_active()
                                await VolunteerProfileDialog(
                                    user=u,
                                    positions=active_positions,
                                    on_submit=lambda: roster.refresh(),
                                ).open()

                            ui.button(icon='manage_accounts', on_click=open_profile) \
                                .props('flat dense').tooltip('View availability & qualifications')

        await roster()


def _wide_window():
    """A wide enough window to catch any declared availability."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    return now - timedelta(days=365), now + timedelta(days=365)
