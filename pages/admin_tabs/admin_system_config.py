"""Admin System Configuration Page"""

from datetime import date

from nicegui import app, ui

from application.services import (
    AuthService,
    StationService,
    SystemConfigService,
    TimezoneService,
    get_user_from_discord_id,
)
from application.services.system_config_service import (
    KEY_EVENT_END_DATE,
    KEY_EVENT_START_DATE,
    KEY_MAX_CONCURRENT_PLAYERS,
    KEY_MAX_CONCURRENT_STAGES,
    KEY_STATION_FORMAT,
    KEY_VOLUNTEER_COMP_TIERS,
    KEY_VOLUNTEER_REMINDER_LEAD_MINUTES,
)
from application.utils.timezone import timezone_label
from models import StationFormat
from theme.dialog._helpers import native_date_input, native_time_input
from theme.notify import notify_error


def _format_hours(value: float) -> str:
    """Render an hour threshold without a pointless ``.0``."""
    return str(int(value)) if float(value).is_integer() else f'{value:g}'


def _validate_comp_tiers(raw: str | None) -> str:
    """Normalize the comma-separated tier list, or explain what is wrong.

    Blank is stored blank, which the getter reads as "use the default" — the
    admin who clears the box gets 8/12/16 back rather than nothing.
    """
    text = (raw or '').strip()
    if not text:
        return ''
    values: list[float] = []
    for token in text.split(','):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            raise ValueError('Comp tiers must be numbers of hours, separated by commas.') from None
        if value < 0:
            raise ValueError('Comp tiers cannot be negative.')
        values.append(value)
    return ', '.join(_format_hours(v) for v in sorted(set(values)))


def _date_field(label: str, value: str):
    # Native date picker (YYYY-MM-DD) — OS calendar on mobile, shared recipe.
    return native_date_input(label, value, clearable=True)


async def _station_pool_section(can_edit: bool) -> None:
    """The venue's station pool, beneath the format control it belongs with.

    A community with no stations keeps the historical free-text station field, so
    an empty pool is a valid state rather than a setup step.
    """
    service = StationService()

    async def _actor():
        return await get_user_from_discord_id(app.storage.user.get('discord_id'))

    @ui.refreshable
    async def station_list() -> None:
        stations = await service.list_stations()
        if not stations:
            ui.label(
                'No stations defined. Proctors type the station by hand; add '
                'stations here to pick from a list and block double-booking.'
            ).classes('text-caption text-grey')
            return
        for station in stations:
            with ui.row().classes('items-center gap-3 q-mb-xs full-width'):
                ui.label(station.name).classes('w-16 text-weight-medium')
                ui.label(station.section or '—').classes('col text-caption text-grey')

                async def toggle(_e, s=station) -> None:
                    try:
                        await service.update_station(
                            s.id, await _actor(), is_active=not s.is_active,
                        )
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                    station_list.refresh()

                async def remove(_e, s=station) -> None:
                    try:
                        await service.delete_station(s.id, await _actor())
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                    station_list.refresh()

                ui.switch(
                    'Active', value=station.is_active, on_change=toggle,
                ).props('dense').set_enabled(can_edit)
                ui.button(icon='delete', on_click=remove).props(
                    'flat dense color=negative'
                ).set_enabled(can_edit)

    ui.separator().classes('separator-spacing')
    ui.label('Station Pool').classes('section-title q-mt-md')
    ui.label(
        'The physical stations in your venue. Once any station exists, proctors '
        'pick from this list and a station in use by a live match cannot be '
        'assigned again. Deactivate rather than delete to keep past matches readable.'
    ).classes('text-caption text-grey')

    with ui.column().classes('gap-1 full-width q-mt-sm'):
        await station_list()

    if not can_edit:
        return

    with ui.row().classes('items-center gap-3 q-mt-sm'):
        name_input = ui.input('Name').props('outlined dense maxlength=50').classes('w-32')
        section_input = ui.input('Section').props('outlined dense maxlength=50').classes('w-40')
        order_input = ui.number('Order', value=0, format='%d').props('outlined dense').classes('w-24')

        async def add() -> None:
            try:
                await service.create_station(
                    name_input.value or '',
                    await _actor(),
                    section=section_input.value or None,
                    sort_order=int(order_input.value or 0),
                )
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            name_input.value = ''
            section_input.value = ''
            station_list.refresh()

        ui.button('Add Station', icon='add', on_click=add).props('color=primary')


