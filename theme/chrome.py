"""Brand chrome for the **tenant-less** surfaces (``/platform``, the MCP consent
screen).

These pages run on the bare platform host with no tenant in scope, so they
cannot use :class:`~theme.base.BaseLayout`: its drawer links into tenant routes
(``/admin``, ``/volunteer``) and its palette is resolved from the in-scope
tenant. What they still need is everything that makes a page read as Wizzrobe —
the stylesheet and its fonts, the phoenix palette, dark mode, and the gold
header bar with its ember strip. :func:`render_platform_chrome` is that subset,
shared so the tenant-less surfaces cannot drift apart from each other.

:func:`dark_mode_button` is shared with ``BaseLayout``'s header so the toggle
behaves identically everywhere (auto on first visit, then a sticky per-user
preference).
"""

from typing import Callable, Optional

from nicegui import app, ui

# Above-the-fold weights; the rest of the family loads on demand from styles.css.
_PRELOAD_FONTS = (
    'atkinson-hyperlegible-latin-400-normal',
    'fraunces-latin-600-normal',
)


def dark_mode_button(dark: ui.dark_mode) -> ui.button:
    """The header's dark-mode toggle, bound to ``dark`` and the user's session.

    The initial glyph reflects the stored preference — ``brightness_auto`` when
    there is none, because the client is following its own system theme and the
    button has not yet chosen for it.
    """
    dark_pref = app.storage.user.get('dark_mode')
    ref: dict = {'btn': None}

    def toggle() -> None:
        dark.value = not dark.value
        app.storage.user['dark_mode'] = dark.value
        if ref['btn'] is not None:
            ref['btn'].props(f"icon={'light_mode' if dark.value else 'dark_mode'}")
            ref['btn'].update()

    icon = (
        'brightness_auto' if dark_pref is None
        else 'light_mode' if dark_pref
        else 'dark_mode'
    )
    ref['btn'] = ui.button(icon=icon, on_click=toggle).props('flat color=white') \
        .tooltip('Toggle dark mode')
    return ref['btn']


def render_platform_chrome(
    subtitle: Optional[str] = None,
    *,
    right: Optional[Callable[[], None]] = None,
) -> None:
    """Apply the Wizzrobe stylesheet, palette and header bar to a tenant-less page.

    Args:
        subtitle: Rendered after the wordmark as "Wizzrobe · <subtitle>" to name
            the surface (e.g. ``'Platform'``).
        right: Optional callable rendering extra header content before the
            dark-mode toggle, in the right-hand slot.
    """
    dark = ui.dark_mode(app.storage.user.get('dark_mode'))  # None ⇒ follow the client's system theme
    for font_file in _PRELOAD_FONTS:
        ui.add_head_html(
            f'<link rel="preload" href="/static/fonts/{font_file}.woff2" '
            'as="font" type="font/woff2" crossorigin>'
        )
    ui.add_head_html('<link rel="stylesheet" href="/static/css/styles.css">')
    ui.add_head_html('<meta name="robots" content="noindex, nofollow">')
    ui.add_head_html('<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">')
    # The shipped phoenix defaults, not a tenant override: these surfaces belong
    # to the platform, and the consent screen in particular grants a credential
    # that is not scoped to any one community.
    from application.services.tenant_theme_service import DEFAULT_THEME
    ui.colors(
        primary=DEFAULT_THEME['primary'],
        secondary=DEFAULT_THEME['secondary'],
        accent=DEFAULT_THEME['accent'],
        positive='#557A1F',
        negative='#B3362B',
        warning='#B45309',
        info='#0E7470',
    )
    with ui.header().classes(replace='row items-center no-wrap wiz-header'):
        ui.label('Wizzrobe').classes('wiz-wordmark')
        if subtitle:
            ui.label(f'· {subtitle}').classes('wiz-wordmark wiz-wordmark-sub')
        ui.space()
        if right is not None:
            right()
        dark_mode_button(dark)
