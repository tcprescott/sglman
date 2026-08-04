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

from theme.assets import asset_url

# Above-the-fold weights; the rest of the family loads on demand from styles.css.
_PRELOAD_FONTS = (
    'atkinson-hyperlegible-latin-400-normal',
    'fraunces-latin-600-normal',
)


def install_timezone_detection() -> None:
    """Report the device's IANA timezone to the server on a cookie.

    The server renders times before any websocket exists, so the zone has to
    arrive with the HTTP request itself — a cookie, not a ``run_javascript``
    round-trip. This snippet writes it on every load (cheap and idempotent), and
    ``TenantMiddleware`` reads it back into the request's timezone context.

    On a browser's **first** visit there is no cookie yet, so that one page
    renders on the community's default clock and then reloads once to pick up
    the real zone. The reload is guarded twice over: ``sessionStorage`` caps it
    at one per tab even when cookies are blocked outright (otherwise the missing
    cookie would look like a first visit forever), and the window flag stops a
    double-fire within a single load. A zone that merely *changed* — someone
    travelled — updates the cookie silently and takes effect on the next
    navigation, because a surprise reload mid-session is worse than a stale
    clock for a few seconds.

    Ignored entirely when the community pins a timezone: the cookie is still
    written, but resolution never reads it.
    """
    ui.add_body_html(
        '<script>'
        'if(!window.__wizTzInstalled){'
        'window.__wizTzInstalled=true;'
        'try{'
        'var tz=Intl.DateTimeFormat().resolvedOptions().timeZone;'
        'if(tz){'
        "var m=document.cookie.match(/(?:^|;\\s*)wiz_tz=([^;]*)/);"
        'var cur=m?decodeURIComponent(m[1]):null;'
        'if(cur!==tz){'
        "document.cookie='wiz_tz='+encodeURIComponent(tz)+"
        "';path=/;max-age=31536000;samesite=Lax';"
        "if(!m&&!sessionStorage.getItem('wizTzReload')){"
        "sessionStorage.setItem('wizTzReload','1');location.reload();}"
        '}}}catch(e){}'
        '}'
        '</script>'
    )


def apply_brand_palette(colors: dict[str, str]) -> None:
    """Point Quasar's palette and the ``--wiz-*`` brand vars at ``colors``.

    Shared by every surface that paints itself Wizzrobe — the tenant layout, the
    platform chrome, and the auth wait screens — so a community's colours reach
    all of them and none of them drift. Semantic status colours stay fixed,
    warm-tuned to the ``--status-*`` tokens in styles.css.
    """
    ui.colors(
        primary=colors['primary'],
        secondary=colors['secondary'],
        accent=colors['accent'],
        positive='#557A1F',
        negative='#B3362B',
        warning='#B45309',
        info='#0E7470',
    )
    # ui.colors only recolors Quasar's palette; the header bar, links, and
    # section titles read the --wiz-* brand vars from styles.css. Re-point
    # those to the tenant palette here (loaded after the stylesheet, so this
    # wins). --wiz-header-bg is set on :root for the light bar; the dark
    # rule in styles.css re-points it to charcoal on <body>, which stays
    # authoritative in dark mode. The two dark text-tint rules mirror the
    # !important defaults in styles.css so primary/secondary text follows the
    # tenant accent/secondary in dark mode too.
    ui.add_head_html(
        '<style>'
        ':root{'
        f'--wiz-gold-deep:{colors["primary"]};'
        f'--wiz-gold:{colors["accent"]};'
        f'--wiz-ember-deep:{colors["secondary"]};'
        f'--wiz-ember:{colors["secondary"]};'
        f'--wiz-header-bg:{colors["header"]};'
        '}'
        '.body--dark .text-primary,.q-dark .text-primary{color:var(--wiz-gold)!important;}'
        '.body--dark .text-secondary,.q-dark .text-secondary{color:var(--wiz-ember)!important;}'
        '</style>'
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
    ui.add_head_html(f'<link rel="stylesheet" href="{asset_url("css/styles.css")}">')
    ui.add_head_html('<meta name="robots" content="noindex, nofollow">')
    ui.add_head_html('<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">')
    install_timezone_detection()
    # The shipped phoenix defaults, not a tenant override: these surfaces belong
    # to the platform, and the consent screen in particular grants a credential
    # that is not scoped to any one community.
    from application.services.tenant_theme_service import DEFAULT_THEME
    apply_brand_palette(DEFAULT_THEME)
    with ui.header().classes(replace='row items-center no-wrap wiz-header'):
        ui.label('Wizzrobe').classes('wiz-wordmark')
        if subtitle:
            ui.label(f'· {subtitle}').classes('wiz-wordmark wiz-wordmark-sub')
        ui.space()
        if right is not None:
            right()
        dark_mode_button(dark)
