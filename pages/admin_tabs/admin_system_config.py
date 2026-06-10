"""Admin System Configuration Page"""

from datetime import date

from nicegui import ui

from application.services import AuthService, SystemConfigService, current_user_from_storage
from application.services.system_config_service import (
    KEY_EVENT_END_DATE,
    KEY_EVENT_START_DATE,
    KEY_MAX_CONCURRENT_PLAYERS,
    KEY_MAX_CONCURRENT_STAGES,
)


def _date_field(label: str, value: str):
    with ui.input(label, value=value).props('clearable') as field:
        with ui.menu().props('no-parent-event') as menu:
            with ui.column().classes('items-center'):
                ui.date().bind_value(field)
                ui.button('Close', on_click=menu.close).props('flat')
        with field.add_slot('append'):
            ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')
    return field


async def admin_system_config_page() -> None:
    actor = await current_user_from_storage()
    can_edit = await AuthService.is_staff(actor)

    start_date = await SystemConfigService.get_date(KEY_EVENT_START_DATE)
    end_date = await SystemConfigService.get_date(KEY_EVENT_END_DATE)
    max_players = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_PLAYERS)
    max_stages = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_STAGES)

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('System Configuration').classes('page-title')

        ui.separator().classes('separator-spacing')

        with ui.column().classes('w-full gap-4'):
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

        async def save():
            actor = await current_user_from_storage()
            try:
                start_raw = (start_input.value or '').strip()
                end_raw = (end_input.value or '').strip()
                for label, raw in (('start', start_raw), ('end', end_raw)):
                    if raw:
                        try:
                            date.fromisoformat(raw)
                        except ValueError:
                            raise ValueError(f'Event {label} date must be in YYYY-MM-DD format.')

                def int_str(value) -> str:
                    if value is None or value == '':
                        return ''
                    ivalue = int(value)
                    if ivalue < 1:
                        raise ValueError('Concurrency limits must be at least 1.')
                    return str(ivalue)

                players_raw = int_str(players_input.value)
                stages_raw = int_str(stages_input.value)

                await SystemConfigService.set_raw(KEY_EVENT_START_DATE, start_raw, actor)
                await SystemConfigService.set_raw(KEY_EVENT_END_DATE, end_raw, actor)
                await SystemConfigService.set_raw(KEY_MAX_CONCURRENT_PLAYERS, players_raw, actor)
                await SystemConfigService.set_raw(KEY_MAX_CONCURRENT_STAGES, stages_raw, actor)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Settings saved', color='positive')

        if can_edit:
            ui.button('Save', icon='save', on_click=save).props('color=primary').classes('mt-2')
