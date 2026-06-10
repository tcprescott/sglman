"""Player Availability Page (self-service for any logged-in player)."""

from datetime import timedelta

from nicegui import app, ui
from middleware.auth import protected_page

from application.services import SystemConfigService, current_user_from_storage
from application.services.player_availability_service import PlayerAvailabilityService
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_time,
    parse_eastern_datetime,
    to_eastern,
)
from models import VolunteerAvailabilityStatus
from theme.base import BaseLayout


_STATUS_OPTIONS = {
    VolunteerAvailabilityStatus.PREFERRED.value: 'Preferred',
    VolunteerAvailabilityStatus.AVAILABLE.value: 'Available',
    VolunteerAvailabilityStatus.UNAVAILABLE.value: 'Unavailable',
}


def create() -> None:
    @protected_page('/availability')
    async def availability_page(tab: str = None) -> None:
        ui.page_title('Speedgaming Live Onsite - My Availability')
        discord_id = app.storage.user.get('discord_id', None)
        from models import User
        from application.services import AuthService
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.row():
                ui.label('You must be logged in to view this page.').classes('text-error')
            return

        show_admin = await AuthService.can_view_admin(user)
        show_volunteer = await AuthService.is_volunteer(user)

        async def render_content():
            await _availability_content(user)

        tabs = [
            {'label': 'My Availability', 'icon': 'event_available', 'content': render_content},
        ]
        await BaseLayout(
            tabs=tabs, default_tab=tab, page_name='availability', user=user,
            show_admin=show_admin, show_volunteer=show_volunteer,
        ).render()


async def _availability_content(user) -> None:
    service = PlayerAvailabilityService()

    event_start, event_end = await SystemConfigService.get_event_window()
    existing = await service.availability_for(user)

    rows: list[dict] = [
        {
            'date': format_eastern_date(w.starts_at),
            'start': format_eastern_time(w.starts_at),
            'end': format_eastern_time(to_eastern(w.ends_at)),
            'status': w.status.value if hasattr(w.status, 'value') else str(w.status),
        }
        for w in existing
    ]

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('My Availability').classes('page-title')
        ui.separator().classes('separator-spacing')
        ui.label(
            f'Event window: {format_eastern_date(event_start)} → {format_eastern_date(event_end)} '
            '(US/Eastern). Add the windows when you can play.'
        ).classes('italic-note')

        @ui.refreshable
        def window_rows() -> None:
            if not rows:
                ui.label('No availability windows yet. Add one below.').classes('italic-note')
            for row in rows:
                with ui.row().classes('items-center gap-2 q-mb-xs'):
                    ui.input('Date', value=row['date']) \
                        .props('type=date dense').bind_value(row, 'date')
                    ui.input('Start', value=row['start']) \
                        .props('type=time dense').bind_value(row, 'start')
                    ui.input('End', value=row['end']) \
                        .props('type=time dense').bind_value(row, 'end')
                    ui.select(_STATUS_OPTIONS, value=row['status']) \
                        .props('dense').bind_value(row, 'status').classes('w-40')
                    ui.button(icon='delete', on_click=lambda r=row: _remove(r)) \
                        .props('flat dense color=negative')

        def _remove(row: dict) -> None:
            rows.remove(row)
            window_rows.refresh()

        def _add() -> None:
            rows.append({
                'date': format_eastern_date(event_start),
                'start': '09:00',
                'end': '13:00',
                'status': VolunteerAvailabilityStatus.AVAILABLE.value,
            })
            window_rows.refresh()

        window_rows()

        async def save() -> None:
            windows = []
            try:
                for row in rows:
                    if not row['date'] or not row['start'] or not row['end']:
                        raise ValueError('Every window needs a date, start, and end.')
                    starts_at = parse_eastern_datetime(row['date'], row['start'])
                    ends_at = parse_eastern_datetime(row['date'], row['end'])
                    if ends_at <= starts_at:
                        ends_at = ends_at + timedelta(days=1)
                    status = VolunteerAvailabilityStatus(row['status'])
                    windows.append((starts_at, ends_at, status, None))
                await service.set_windows(user, windows)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Availability saved.', color='positive')

        with ui.row().classes('q-mt-md gap-2'):
            ui.button('Add window', icon='add', on_click=_add).props('flat color=primary')
            ui.button('Save availability', icon='save', on_click=save).props('color=primary')
