"""Settings → Volunteers: shift reminders and the hour totals that earn rewards."""

from nicegui import ui

from application.services import SystemConfigService
from application.services.system_config_service import (
    KEY_VOLUNTEER_COMP_TIERS,
    KEY_VOLUNTEER_REMINDER_LEAD_MINUTES,
)
from pages.admin_tabs.settings._common import current_actor, field_hint, positive_int_or_blank
from theme.notify import notify_error
from theme.save_footer import SaveFooter
from theme.section import section_panel


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


async def volunteers_settings_pane(can_edit: bool) -> None:
    reminder_lead = await SystemConfigService.get_int(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES)
    comp_tiers = await SystemConfigService.get_volunteer_comp_tiers()

    card = await section_panel(
        'Shifts', icon='volunteer_activism',
        subtitle='When volunteers hear about their next shift, and what their hours add up to.',
    )
    with card.body:
        with ui.column().classes('gap-1'):
            reminder_input = ui.number(
                'Reminder lead (minutes)', value=reminder_lead, min=1, format='%d',
            ).classes('w-56')
            field_hint('How long before a shift its volunteers get a DM. Blank uses 60.')
        with ui.column().classes('gap-1 w-full'):
            tiers_input = ui.input(
                'Reward tiers (hours)', value=', '.join(_format_hours(t) for t in comp_tiers),
            ).classes('w-72')
            field_hint(
                'Hour totals that earn a volunteer something, separated by commas. '
                'Blank uses 8, 12, 16. Enter 0 if your community awards nothing by hours.'
            )

    async def save() -> bool:
        try:
            reminder_raw = positive_int_or_blank(reminder_input.value, 'The reminder lead')
            tiers_raw = _validate_comp_tiers(tiers_input.value)
            actor = await current_actor()
            await SystemConfigService.set_raw(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES, reminder_raw, actor)
            await SystemConfigService.set_raw(KEY_VOLUNTEER_COMP_TIERS, tiers_raw, actor)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return False
        ui.notify('Volunteer settings saved', color='positive')
        return True

    with card.panel:
        SaveFooter(save, enabled=can_edit).watch(reminder_input, tiers_input)
    if not can_edit:
        reminder_input.disable()
        tiers_input.disable()
