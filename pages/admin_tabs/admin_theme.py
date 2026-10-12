"""Admin Appearance / Theme Colours Page.

Lets a community's STAFF override the shipped brand palette (primary, secondary,
accent, and the header's brand mark). Reads/writes go through ``TenantThemeService``;
semantic status colours are intentionally not editable. A preset picker offers
contrast-verified palettes, and each field shows a live WCAG-AA contrast warning
when a colour would be hard to read where it is used. Saving reloads the page so
the new palette (applied at chrome render) takes effect immediately.

The logo section uploads through ``TenantLogoService``, which validates and
re-encodes the image; it saves on upload rather than with the colours.
"""

from nicegui import app, ui

from application.services import AuthService, TenantLogoService, TenantThemeService, get_user_from_discord_id
from application.services.tenant_logo_service import ACCEPT, MAX_UPLOAD_BYTES
from application.services.tenant_theme_service import DEFAULT_THEME, THEME_PRESETS
from application.tenant_context import get_current_tenant_id, tenant_scope
from theme.notify import notify_error
from theme.page_header import page_header

# label, config key, helper caption for each editable brand colour.
_FIELDS = [
    ('Primary', 'primary', 'Buttons, links, and the selected menu item (deep tone for light mode).'),
    ('Secondary', 'secondary', 'Secondary accents and ember highlights.'),
    ('Accent', 'accent', 'Bright accent — highlights and links in dark mode.'),
    ('Brand mark', 'header', "The square beside your community's name in the header, when there's no logo."),
]


def _logo_preview(logo: str | None, name: str, tone: str) -> None:
    with ui.element('div').classes(f'wiz-logo-preview wiz-logo-preview--{tone}'):
        if logo:
            ui.element('img').props(f'src="{logo}" alt="" width="28" height="28"').classes('wiz-logo-preview-mark')
        else:
            ui.element('span').classes('wiz-logo-preview-mark wiz-logo-preview-mark--colour')
        ui.label(name).classes('wiz-logo-preview-name')


def _logo_section(logo: str | None, can_edit: bool) -> None:
    tenant_id = get_current_tenant_id()
    ui.label('Logo').classes('text-subtitle1 text-weight-bold')
    ui.label(
        "Replaces the brand mark beside your community's name and becomes the browser tab icon. "
        'Use a square PNG, JPEG or WebP, at least 64×64 and up to 1 MB. '
        "A transparent background looks best, but check it's visible on the dark header too."
    ).classes('text-caption text-grey')
    with ui.row().classes('gap-3 items-center'):
        _logo_preview(logo, 'Light header', 'light')
        _logo_preview(logo, 'Dark header', 'dark')
    if not can_edit:
        return

    async def on_upload(e) -> None:
        if e.file.size() > MAX_UPLOAD_BYTES:
            ui.notify('Logos can be up to 1 MB. Try exporting a smaller PNG or WebP.', color='warning')
            uploader.reset()
            return
        data = await e.file.read()
        with tenant_scope(tenant_id):
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            if actor is None:
                return
            try:
                await TenantLogoService.set_logo(actor, data)
            except (ValueError, PermissionError) as err:
                notify_error(err)
                uploader.reset()
                return
        ui.notify('Logo saved', color='positive')
        ui.navigate.reload()

    async def remove() -> None:
        with tenant_scope(tenant_id):
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            if actor is None:
                return
            try:
                await TenantLogoService.remove_logo(actor)
            except (ValueError, PermissionError) as err:
                notify_error(err)
                return
        ui.notify('Logo removed', color='positive')
        ui.navigate.reload()

    # Quasar's uploader card fails axe (an unnamed file input, a nameless nested
    # button), so it stays hidden and a plain named button opens its picker.
    uploader = ui.upload(
        auto_upload=True,
        max_file_size=MAX_UPLOAD_BYTES,
        on_upload=on_upload,
        on_rejected=lambda: ui.notify(
            'Logos can be up to 1 MB, as a PNG, JPEG or WebP.', color='warning'),
    ).props(f'accept="{ACCEPT}"').classes('hidden wiz-logo-upload')
    with ui.row().classes('gap-2 items-center'):
        ui.button(
            'Replace logo' if logo else 'Upload logo', icon='upload',
            on_click=lambda: uploader.run_method('pickFiles'),
        ).props('outline color=primary')
        if logo:
            ui.button('Remove logo', icon='delete', on_click=remove).props('flat color=negative')


async def admin_theme_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_edit = await AuthService.is_staff(actor)

    colors = await TenantThemeService.get_current_theme()

    with ui.column().classes('page-container-narrow'):
        page_header(
            'Appearance',
            'Customise your community\'s logo and brand colours. Changes apply across the '
            'app on the next page load. Leave a field blank to use the default. '
            'Status colours (success, warning, error) are fixed for consistency.',
        )

        _logo_section(colors.get('logo'), can_edit)
        ui.separator()

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

        with ui.column().classes('wiz-form-column gap-4'):
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
