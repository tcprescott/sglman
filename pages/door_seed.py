"""The door seed page: one Door Randomizer seed, and the patcher that builds it.

``GET /t/<slug>/door/<token>``, the link a door seed's roll hands out. It is a
``@public_page``: players open it signed out, and the unguessable token is the
whole authorization, as for the patch files it loads.

The player's ROM never reaches the server. ``static/js/door-patcher/page.js``
keeps it in IndexedDB on the device, fetches the seed's writes and the base
patch from ``/door-seeds/…``, builds the ROM and saves it. Options live in the
browser's localStorage so the next seed reuses them; this side only mirrors
them to draw the controls and the one-line summary.

Layout C (Thomas, 2026-10-16): a big Download button that uses the saved
setup, with the options folded under Customize.
"""

import json
from typing import Optional

from nicegui import app, ui

from application.errors import NotFoundError
from application.services import DoorSeedService, TenantService, get_user_from_session
from application.tenant_context import get_current_tenant_id
from application.utils.tenant_urls import tenant_url
from application.utils.timezone import format_local_display
from middleware.auth import public_page
from models import DoorSeed, User
from theme.assets import asset_url
from theme.banner import banner
from theme.base import BaseLayout
from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_header, mobile_sheet
from theme.page_header import page_header

__all__ = ['create']

SPRITE_PAGE = 48

DEFAULTS = {
    'heartColor': 'red',
    'heartBeep': 'normal',
    'menuSpeed': 'normal',
    'owPalettes': 'default',
    'uwPalettes': 'default',
    'quickswap': True,
    'music': True,
    'reduceFlashing': False,
    'sprite': None,
}

SELECTS = [
    ('heartColor', 'Heart colour', {
        'red': 'Red', 'blue': 'Blue', 'green': 'Green', 'yellow': 'Yellow', 'random': 'Random',
    }),
    ('heartBeep', 'Low health beep', {
        'off': 'Off', 'quarter': 'Quarter', 'half': 'Half', 'normal': 'Normal', 'double': 'Double',
    }),
    ('menuSpeed', 'Menu speed', {
        'half': 'Half', 'normal': 'Normal', 'double': 'Double', 'triple': 'Triple',
        'quadruple': 'Quadruple', 'instant': 'Instant',
    }),
    ('owPalettes', 'Overworld palettes', {
        'default': 'Default', 'shuffled': 'Shuffled', 'legacy': 'Legacy', 'grayscale': 'Grayscale',
        'blackout': 'Blackout', 'puke': 'Puke',
    }),
    ('uwPalettes', 'Dungeon palettes', {
        'default': 'Default', 'shuffled': 'Shuffled', 'legacy': 'Legacy', 'grayscale': 'Grayscale',
        'blackout': 'Blackout', 'puke': 'Puke',
    }),
]

TOGGLES = [
    ('quickswap', 'Item quickswap'),
    ('music', 'Background music'),
    ('reduceFlashing', 'Reduce flashing'),
]

_JS_READY = 'window.__wizDoorPatcherReady'


def _clean_options(raw: object) -> dict:
    """Saved options from the browser, with anything unknown dropped."""
    options = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return options
    for key, _label, choices in SELECTS:
        if raw.get(key) in choices:
            options[key] = raw[key]
    for key, _label in TOGGLES:
        if isinstance(raw.get(key), bool):
            options[key] = raw[key]
    sprite = raw.get('sprite')
    if isinstance(sprite, dict):
        if sprite.get('random') is True:
            options['sprite'] = {'random': True, 'name': 'Random'}
        elif isinstance(sprite.get('name'), str) and isinstance(sprite.get('file'), str):
            options['sprite'] = {k: sprite.get(k) for k in ('name', 'file', 'preview')}
    return options


def _sprite_name(options: dict) -> str:
    sprite = options.get('sprite')
    return sprite['name'] if sprite else 'Link'


