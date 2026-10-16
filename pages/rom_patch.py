"""The ROM patch pages: a patch staff host, and the open patcher.

``GET /t/<slug>/patch/<token>`` is the link staff share for a patch uploaded
under Admin → Patches. ``GET /t/<slug>/patcher`` is one page where anyone
applies a BPS, IPS or UPS file they already have. Both are ``@public_page``s:
players open them signed out, and a hosted patch's unguessable token is the
whole authorization, as for the file it loads.

The player's ROM never reaches the server. ``static/js/rom-patcher/page.js``
keeps every ROM in IndexedDB on the device, keyed by CRC32, so a second patch
for the same game downloads in one tap. This side only draws what its events
report.
"""

import json
import re
from typing import Any, Optional

from nicegui import app, ui

from application.errors import NotFoundError
from application.services import RomPatchService, TenantService, get_user_from_session
from application.tenant_context import get_current_tenant_id
from application.utils.tenant_urls import tenant_url
from application.utils.timezone import format_local_date
from middleware.auth import public_page
from models import RomPatch
from theme.assets import asset_url
from theme.banner import banner
from theme.base import BaseLayout
from theme.clipboard import copy_to_clipboard
from theme.page_header import page_header

__all__ = ['create', 'output_base']

_JS_READY = 'window.__wizRomPatcherReady'
_FORMAT_LABELS = {'bps': 'BPS', 'ips': 'IPS', 'ups': 'UPS'}


def output_base(title: str) -> str:
    """A filename stem from a patch title: ``"SM: SGL practice hack"`` → ``SM_SGL_practice_hack``."""
    stem = re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_')
    return stem[:80] or 'patched'


def _add_scripts(config: dict) -> None:
    """The patcher's scripts, added before the layout renders.

    A signed-in layout awaits the socket while it builds, and anything added to
    the head after that is inserted as HTML, where a <script> never runs.
    """
    # A <script> body ends at the first "</", so escape it out of the JSON.
    payload = json.dumps(config).replace('<', '\\u003c')
    ui.add_head_html(
        '<script>'
        f'window.__wizRomPatch = {payload};'
        f'{_JS_READY} = new Promise(r => {{ window.__wizRomPatcherResolve = r; }});'
        '</script>'
        f'<script type="module" src="{asset_url("js/rom-patcher/page.js")}"></script>'
    )


def _primary_button(label: str, icon: str, js: str, busy: bool = False, disabled: bool = False):
    props = 'unelevated no-caps'
    if busy:
        props += ' loading'
    if disabled:
        props += ' disable'
    return ui.button(label, icon=icon).props(props).classes('wiz-door-primary') \
        .on('click', js_handler=f'() => {{ emit(); {_JS_READY}.then(p => p.{js}()); }}')


def _loader_failed() -> None:
    with banner(
        "This browser couldn't load the patcher. Try an up-to-date Chrome, Firefox, Edge or Safari.",
        tone='warning',
    ):
        pass


def _watch_loader(state: dict, refresh) -> None:
    def give_up() -> None:
        # The patcher script never loaded (an old browser, a blocked module):
        # say so rather than spin forever.
        if not state['ready']:
            state['failed'] = True
            refresh()

    ui.timer(15, give_up, once=True)


def _needs_line(patch: RomPatch) -> None:
    with ui.element('div').classes('wiz-door-code wiz-patch-needs'):
        ui.label('Needs').classes('wiz-door-code__label')
        ui.label(patch.game).classes('text-weight-bold')
        if patch.source_crc:
            ui.label(f'CRC32 {patch.source_crc}').classes('wiz-patch-crc')
        else:
            ui.label("This patch doesn't say which exact ROM it needs.").classes('wiz-door-code__label')


async def _patch_link(patch: RomPatch) -> Optional[str]:
    tid = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tid) if tid is not None else None
    return tenant_url(tenant, f'/patch/{patch.token}') if tenant is not None else None


