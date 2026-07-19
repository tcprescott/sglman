"""Admin Appearance / Theme Colours Page.

Lets a community's STAFF override the shipped brand palette (primary, secondary,
accent, and the header bar). Reads/writes go through ``TenantThemeService``;
semantic status colours are intentionally not editable. A preset picker offers
contrast-verified palettes, and each field shows a live WCAG-AA contrast warning
when a colour would be hard to read where it is used. Saving reloads the page so
the new palette (applied at chrome render) takes effect immediately.
"""

from nicegui import app, ui

from application.services import AuthService, TenantThemeService, get_user_from_discord_id
from application.services.tenant_theme_service import DEFAULT_THEME, THEME_PRESETS

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
        warn_labels: dict[str, ui.label] = {}

        def revalidate() -> None:
            report = TenantThemeService.contrast_report(
                {key: (inp.value or '') for key, inp in inputs.items()}
            )
            for key, wl in warn_labels.items():
                result = report.get(key)
                if result and not result['ok']:
                    wl.text = (
                        f'⚠ Contrast {result["ratio"]}:1 against {result["against"]} '
                        f'— below the {result["threshold"]}:1 AA target.'
                    )
                    wl.visible = True
                else:
                    wl.text = ''
                    wl.visible = False

        # Preset picker: contrast-verified palettes; selecting one fills the
        # fields below (which the user can then fine-tune before saving).
        preset_select = ui.select(
            options=list(THEME_PRESETS.keys()),
            label='Start from a preset',
        ).classes('w-full')
        ui.label(
            'Presets are verified to meet WCAG AA contrast. Pick one, then '
            'fine-tune below.'
        ).classes('text-caption text-grey')

        def apply_preset() -> None:
            preset = THEME_PRESETS.get(preset_select.value)
            if not preset:
                return
            for key, inp in inputs.items():
                inp.value = preset[key]
            revalidate()

        preset_select.on_value_change(apply_preset)

        with ui.column().classes('sgl-form-column gap-4'):
            for label, key, caption in _FIELDS:
                inputs[key] = ui.color_input(
                    label=f'{label} ({DEFAULT_THEME[key]} default)',
                    value=colors[key],
                ).classes('w-full')
                inputs[key].on_value_change(revalidate)
                ui.label(caption).classes('text-caption text-grey')
                warn_labels[key] = ui.label('').classes('text-caption text-warning')
                warn_labels[key].visible = False

        revalidate()

        async def save():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            payload = {key: inp.value for key, inp in inputs.items()}
            try:
                await TenantThemeService.set_theme(actor, payload)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            if TenantThemeService.contrast_warnings(payload):
                ui.notify(
                    'Saved — but some colours may be hard to read (see contrast warnings).',
                    color='warning',
                )
            else:
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