def _summary(options: dict) -> str:
    labels = {key: choices for key, _label, choices in SELECTS}
    parts = [
        _sprite_name(options),
        f"{labels['heartColor'][options['heartColor']]} hearts",
        f"{labels['heartBeep'][options['heartBeep']]} beep",
        f"Quickswap {'on' if options['quickswap'] else 'off'}",
    ]
    if not options['music']:
        parts.append('Music off')
    if options['menuSpeed'] != 'normal':
        parts.append(f"{labels['menuSpeed'][options['menuSpeed']]} menu")
    if options['owPalettes'] != 'default' or options['uwPalettes'] != 'default':
        parts.append('Palette shuffle')
    return ' · '.join(parts)


def _add_scripts(seed: DoorSeed) -> None:
    """The patcher's scripts, added before the layout renders.

    A signed-in layout awaits the socket while it builds, and anything added to
    the head after that is inserted as HTML, where a <script> never runs.
    """
    ui.add_head_html(
        '<script>'
        f'window.__wizDoorSeed = {_seed_config(seed)};'
        f'{_JS_READY} = new Promise(r => {{ window.__wizDoorPatcherResolve = r; }});'
        '</script>'
        f'<script type="module" src="{asset_url("js/door-patcher/page.js")}"></script>'
    )


def _seed_config(seed: DoorSeed) -> str:
    config = {
        'patchUrl': f'/door-seeds/{seed.token}/patch.json',
        'baseUrl': f'/door-seeds/base/{seed.version}.bps',
        'spritesUrl': '/door-seeds/sprites.json',
        'filename': f'DR_{seed.token}.sfc',
    }
    # A <script> body ends at the first "</", so escape it out of the JSON.
    return json.dumps(config).replace('<', '\\u003c')


async def _page_link(seed: DoorSeed) -> Optional[str]:
    tid = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tid) if tid is not None else None
    return tenant_url(tenant, f'/door/{seed.token}') if tenant is not None else None


class _SpritePicker:
    """The sprite dialog: Link, Random, then the alttpr.com list, searchable."""

    def __init__(self, on_pick, current) -> None:
        self.on_pick = on_pick
        self.current = current
        self.sprites: list = []
        self.query = ''
        with ui.dialog() as self.dialog, ui.card().classes('dialog-card dialog-card--lg'):
            mobile_sheet(self.dialog)
            dialog_header('Choose a sprite', self.dialog)
            ui.input(
                'Search sprites', on_change=lambda e: self._search(e.value),
            ).props('outlined dense clearable autofocus').classes('w-full')
            self.grid = ui.refreshable(self._grid)
            self.grid()

    async def open(self) -> None:
        if not self.sprites:
            self.sprites = await DoorSeedService.sprite_list()
        self.grid.refresh()
        self.dialog.open()

    def _search(self, value: Optional[str]) -> None:
        self.query = (value or '').strip().lower()
        self.grid.refresh()

    def _tile(self, name: str, caption: str, preview: Optional[str], choice: Optional[dict]) -> None:
        chosen = _sprite_name({'sprite': self.current()}) == name
        tile = ui.element('button').classes('wiz-door-sprite' + (' wiz-door-sprite--chosen' if chosen else '')) \
            .props(f'type=button aria-pressed={"true" if chosen else "false"}')
        with tile:
            if preview:
                # A few listed previews 404 upstream; hide the broken image, keep the name.
                ui.element('img').props(
                    f'src="{preview}" alt="" loading=lazy width=32 height=48 '
                    'onerror="this.style.visibility=\'hidden\'"'
                ) \
                    .classes('wiz-door-sprite__img')
            else:
                ui.icon('shuffle' if choice else 'person', size='28px').classes('wiz-door-sprite__img')
            ui.label(name).classes('wiz-door-sprite__name')
            if caption:
                ui.label(caption).classes('wiz-door-sprite__author')
        tile.on('click', lambda: self._pick(choice))

    async def _pick(self, choice: Optional[dict]) -> None:
        self.dialog.close()
        await self.on_pick(choice)

    def _grid(self) -> None:
        matches = [
            s for s in self.sprites
            if not s.get('default') and (
                not self.query or self.query in s['name'].lower() or self.query in s['author'].lower()
                or any(self.query in t.lower() for t in s.get('tags', []))
            )
        ]
        with ui.element('div').classes('wiz-door-sprites'):
            if not self.query:
                self._tile('Link', 'The original', None, None)
                self._tile('Random', 'A new one each download', None, {'random': True, 'name': 'Random'})
            for sprite in matches[:SPRITE_PAGE]:
                self._tile(sprite['name'], sprite['author'], sprite['preview'], {
                    'name': sprite['name'], 'file': sprite['file'], 'preview': sprite['preview'],
                })
        if not self.sprites:
            ui.label("The sprite list isn't available right now. Try again in a few minutes.") \
                .classes('text-muted')
        elif len(matches) > SPRITE_PAGE:
            ui.label(f'Showing {SPRITE_PAGE} of {len(matches)}. Search to find the rest.').classes('text-muted')
        elif not matches and self.query:
            ui.label('No sprites match that.').classes('text-muted')