async def _render_hosted(patch: RomPatch) -> None:
    state: dict[str, Any] = {'rom': None, 'ready': False, 'busy': False, 'failed': False}
    link = await _patch_link(patch)
    uploader = patch.uploaded_by
    byline = ' · '.join(filter(None, [
        f'Uploaded by {uploader.display_name or uploader.username}' if uploader else None,
        format_local_date(patch.updated_at),
        patch.tournament.name if patch.tournament else None,
    ]))

    with ui.column().classes('page-container-narrow w-full gap-4'):
        page_header(patch.title, byline)

        with ui.element('section').classes('wiz-panel wiz-door-card'):
            if patch.description:
                ui.label(patch.description).classes('wiz-patch-description')
            _needs_line(patch)

            @ui.refreshable
            def primary() -> None:
                if state['failed']:
                    _loader_failed()
                elif not state['ready']:
                    ui.button('Getting ready…').props('unelevated no-caps disable loading') \
                        .classes('wiz-door-primary')
                elif state['rom']:
                    _primary_button('Download patched ROM', 'download', 'download', busy=state['busy']) \
                        .on('click', start_download)
                else:
                    _primary_button('Choose your ROM…', 'upload_file', 'pickRom')
                    ui.label(
                        "First time on this device: pick your ROM once and it's remembered "
                        'for every patch that needs it.'
                    ).classes('text-muted')

            async def start_download() -> None:
                state['busy'] = True
                primary.refresh()

            primary()

        @ui.refreshable
        def rom_note() -> None:
            if not state['rom']:
                return
            with ui.row().classes('items-center gap-2 text-muted wiz-door-rom'):
                ui.icon('check_circle').classes('st-ok')
                ui.label(f"Your ROM ({state['rom']['name']}) is saved on this device.").classes('col')
                ui.button('Change ROM', color=None).props('flat no-caps dense').classes('wiz-door-link') \
                    .on('click', js_handler=f'() => {_JS_READY}.then(p => p.pickRom())')

        rom_note()

        if link:
            with ui.row().classes('items-center gap-2'):
                ui.button('Copy link', icon='link', on_click=lambda: copy_to_clipboard(link, 'Link'), color=None) \
                    .props('flat no-caps dense').classes('wiz-door-link')

    def on_rom_picked(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        if result.get('ok'):
            state['rom'] = result.get('rom')
            ui.notify('ROM saved on this device.', color='positive')
        else:
            ui.notify(result.get('error') or "That ROM couldn't be read.", color='warning')
        primary.refresh()
        rom_note.refresh()

    async def on_download_done(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        state['busy'] = False
        if result.get('needRom'):
            state['rom'] = None
            rom_note.refresh()
        if result.get('ok'):
            try:
                await RomPatchService.record_download(patch.token)
            except NotFoundError:
                pass
        else:
            ui.notify(result.get('error') or "The ROM couldn't be patched.", color='warning')
        primary.refresh()

    def on_state(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        state['rom'] = result.get('rom') if isinstance(result.get('rom'), dict) else None
        state['ready'] = True
        primary.refresh()
        rom_note.refresh()

    async def ask_state() -> None:
        await ui.context.client.connected()
        ui.run_javascript(
            f'{_JS_READY}.then(p => p.status()).then(s => emitEvent("rom_state", {{rom: s.rom}}))'
        )

    ui.on('rom_picked', on_rom_picked)
    ui.on('rom_download_done', on_download_done)
    ui.on('rom_state', on_state)
    ui.timer(0, ask_state, once=True)
    _watch_loader(state, primary.refresh)


async def _render_open() -> None:
    state: dict[str, Any] = {'patch': None, 'rom': None, 'error': None, 'ready': False, 'busy': False, 'failed': False}

    with ui.column().classes('page-container-narrow w-full gap-4'):
        page_header('ROM patcher', 'Apply a BPS, IPS or UPS patch to your own ROM, right in your browser. '
                                   'Nothing is uploaded.')

        @ui.refreshable
        def card() -> None:
            with ui.element('section').classes('wiz-panel wiz-door-card'):
                if state['failed']:
                    _loader_failed()
                    return
                patch = state['patch']
                rom = state['rom']
                file_row(
                    _FORMAT_LABELS.get(patch['format'], 'Patch') if patch else 'Patch',
                    patch['name'] if patch else None,
                    (f"Needs CRC32 {patch['crc']}" if patch['crc'] else "Doesn't name a ROM") if patch else None,
                    'Choose patch…', 'pickPatch',
                )
                file_row(
                    'ROM', rom['name'] if rom else None,
                    ('Saved on this device · matches the patch' if patch and patch['crc'] else 'Ready to patch')
                    if rom else None,
                    'Choose ROM…', 'pickRom', disabled=patch is None,
                )
                if state['error']:
                    with banner(state['error'], tone='warning'):
                        pass
                elif patch and rom and patch['crc']:
                    ui.label('Ready: the ROM matches what this patch was made for.').classes('st-ok')
                elif patch and not patch['crc'] and not rom:
                    ui.label(
                        "An IPS patch doesn't say which ROM it needs, so check you've got the right one."
                    ).classes('text-muted')
                _primary_button(
                    'Download patched ROM', 'download', 'download',
                    busy=state['busy'], disabled=not (state['ready'] and patch and rom),
                ).on('click', start_download)

        def file_row(kind: str, name: Optional[str], detail: Optional[str], pick: str, js: str,
                     disabled: bool = False) -> None:
            with ui.row().classes('wiz-patch-file items-center no-wrap w-full'):
                ui.label(kind).classes('wiz-patch-file__kind')
                with ui.column().classes('gap-0 col wiz-patch-file__body'):
                    if name:
                        ui.label(name).classes('text-weight-bold wiz-patch-file__name')
                        ui.label(detail or '').classes('wiz-door-code__label')
                    else:
                        ui.label('None chosen').classes('text-muted')
                button = ui.button('Change' if name else pick, color=None) \
                    .props('outline no-caps' + (' disable' if disabled or not state['ready'] else ''))
                button.on('click', js_handler=f'() => {_JS_READY}.then(p => p.{js}())')

        async def start_download() -> None:
            state['busy'] = True
            card.refresh()

        card()

    def on_patch_picked(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        if result.get('ok'):
            state['patch'] = {k: result.get(k) for k in ('name', 'format', 'crc')}
            state['rom'] = result.get('rom') if isinstance(result.get('rom'), dict) else None
            state['error'] = None
        else:
            ui.notify(result.get('error') or "That patch couldn't be read.", color='warning')
        card.refresh()

    def on_rom_picked(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        if result.get('ok'):
            state['rom'] = result.get('rom')
            state['error'] = None
        else:
            state['error'] = result.get('error') or "That ROM couldn't be read."
        card.refresh()

    def on_download_done(e) -> None:
        result = e.args if isinstance(e.args, dict) else {}
        state['busy'] = False
        if not result.get('ok'):
            ui.notify(result.get('error') or "The ROM couldn't be patched.", color='warning')
        card.refresh()

    def on_ready(_e) -> None:
        state['ready'] = True
        card.refresh()

    async def ask_ready() -> None:
        await ui.context.client.connected()
        ui.run_javascript(f'{_JS_READY}.then(() => emitEvent("rom_patcher_ready", {{}}))')

    ui.on('patch_picked', on_patch_picked)
    ui.on('rom_picked', on_rom_picked)
    ui.on('rom_download_done', on_download_done)
    ui.on('rom_patcher_ready', on_ready)
    ui.timer(0, ask_ready, once=True)
    _watch_loader(state, card.refresh)


def create() -> None:
    @public_page('/patch/{token}', telemetry_path='/patch')
    async def rom_patch(token: str) -> None:
        user = await get_user_from_session(app.storage.user)
        try:
            patch = await RomPatchService.get_by_token(token)
        except NotFoundError:
            from theme.error_page import render_not_found
            await render_not_found(user=user)
            return
        ui.page_title(f'{patch.title} — {await TenantService.current_community_name() or "Wizzrobe"}')
        _add_scripts({
            'mode': 'hosted',
            'patchUrl': f'/rom-patches/{patch.token}/{int(patch.updated_at.timestamp())}.{patch.format}',
            'sourceCrc': patch.source_crc,
            'game': patch.game,
            'outputBase': output_base(patch.title),
        })
        await BaseLayout(user=user).render()
        await _render_hosted(patch)

    @public_page('/patcher')
    async def rom_patcher() -> None:
        user = await get_user_from_session(app.storage.user)
        ui.page_title(f'ROM patcher — {await TenantService.current_community_name() or "Wizzrobe"}')
        _add_scripts({'mode': 'open'})
        await BaseLayout(user=user).render()
        await _render_open()
