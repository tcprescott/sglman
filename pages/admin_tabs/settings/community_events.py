"""Settings → Community Events: when subscribers hear about an event starting."""

from nicegui import ui

from application.services import SystemConfigService
from application.services.system_config_service import KEY_COMMUNITY_EVENT_REMINDER_LEAD_MINUTES
from pages.admin_tabs.settings._common import current_actor, field_hint, positive_int_or_blank
from theme.notify import notify_error
from theme.save_footer import SaveFooter
from theme.section import section_panel


async def community_events_settings_pane(can_edit: bool) -> None:
    lead = await SystemConfigService.get_int(KEY_COMMUNITY_EVENT_REMINDER_LEAD_MINUTES)

    card = await section_panel(
        'Reminders', icon='notifications',
        subtitle='How early subscribers get a DM before a community event starts.',
    )
    with card.body:
        with ui.column().classes('gap-1'):
            lead_input = ui.number('Reminder lead (minutes)', value=lead, min=1, format='%d').classes('w-56')
            field_hint('How long before an event its subscribers get a DM. Blank uses 30.')

    async def save() -> bool:
        try:
            raw = positive_int_or_blank(lead_input.value, 'The reminder lead')
            await SystemConfigService.set_raw(KEY_COMMUNITY_EVENT_REMINDER_LEAD_MINUTES, raw, await current_actor())
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return False
        ui.notify('Community event settings saved', color='positive')
        return True

    with card.panel:
        SaveFooter(save, enabled=can_edit).watch(lead_input)
    if not can_edit:
        lead_input.disable()
