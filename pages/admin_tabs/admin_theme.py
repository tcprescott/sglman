"""Admin Appearance / Theme Colours Page.

Lets a community's STAFF override the shipped brand palette (primary, secondary,
accent, and the header bar). Reads/writes go through ``TenantThemeService``;
semantic status colours are intentionally not editable. Saving reloads the page
so the new palette (applied at chrome render) takes effect immediately.
"""

from nicegui import app, ui

from application.services import AuthService, TenantThemeService, get_user_from_discord_id
from application.services.tenant_theme_service import DEFAULT_THEME

# label, config key, helper caption for each editable brand colour.
_FIELDS = [
    ('Primary', 'primary', 'Buttons, links, and section titles (deep tone for light mode).'),
    ('Secondary', 'secondary', 'Secondary accents and ember highlights.'),
    ('Accent', 'accent', 'Bright accent — highlights and links in dark mode.'),
    ('Header bar', 'header', 'Background of the top header bar in light mode.'),
]


async def admin_theme_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_edit = await AuthService.is_staff(actor)

    colors = await TenantThemeService.get_current_theme()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Appearance').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Customise your community\'s brand colours. Changes apply across the '
            'app on the next page load. Leave a field blank to use the default. '
            'Status colours (success, warning, error) are fixed for consistency.'
        ).classes('text-caption text-grey')

        inputs: dict[str, ui.color_input] = {}
        with ui.column().classes('sgl-form-column gap-4'):
            for label, key, caption in _FIELDS:
                inputs[key] = ui.color_input(
                    label=f'{label} ({DEFAULT_THEME[key]} default)',
                    value=colors[key],
                ).classes('w-full')
                ui.label(caption).classes('text-caption text-grey')

        async def save():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            try:
                await TenantThemeService.set_theme(
                    actor, {key: inp.value for key, inp in inputs.items()}
                )
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Theme colours saved', color='positive')
            ui.navigate.reload()

        async def reset():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            try:
                await TenantThemeService.set_theme(actor, {})
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Reset to default colours', color='positive')
            ui.navigate.reload()

        if can_edit:
            with ui.row().classes('gap-2 mt-2'):
                ui.button('Save', icon='save', on_click=save).props('color=primary')
                ui.button('Reset to defaults', icon='restart_alt', on_click=reset).props('flat color=primary')