async def _render(seed: DoorSeed, user: Optional[User]) -> None:
    state = {'options': dict(DEFAULTS), 'has_rom': False, 'ready': False, 'busy': False, 'failed': False}
    spoiler_ok = await DoorSeedService.can_read_spoiler(seed, user)
    link = await _page_link(seed)

    def save_options() -> None:
        ui.run_javascript(f'{_JS_READY}.then(p => p.saveOptions({json.dumps(state["options"])}))')
        summary.refresh()

    async def pick_sprite(choice: Optional[dict]) -> None:
        state['options']['sprite'] = choice
        save_options()
        sprite_row.refresh()

    picker = _SpritePicker(pick_sprite, lambda: state['options']['sprite'])

    def set_option(key: str, value) -> None:
        state['options'][key] = value
        save_options()

    with ui.column().classes('page-container-narrow w-full gap-4'):
        page_header('Door seed', f'Door Randomizer {seed.version} · rolled {format_local_display(seed.created_at)}')

        with ui.element('section').classes('wiz-panel wiz-door-card'):
            if seed.seed_code:
                with ui.element('div').classes('wiz-door-code'):
                    ui.label('Code').classes('wiz-door-code__label')
                    ui.label(', '.join(seed.seed_code)).classes('wiz-door-code__value')

            @ui.refreshable
            def primary() -> None:
                if state['failed']:
                    with banner(
                        "This browser couldn't load the patcher. Try an up-to-date Chrome, Firefox, Edge or Safari.",
                        tone='warning',
                    ):
                        pass
                elif not state['ready']:
                    ui.button('Getting ready…').props('unelevated no-caps disable loading') \
                        .classes('wiz-door-primary')
                elif state['has_rom']:
                    ui.button('Download ROM', icon='download').props(
                        f'unelevated no-caps{" loading" if state["busy"] else ""}',
                    ).classes('wiz-door-primary').on(
                        'click', start_download,
                        js_handler=f'() => {{ emit(); {_JS_READY}.then(p => p.downloadCurrent()); }}',
                    )
                else:
                    ui.button('Choose your ROM…', icon='upload_file').props('unelevated no-caps') \
                        .classes('wiz-door-primary') \
                        .on('click', js_handler=f'() => {_JS_READY}.then(p => p.pickRom())')
                    ui.label(
                        'Pick your Japanese 1.0 Link to the Past ROM. It stays on this device, '
                        "and you won't be asked again."
                    ).classes('text-muted')

            async def start_download() -> None:
                state['busy'] = True
                primary.refresh()

            primary()

            with ui.row().classes('wiz-door-setup items-center no-wrap w-full'):
                @ui.refreshable
                def summary() -> None:
                    ui.label(_summary(state['options'])).classes('wiz-door-summary')

                summary()
                customize = ui.button('Customize', color=None) \
                    .props('outline no-caps icon-right=expand_more').classes('wiz-door-customize')

            with ui.column().classes('wiz-door-options w-full gap-3') as options_panel:
                @ui.refreshable
                def sprite_row() -> None:
                    with ui.row().classes('items-center no-wrap w-full gap-3'):
                        with ui.column().classes('gap-0 col'):
                            ui.label('Sprite').classes('wiz-door-code__label')
                            ui.label(_sprite_name(state['options'])).classes('text-weight-bold')
                        ui.button('Choose sprite…', on_click=picker.open, color=None).props('outline no-caps')

                sprite_row()

                @ui.refreshable
                def controls() -> None:
                    with ui.element('div').classes('wiz-door-selects'):
                        for key, label, choices in SELECTS:
                            ui.select(
                                choices, label=label, value=state['options'][key],
                                on_change=lambda e, k=key: set_option(k, e.value),
                            ).props('outlined dense options-dense')
                    with ui.column().classes('gap-0'):
                        for key, label in TOGGLES:
                            ui.checkbox(
                                label, value=state['options'][key],
                                on_change=lambda e, k=key: set_option(k, bool(e.value)),
                            )

                controls()
            options_panel.set_visibility(False)

            def toggle_options() -> None:
                options_panel.set_visibility(not options_panel.visible)
                customize.props(f'aria-expanded={"true" if options_panel.visible else "false"}')
                customize.props(f'icon-right={"expand_less" if options_panel.visible else "expand_more"}')

            customize.props('aria-expanded=false')
            customize.on('click', toggle_options)

        @ui.refreshable
        def rom_note() -> None:
            if not state['has_rom']:
                return
            with ui.row().classes('items-center gap-2 text-muted wiz-door-rom'):
                ui.icon('check_circle').classes('st-ok')
                ui.label('Your ROM is saved on this device.').classes('col')
                ui.button('Change ROM', color=None).props('flat no-caps dense').classes('wiz-door-link') \
                    .on('click', js_handler=f'() => {_JS_READY}.then(p => p.pickRom())')

        rom_note()

        with ui.row().classes('items-center gap-2'):
            if spoiler_ok and seed.spoiler_access == 'public':
                ui.link('Spoiler log', f'/door-seeds/{seed.token}/spoiler.json').classes('wiz-door-link')
            elif spoiler_ok:
                async def download_spoiler() -> None:
                    try:
                        content = await DoorSeedService().spoiler_for(seed, user)
                    except NotFoundError as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.download.content(content, f'DR_{seed.token}_spoiler.json', 'application/json')

                ui.button('Spoiler log (staff)', icon='lock', on_click=download_spoiler, color=None) \
                    .props('flat no-caps dense').classes('wiz-door-link')
            if link:
                ui.button('Copy link', icon='link', on_click=lambda: copy_to_clipboard(link, 'Link'), color=None) \
                    .props('flat no-caps dense').classes('wiz-door-link')

    def on_rom_picked(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        if result.get('ok'):
            state['has_rom'] = True
            ui.notify('ROM saved on this device.', color='positive')
        else:
            ui.notify(result.get('error') or "That ROM couldn't be read.", color='warning')
        primary.refresh()
        rom_note.refresh()

    def on_download_done(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        state['busy'] = False
        if result.get('needRom'):
            state['has_rom'] = False
            rom_note.refresh()
        if not result.get('ok'):
            ui.notify(result.get('error') or "The ROM couldn't be built.", color='warning')
        primary.refresh()

    ui.on('door_rom_picked', on_rom_picked)
    ui.on('door_download_done', on_download_done)

    def on_state(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        state['options'] = _clean_options(result.get('options'))
        state['has_rom'] = bool(result.get('hasRom'))
        state['ready'] = True
        for section in (primary, summary, sprite_row, controls, rom_note):
            section.refresh()

    def give_up() -> None:
        # The patcher script never loaded (an old browser, a blocked module):
        # say so rather than spin forever.
        if not state['ready']:
            state['failed'] = True
            primary.refresh()

    async def ask_state() -> None:
        await ui.context.client.connected()
        ui.run_javascript(
            f'{_JS_READY}.then(p => Promise.all([p.loadOptions(), p.hasRom()]))'
            '.then(([o, r]) => emitEvent("door_state", {options: o.options, hasRom: r.hasRom}))'
        )

    ui.on('door_state', on_state)
    ui.timer(0, ask_state, once=True)
    ui.timer(15, give_up, once=True)


def create() -> None:
    @public_page('/door/{token}', telemetry_path='/door')
    async def door_seed(token: str) -> None:
        user = await get_user_from_session(app.storage.user)
        try:
            seed = await DoorSeedService().get_seed(token)
        except NotFoundError:
            from theme.error_page import render_not_found
            await render_not_found(user=user)
            return
        ui.page_title(f'Door seed — {await TenantService.current_community_name() or "Wizzrobe"}')
        _add_scripts(seed)
        await BaseLayout(user=user).render()
        await _render(seed, user)