async def admin_system_config_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_edit = await AuthService.is_staff(actor)

    start_date = await SystemConfigService.get_date(KEY_EVENT_START_DATE)
    end_date = await SystemConfigService.get_date(KEY_EVENT_END_DATE)
    max_players = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_PLAYERS)
    max_stages = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_STAGES)
    reminder_lead = await SystemConfigService.get_int(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES)
    comp_tiers = await SystemConfigService.get_volunteer_comp_tiers()
    station_format = await SystemConfigService.get_station_format()
    tournament_hours = await SystemConfigService.get_tournament_hours()
    event_start, event_end = await SystemConfigService.get_event_window()
    # Operating hours are the community's rule, so they are written and enforced
    # on the community's clock — never the admin's. Labelled with that zone so an
    # admin abroad is not silently reading the numbers as their own local time.
    tenant_tz = await TimezoneService.tenant_timezone_name()
    tenant_tz_label = timezone_label(tenant_tz)

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('System Configuration').classes('page-title')

        ui.separator().classes('separator-spacing')

        with ui.column().classes('wiz-form-column gap-4'):
            start_input = _date_field('Event Start Date', start_date.isoformat() if start_date else '')
            end_input = _date_field('Event End Date', end_date.isoformat() if end_date else '')
            ui.label('Leave blank to derive the event window from scheduled match times.').classes('text-caption text-grey')

            players_input = ui.number(
                'Max Concurrent Players', value=max_players, min=1, format='%d',
            ).classes('w-full')
            ui.label('Blank uses the default of 60.').classes('text-caption text-grey')

            stages_input = ui.number(
                'Max Concurrent Stages', value=max_stages, min=1, format='%d',
            ).classes('w-full')
            ui.label('Blank defaults to the number of active stream rooms.').classes('text-caption text-grey')

            reminder_lead_input = ui.number(
                'Volunteer Reminder Lead (minutes)', value=reminder_lead, min=1, format='%d',
            ).classes('w-full')
            ui.label('How far ahead of a shift to DM volunteers. Blank uses 60 minutes.').classes('text-caption text-grey')

            comp_tiers_input = ui.input(
                'Volunteer Comp Tiers (hours)',
                value=', '.join(_format_hours(t) for t in comp_tiers),
            ).classes('w-full')
            ui.label(
                'Hour totals that earn a volunteer something, separated by commas. '
                'Blank uses 8, 12, 16. Enter 0 if your community awards nothing by hours.'
            ).classes('text-caption text-grey')

            station_format_input = ui.select(
                options={
                    StationFormat.FREE.value: 'Free text (no validation)',
                    StationFormat.NUMERIC.value: 'Numeric only (1, 2, 3…)',
                    StationFormat.STRUCTURED.value: 'Structured ID (A1, B12)',
                    StationFormat.ALPHANUMERIC.value: 'Alphanumeric (letters, numbers, hyphens)',
                },
                value=station_format.value,
                label='Station Assignment Format',
            ).classes('w-full')
            ui.label('Controls the format enforced when assigning stations to match players.').classes('text-caption text-grey')

        await _station_pool_section(can_edit)

        # --- Per-day tournament hours ---
        from datetime import timedelta

        ui.separator().classes('separator-spacing')
        ui.label('Tournament Hours').classes('section-title q-mt-md')
        ui.label(
            'Set the window during which matches may start each day. '
            f'Matches cannot be scheduled outside these hours, given in {tenant_tz_label} — '
            f'the community\'s own timezone, so the rule means the same thing for '
            f'everyone. Leave a day blank to allow any time.'
        ).classes('text-caption text-grey')

        hours_inputs: dict[date, dict] = {}
        current = event_start
        while current <= event_end:
            window = tournament_hours.get(current)
            open_val = window[0].strftime('%H:%M') if window else ''
            close_val = window[1].strftime('%H:%M') if window else ''
            with ui.row().classes('items-center gap-3 q-mb-xs'):
                ui.label(current.isoformat()).classes('w-28 text-mono')
                open_input = native_time_input(
                    'Open', open_val, dense=True, stack_label=False, show_timezone=False,
                ).classes('w-28')
                close_input = native_time_input(
                    'Close', close_val, dense=True, stack_label=False, show_timezone=False,
                ).classes('w-28')
                hours_inputs[current] = {'open': open_input, 'close': close_input}
            current += timedelta(days=1)

        # --- Discord role sync ---
        ui.separator().classes('separator-spacing')
        ui.label('Discord Role Sync').classes('section-title q-mt-md')
        ui.label(
            'Connect a Discord server and configure role mappings on the '
            'Discord Roles tab. Connecting verifies you manage that server.'
        ).classes('text-caption text-grey')

        async def save():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            try:
                start_raw = (start_input.value or '').strip()
                end_raw = (end_input.value or '').strip()
                for label, raw in (('start', start_raw), ('end', end_raw)):
                    if raw:
                        try:
                            date.fromisoformat(raw)
                        except ValueError:
                            raise ValueError(f'Event {label} date must be in YYYY-MM-DD format.') from None

                def int_str(value) -> str:
                    if value is None or value == '':
                        return ''
                    ivalue = int(value)
                    if ivalue < 1:
                        raise ValueError('Concurrency limits must be at least 1.')
                    return str(ivalue)

                players_raw = int_str(players_input.value)
                stages_raw = int_str(stages_input.value)
                reminder_raw = int_str(reminder_lead_input.value)
                tiers_raw = _validate_comp_tiers(comp_tiers_input.value)

                # Build per-day tournament hours mapping
                hours_mapping: dict[date, tuple[str, str]] = {}
                for d, fields in hours_inputs.items():
                    open_str = (fields['open'].value or '').strip()
                    close_str = (fields['close'].value or '').strip()
                    if open_str and close_str:
                        hours_mapping[d] = (open_str, close_str)

                await SystemConfigService.set_raw(KEY_EVENT_START_DATE, start_raw, actor)
                await SystemConfigService.set_raw(KEY_EVENT_END_DATE, end_raw, actor)
                await SystemConfigService.set_raw(KEY_MAX_CONCURRENT_PLAYERS, players_raw, actor)
                await SystemConfigService.set_raw(KEY_MAX_CONCURRENT_STAGES, stages_raw, actor)
                await SystemConfigService.set_raw(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES, reminder_raw, actor)
                await SystemConfigService.set_raw(KEY_VOLUNTEER_COMP_TIERS, tiers_raw, actor)
                await SystemConfigService.set_raw(KEY_STATION_FORMAT, station_format_input.value or StationFormat.FREE.value, actor)
                await SystemConfigService.set_tournament_hours(hours_mapping, actor)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Settings saved', color='positive')

        if can_edit:
            ui.button('Save', icon='save', on_click=save).props('color=primary').classes('mt-2')
