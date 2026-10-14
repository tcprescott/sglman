"""``/live``: the Watch page, the one place an online viewer needs.

Every stage's stream in one player, what's on each stage now and next, what's
coming up on stream over the next few days, and every tournament's bracket. It
replaced the Event tab's On Air view, so whoever runs the Schedule board gets a
⋮ "Open in Schedule" on each match their board can show. No sign-in
and no feature flag. A live NiceGUI page by default; when staff set it static,
or a rush of arrivals trips it, ``middleware/watch_mode.py`` answers before this
page is built (see ``pages/static_watch.py``).

The content comes from :func:`pages.watch_data.get_watch_view`, built once per
change for every reader. Each open page polls the shared version every couple of
seconds and repaints from the cached content when it moves, so a hundred viewers
cost one rebuild, not a hundred.
"""

import time

from nicegui import app, context, ui

from application.services import AuthService, TenantService, WatchLayoutService, get_user_from_session
from application.services.watch_layout_service import WATCH_LAYOUTS
from application.tenant_context import require_tenant_id
from application.utils import live_audience
from middleware.auth import public_page
from pages.watch_data import get_watch_view, watch_version
from theme.base import BaseLayout
from theme.notify import notify_error
from theme.page_header import page_header
from theme.watch_live import LiveWatch

#: How often an open page checks whether the content moved.
_POLL_SECONDS = 2.0
#: Repaint at least this often, for what no event announces (a match's time passing).
_REPAINT_SECONDS = 30.0


def create() -> None:
    @public_page('/live')
    async def live_watch() -> None:
        tenant_id = require_tenant_id()
        community = await TenantService.current_community_name() or 'Wizzrobe'
        ui.page_title(f'Watch — {community}')
        user = await get_user_from_session(app.storage.user)
        await BaseLayout(user=user).render()

        view = await get_watch_view(tenant_id)
        # Each viewer lands on a random layout and keeps it (app.storage.user is
        # per browser, signed in or not) until they pick another.
        layout = WatchLayoutService.resolve(app.storage.user.get('watch_layout'))
        app.storage.user['watch_layout'] = layout
        session_id = app.storage.browser.get('id')
        await WatchLayoutService().mark_seen(session_id, layout)
        root_path = context.client.request.scope.get('root_path', '') or ''
        with ui.column().classes('page-container'):
            page_header('Watch', subtitle=f'Times in {view.timezone_label}' if view.timezone_label else None)
            await _layout_bar(layout, session_id)
            live = LiveWatch(root_path, await AuthService.schedule_board_scope(user), layout=layout)
            live.render(view)

        seen = {'version': watch_version(tenant_id), 'at': time.monotonic()}

        async def repaint_if_changed() -> None:
            version = watch_version(tenant_id)
            if version == seen['version'] and time.monotonic() - seen['at'] < _REPAINT_SECONDS:
                return
            seen['version'], seen['at'] = version, time.monotonic()
            live.render(await get_watch_view(tenant_id))

        ui.timer(_POLL_SECONDS, repaint_if_changed)

        client = context.client
        live_audience.viewer_joined(tenant_id, client.id)
        client.on_connect(lambda: live_audience.viewer_joined(tenant_id, client.id))
        client.on_disconnect(lambda: live_audience.viewer_left(tenant_id, client.id))


async def _layout_bar(layout: str, session_id: str | None) -> None:
    """The layout switcher and its thumbs up/down, while the community decides."""
    service = WatchLayoutService()
    mine = {'vote': (await service.votes_for(session_id)).get(layout)}

    def switch(key: str) -> None:
        if key == layout:
            return
        app.storage.user['watch_layout'] = key
        ui.navigate.reload()

    with ui.element('section').classes('wiz-watch-layout').props('aria-label="Page layout"'):
        ui.label("We're trying three layouts. Pick one, and tell us what you think.").classes(
            'wiz-watch-layout__lead')
        with ui.row().classes('wiz-watch-layout__controls items-center'):
            with ui.element('div').classes('wiz-watch-layout__pick').props('role="group" aria-label="Layout"'):
                for key, label in WATCH_LAYOUTS.items():
                    on = key == layout
                    ui.button(label, on_click=lambda k=key: switch(k)).props(
                        f'no-caps {"unelevated" if on else "outline"} aria-pressed={"true" if on else "false"}',
                    ).classes('wiz-watch-layout__option')

            @ui.refreshable
            def thumbs() -> None:
                for vote, icon, name in (('down', 'thumb_down', 'I don\'t like this layout'),
                                         ('up', 'thumb_up', 'I like this layout')):
                    on = mine['vote'] == vote
                    ui.button(icon=icon, on_click=lambda v=vote: cast(v)).props(
                        f'round {"unelevated" if on else "flat"} aria-pressed={"true" if on else "false"} '
                        f'aria-label="{name}"',
                    ).classes('wiz-watch-layout__vote').tooltip(name)

            async def cast(vote: str) -> None:
                new = None if mine['vote'] == vote else vote
                try:
                    await service.vote(session_id, layout, new)
                except ValueError as e:
                    notify_error(e)
                    return
                mine['vote'] = new
                thumbs.refresh()
                if new:
                    ui.notify('Thanks, noted.', color='positive')

            with ui.row().classes('wiz-watch-layout__thumbs items-center no-wrap'):
                thumbs()
