"""Admin Async Qualifiers page — create/administer qualifiers, author pools, review runs.

Gated by ``QUALIFIER_ADMIN``/STAFF (or a per-qualifier admin). Mirrors the
Tournaments admin pattern: a list of qualifiers with a create/edit dialog, plus a
"Manage" drill-down that authors pools/permalinks, works the reviewer queue, and
shows the leaderboard.

Rendering follows the ``service_health_view`` pattern: sync ``@ui.refreshable``
views read from ``state``; async loaders fetch, stash into ``state``, and restore
the captured client (``with client:``) before ``.refresh()``. Mutating handlers
run directly from ``on_click`` (event context has a slot) so ``ui.notify`` is safe
without a background task.
"""

from nicegui import app, context, ui

from application.services import (
    AsyncQualifierLiveRaceService,
    AsyncQualifierService,
    PresetService,
    get_user_from_discord_id,
)
from application.services.async_qualifier.async_qualifier_rules import ClaimVerdict, classify_claim
from application.tenant_context import require_tenant_id, tenant_scope
from application.utils.duration import format_hms
from application.utils.timezone import parse_local_datetime
from pages.admin_tabs.admin_qualifiers.live_races import build_live_tab
from pages.admin_tabs.admin_qualifiers.shared import (
    BOARD_COLUMNS,
    BOARD_PAGE,
    BOARD_TAB,
    GRANT_ACTION,
    LIVE_TAB,
    POOL_PERMALINK_PREVIEW,
    POOLS_TAB,
    QUEUE_PAGE_SIZE,
    QUEUE_TAB,
    RUNS_COLUMNS,
    RUNS_PAGE,
    RUNS_TAB,
    board_rows,
    claim_holder,
    enum_value,
    existing_notes,
    fmt,
    other_runs_summary,
    run_rows,
    short_url,
)
from theme.dialog._helpers import native_date_input, native_time_input
from theme.notify import notify_error
from theme.qualifier_copy import BOARD_EXPLAINER
from theme.tables.admin_crud import wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys, row_count_label, search_input, sticky_header


async def admin_qualifiers_page() -> None:
    service = AsyncQualifierService()
    live_race_service = AsyncQualifierLiveRaceService()
    preset_service = PresetService()
    client = context.client
    # Captured at page build, where a request tenant is guaranteed; every
    # later handler re-binds it rather than re-resolving.
    tenant_id = require_tenant_id()
    state: dict = {
        'qualifiers': [], 'managing': None, 'shell': None, 'list_error': None,
        # The drill-down loads one tab at a time. 'loaded' is which tabs have their
        # data, 'errors' is the per-tab refusal to render in place of it, and 'tab'
        # survives a rebuild so a verdict does not throw the reviewer back to Pools.
        'tab': POOLS_TAB, 'loaded': set(), 'errors': {}, 'queue_shown': QUEUE_PAGE_SIZE,
        'pools': [], 'presets': [], 'live_races': [], 'queue': [], 'queue_context': {},
        'runs': [], 'board': [], 'viewer_id': None,
    }

    # name → the refreshable that renders it. Filled in once the views are defined
    # (they close over ``state``, so they cannot be declared before it).
    _TAB_VIEWS: dict = {}

    async def _current():
        return await get_user_from_discord_id(app.storage.user.get('discord_id'))

    # ---------------------------------------------------------------- loaders

    async def load_list() -> None:
        try:
            with tenant_scope(tenant_id):
                state['qualifiers'] = await service.list_qualifiers(await _current())
            state['list_error'] = None
        except PermissionError as e:
            state['qualifiers'] = []
            state['list_error'] = str(e)
        with client:
            list_view.refresh()

    async def _fetch_pools(current, qid) -> None:
        state['pools'] = await service.list_pools(current, qid)
        state['presets'] = await preset_service.list_selectable()

    async def _fetch_live(current, qid) -> None:
        state['live_races'] = await live_race_service.list_live_races(current, qid)
        if POOLS_TAB not in state['loaded']:
            # The New Live Race dialog picks a pool and one of its permalinks, so
            # this tab cannot render its own control without them.
            await _fetch_pools(current, qid)
            state['loaded'].add(POOLS_TAB)

    async def _fetch_queue(current, qid) -> None:
        state['queue'] = await service.list_review_queue(current, qid)
        state['queue_context'] = await service.review_queue_context(current, qid, state['queue'])
        state['queue_shown'] = QUEUE_PAGE_SIZE
        # Whose claims count as "mine" on the cards. Stashed rather than re-read
        # per card: the view is sync and cannot await.
        state['viewer_id'] = current.id if current is not None else None

    async def _fetch_runs(current, qid) -> None:
        state['runs'] = await service.list_runs(current, qid)

    async def _fetch_board(current, qid) -> None:
        state['board'] = await service.get_leaderboard(current, qid)

    _FETCH = {
        POOLS_TAB: _fetch_pools,
        LIVE_TAB: _fetch_live,
        QUEUE_TAB: _fetch_queue,
        RUNS_TAB: _fetch_runs,
        BOARD_TAB: _fetch_board,
    }

    async def load_shell() -> None:
        """The drill-down's header, and nothing else.

        Opening Manage used to pay for the qualifier, its pools, the review queue,
        every run, the leaderboard, every preset and every live race — sequentially,
        and again after every single mutation. Each tab now fetches its own data the
        first time it is selected, and a verdict reloads the queue rather than the
        tournament.
        """
        qid = state.get('managing')
        state['loaded'] = set()
        state['errors'] = {}
        if qid is None:
            state['shell'] = None
        else:
            try:
                with tenant_scope(tenant_id):
                    state['shell'] = {
                        'qualifier': await service.get_qualifier(await _current(), qid)}
            except (ValueError, PermissionError) as e:
                state['shell'] = {'error': str(e)}
        with client:
            detail_view.refresh()
        if state.get('shell') and not state['shell'].get('error'):
            await load_tab(state['tab'])

    async def load_tab(name: str, *, force: bool = False) -> None:
        """Fetch one tab's data if it does not have it, then refresh only that tab.

        A refusal is stashed per tab and rendered in place rather than notified:
        this also runs from ``load_shell``, where there is no event slot to notify
        into.
        """
        qid = state.get('managing')
        if qid is None or name not in _FETCH:
            return
        if not force and name in state['loaded']:
            return
        try:
            # Scope the reads explicitly rather than leaning on the client-stash
            # fallback, the same reason pages/brackets.py does: the tenant
            # contextvar is unset in a handler, so `get_current_tenant_id` falls
            # back to `app.storage.client`, which is not reachable across a chain
            # of awaited reloads in one handler. Measured: a mutation reloading
            # three tabs read tenant 1, 1, then None — and a None tenant makes
            # every feature flag read as off, so the third tab rendered "the Async
            # Qualifiers feature is not enabled for this community".
            with tenant_scope(tenant_id):
                await _FETCH[name](await _current(), qid)
            state['errors'].pop(name, None)
        except (ValueError, PermissionError) as e:
            state['errors'][name] = str(e)
        state['loaded'].add(name)
        with client:
            _TAB_VIEWS[name].refresh()

    async def reload_open_tabs(*names: str) -> None:
        """Re-fetch the tabs a mutation invalidated, skipping any not yet opened.

        A pool edit moves the board and the runs list too, but reloading a tab
        nobody has looked at buys nothing — it is fetched on selection anyway.
        """
        for name in names:
            if name in state['loaded']:
                await load_tab(name, force=True)

    # ------------------------------------------------------------ list view

    @ui.refreshable
    def list_view() -> None:
        if state['list_error']:
            ui.label(state['list_error']).classes('text-warning')
            return
        with ui.row().classes('full-width items-center'):
            ui.button('New Qualifier', icon='add',
                      on_click=lambda: open_qualifier_dialog()).props('color=primary')
            ui.space()
            ui.button(icon='refresh',
                      on_click=load_list).props('flat color=primary').tooltip('Refresh')
        if not state['qualifiers']:
            ui.label('No qualifiers yet. Create one to get started.').classes('text-grey')
        for q in state['qualifiers']:
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(q.name).classes('text-h6')
                    ui.badge('Active' if q.is_active else 'Inactive',
                             color='green' if q.is_active else 'grey')
                    ui.space()
                    ui.button('Manage', icon='tune',
                              on_click=lambda qid=q.id: _manage(qid)).props('flat color=primary')
                    ui.button(icon='edit',
                              on_click=lambda row=q: open_qualifier_dialog(row)
                              ).props('flat round color=primary').tooltip('Edit')
                    ui.button(icon='delete',
                              on_click=lambda qid=q.id: _delete_qualifier(qid)
                              ).props('flat round color=negative').tooltip('Delete')
                ui.label(
                    f'Window: {fmt(q.opens_at)} → {fmt(q.closes_at)}  ·  '
                    f'Runs/pool: {q.runs_per_pool}  ·  Reattempts: {q.allowed_reattempts}'
                ).classes('text-caption text-grey')
                if q.event_name:
                    ui.label(f'Feeds: {q.event_name}').classes('text-caption text-grey')

    async def _manage(qid: int) -> None:
        state['managing'] = qid
        await load_shell()

    async def _delete_qualifier(qid: int) -> None:
        try:
            await service.delete_qualifier(await _current(), qid)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Qualifier deleted', color='positive')
        if state['managing'] == qid:
            state['managing'] = None
            await load_shell()
        await load_list()

    def open_qualifier_dialog(existing=None) -> None:
        is_edit = existing is not None
        with ui.dialog() as dialog, ui.card().classes('w-[38rem]'):
            ui.label('Edit Qualifier' if is_edit else 'New Qualifier').classes('text-h6')
            name_in = ui.input('Name', value=existing.name if is_edit else '').classes('w-full')
            event_in = ui.input(
                'Feeds event (optional)', value=(existing.event_name or '') if is_edit else ''
            ).classes('w-full')
            desc_in = ui.textarea(
                'Description', value=(existing.description or '') if is_edit else ''
            ).classes('w-full').props('rows=2')
            ui.label('Window (leave a date blank for open-ended)').classes('text-caption text-grey')
            with ui.row().classes('w-full'):
                opens_date = native_date_input('Opens date').classes('flex-1')
                opens_time = native_time_input('Opens time', '00:00').classes('flex-1')
            with ui.row().classes('w-full'):
                closes_date = native_date_input('Closes date').classes('flex-1')
                closes_time = native_time_input('Closes time', '23:59').classes('flex-1')
            with ui.row().classes('w-full'):
                rpp_in = ui.number('Runs per pool', value=existing.runs_per_pool if is_edit else 1,
                                   min=1, precision=0).classes('flex-1')
                reattempts_in = ui.number('Allowed reattempts',
                                          value=existing.allowed_reattempts if is_edit else 0,
                                          min=0, precision=0).classes('flex-1')
            active_in = ui.switch('Active', value=existing.is_active if is_edit else True)

            def _parse(date_in, time_in):
                if not date_in.value:
                    return None
                return parse_local_datetime(date_in.value, time_in.value or '00:00')

            async def submit():
                try:
                    opens_at = _parse(opens_date, opens_time)
                    closes_at = _parse(closes_date, closes_time)
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    return
                try:
                    current = await _current()
                    if is_edit:
                        await service.update_qualifier(
                            current, existing.id,
                            name=name_in.value, event_name=event_in.value,
                            description=desc_in.value, opens_at=opens_at, closes_at=closes_at,
                            runs_per_pool=int(rpp_in.value or 1),
                            allowed_reattempts=int(reattempts_in.value or 0),
                            is_active=active_in.value,
                        )
                        ui.notify('Qualifier updated', color='positive')
                    else:
                        await service.create_qualifier(
                            current, name=name_in.value, event_name=event_in.value,
                            description=desc_in.value, opens_at=opens_at, closes_at=closes_at,
                            runs_per_pool=int(rpp_in.value or 1),
                            allowed_reattempts=int(reattempts_in.value or 0),
                        )
                        ui.notify('Qualifier created', color='positive')
                    dialog.close()
                    await load_list()
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save' if is_edit else 'Create', icon='save',
                          on_click=submit).props('color=primary')
        dialog.open()

    # ---------------------------------------------------------- detail view

    @ui.refreshable
    def detail_view() -> None:
        shell = state.get('shell')
        if not shell:
            return
        if shell.get('error'):
            ui.label(shell['error']).classes('text-warning')
            return
        qualifier = shell['qualifier']
        ui.separator()
        with ui.row().classes('items-center full-width'):
            ui.label(f'Managing: {qualifier.name}').classes('text-h6')
            ui.space()
            ui.button(icon='close', on_click=_close_manage).props('flat round').tooltip('Close')
        with ui.tabs().classes('w-full') as tabs:
            for name in (POOLS_TAB, LIVE_TAB, QUEUE_TAB, RUNS_TAB, BOARD_TAB):
                ui.tab(name)
        # Selecting a tab is what fetches it, so the drill-down opens on one read
        # instead of seven. The value comes from state so a rebuild lands back where
        # the reviewer was.
        tabs.on_value_change(lambda e: _select_tab(e.value))
        with ui.tab_panels(tabs, value=state['tab']).classes('w-full'):
            with ui.tab_panel(POOLS_TAB):
                pools_view()
            with ui.tab_panel(LIVE_TAB):
                live_view()
            with ui.tab_panel(QUEUE_TAB):
                queue_view()
            with ui.tab_panel(RUNS_TAB):
                runs_view()
            with ui.tab_panel(BOARD_TAB):
                board_view()

    async def _select_tab(name) -> None:
        name = getattr(name, 'name', name)
        if not isinstance(name, str):
            return
        state['tab'] = name
        await load_tab(name)

    def _tab_placeholder(name: str) -> bool:
        """Render a tab's error or its not-yet-loaded state; True when it handled it."""
        if state['errors'].get(name):
            ui.label(state['errors'][name]).classes('text-warning')
            return True
        if name not in state['loaded']:
            ui.skeleton().classes('w-full h-8')
            return True
        return False

    # The one tab whose service and external system are its own; built here rather
    # than inline because it needs the loaders defined above.
    live_view = build_live_tab(
        state=state, service=live_race_service, current=_current,
        reload_tabs=reload_open_tabs, placeholder=_tab_placeholder,
        notify_error=notify_error,
    )

    async def _close_manage() -> None:
        state['managing'] = None
        await load_shell()

    @ui.refreshable
    def pools_view() -> None:
        if state.get('shell') is None or _tab_placeholder(POOLS_TAB):
            return
        qid = state['managing']
        preset_options = {p.id: f'{p.randomizer}/{p.name}' for p in state['presets']}
        with ui.row().classes('items-center'):
            ui.button('Add Pool', icon='add',
                      on_click=lambda: _open_pool_dialog(qid, preset_options)).props('color=primary')
        if not state['pools']:
            ui.label('No pools yet — add one, then paste or roll permalinks.').classes('text-grey')
        for pool in state['pools']:
            permalinks = list(pool.permalinks)
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(pool.name).classes('text-subtitle1')
                    ui.badge(f'{len(permalinks)} permalink(s)', color='blue')
                    if pool.preset:
                        ui.badge(f'preset: {pool.preset.randomizer}/{pool.preset.name}', color='grey')
                    ui.space()
                    ui.button('Add permalinks', icon='playlist_add',
                              on_click=lambda pid=pool.id: _open_permalinks_dialog(pid)
                              ).props('flat color=primary')
                    if pool.preset:
                        ui.button('Roll', icon='casino',
                                  on_click=lambda pid=pool.id: _open_roll_dialog(pid)
                                  ).props('flat color=primary')
                    ui.button(icon='delete',
                              on_click=lambda pid=pool.id: _delete_pool(pid)
                              ).props('flat round color=negative').tooltip('Delete pool')
                for pl in permalinks[:POOL_PERMALINK_PREVIEW]:
                    _permalink_row(pl)
                # A pool holds as many seeds as the organiser rolled, and every one
                # of them is a row of widgets. The tail is there when it is wanted.
                rest = permalinks[POOL_PERMALINK_PREVIEW:]
                if rest:
                    with ui.expansion(f'Show {len(rest)} more permalink(s)'
                                      ).classes('w-full text-caption'):
                        for pl in rest:
                            _permalink_row(pl)

    def _permalink_row(pl) -> None:
        with ui.row().classes('items-center'):
            ui.badge('live' if pl.live_race else 'async',
                     color='purple' if pl.live_race else 'teal')
            ui.link(pl.url, pl.url, new_tab=True).classes('text-caption')
            if pl.par_time:
                ui.badge(f'par {format_hms(pl.par_time)}', color='green')

    def _open_pool_dialog(qid: int, preset_options: dict) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[30rem]'):
            ui.label('Add Pool').classes('text-h6')
            name_in = ui.input('Pool name').classes('w-full')
            options = {None: '(no preset)', **preset_options}
            preset_in = ui.select(options, label='Preset (optional)', value=None).classes('w-full')

            async def submit():
                try:
                    await service.create_pool(await _current(), qid,
                                              name=name_in.value, preset_id=preset_in.value)
                    ui.notify('Pool added', color='positive')
                    dialog.close()
                    # A pool is a slot per entrant, so the board's totals move too.
                    await reload_open_tabs(POOLS_TAB, LIVE_TAB, BOARD_TAB)
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Add', icon='add', on_click=submit).props('color=primary')
        dialog.open()

    def _open_permalinks_dialog(pool_id: int) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[34rem]'):
            ui.label('Add Permalinks').classes('text-h6')
            ui.label('One URL per line.').classes('text-caption text-grey')
            urls_in = ui.textarea('Permalink URLs').classes('w-full font-mono').props('rows=8')

            async def submit():
                lines = (urls_in.value or '').splitlines()
                try:
                    created = await service.add_permalinks_bulk(await _current(), pool_id, urls=lines)
                    ui.notify(f'Added {len(created)} permalink(s)', color='positive')
                    dialog.close()
                    # A pool that had only live-race seeds becomes runnable, which
                    # is a board change as well as a pool one.
                    await reload_open_tabs(POOLS_TAB, LIVE_TAB, BOARD_TAB)
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Add', icon='add', on_click=submit).props('color=primary')
        dialog.open()

    def _open_roll_dialog(pool_id: int) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[26rem]'):
            ui.label('Roll Permalinks').classes('text-h6')
            count_in = ui.number('How many', value=5, min=1, max=25, precision=0).classes('w-full')

            async def submit():
                try:
                    created = await service.roll_permalinks(
                        await _current(), pool_id, count=int(count_in.value or 1))
                    ui.notify(f'Rolled {len(created)} permalink(s)', color='positive')
                    dialog.close()
                    await reload_open_tabs(POOLS_TAB, LIVE_TAB, BOARD_TAB)
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Roll', icon='casino', on_click=submit).props('color=primary')
        dialog.open()

    async def _delete_pool(pool_id: int) -> None:
        try:
            await service.delete_pool(await _current(), pool_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Pool deleted', color='positive')
        # Deleting a pool cascades its permalinks and detaches their runs, so the
        # runs list and the board both move.
        await reload_open_tabs(POOLS_TAB, LIVE_TAB, BOARD_TAB, RUNS_TAB)

    @ui.refreshable
    def queue_view() -> None:
        if state.get('shell') is None or _tab_placeholder(QUEUE_TAB):
            return
        queue = state['queue']
        if not queue:
            ui.label('No runs awaiting review.').classes('text-grey')
            return
        shown = min(state['queue_shown'], len(queue))
        with ui.row().classes('items-center w-full'):
            ui.label(f'{len(queue)} awaiting review').classes('text-caption text-grey-7')
        me = state.get('viewer_id')
        for run in queue[:shown]:
            runner = run.user.display_name or run.user.username
            pool_name = run.permalink.pool.name if run.permalink and run.permalink.pool else '—'
            holder = claim_holder(run)
            mine = run.review_claimed_by_id == me
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(runner).classes('text-subtitle1')
                    ui.badge(format_hms(run.elapsed_seconds), color='blue')
                    ui.badge(pool_name, color='grey')
                    if holder:
                        ui.badge('you have this' if mine else f'{holder} has this',
                                 color='orange' if mine else 'negative')
                    ui.space()
                    # A claim is a real lock since F5, so the card offers the way in
                    # and the way out — a lock nobody can release is a stuck run.
                    if holder and not mine:
                        # No verdict buttons at all, rather than disabled ones. A
                        # `disable()`d Quasar flat button keeps its colour at 0.7
                        # opacity, which reads as live: the reviewer clicks Approve,
                        # nothing happens, and the reason is hidden in a tooltip.
                        # Release is the only thing they can actually do here.
                        ui.button('Release', icon='lock_open',
                                  on_click=lambda r=run: _release_claim(r)
                                  ).props('flat color=warning').tooltip(
                            f'{holder} is reviewing this run. Release it if they are done.')
                    else:
                        if not holder:
                            ui.button('Claim', icon='lock',
                                      on_click=lambda r=run: _claim_run(r)
                                      ).props('flat color=primary')
                        ui.button('Approve', icon='check',
                                  on_click=lambda r=run: _open_review_dialog(r, True)
                                  ).props('flat color=positive')
                        ui.button('Reject', icon='close',
                                  on_click=lambda r=run: _open_review_dialog(r, False)
                                  ).props('flat color=negative')
                with ui.row().classes('items-center gap-2'):
                    ui.label(f'Claimed {format_hms(run.elapsed_seconds)}  ·  '
                             f'Timed {format_hms(run.measured_seconds)}').classes(
                        'text-caption text-grey')
                    if classify_claim(run.elapsed_seconds or 0,
                                      run.measured_seconds) is ClaimVerdict.IMPLAUSIBLE:
                        drift = run.measured_seconds - (run.elapsed_seconds or 0)
                        ui.badge(f'drift {format_hms(drift)}', color='orange').tooltip(
                            'The runner confirmed this time against their own timer.')
                ui.label(f'Started {fmt(run.started_at)} · Finished {fmt(run.finished_at)}').classes(
                    'text-caption text-grey')
                if run.permalink:
                    ui.link(f'Permalink played: {short_url(run.permalink.url)}',
                            run.permalink.url, new_tab=True).classes('text-caption')
                if run.runner_vod_url:
                    ui.link('VoD', run.runner_vod_url, new_tab=True).classes('text-caption')
                others = other_runs_summary(state['queue_context'], run)
                if others:
                    ui.label(others).classes('text-caption text-grey')
                for note in existing_notes(run):
                    ui.label(f'Note — {note}').classes('text-caption text-italic')
        if shown < len(queue):
            ui.button(f'Show {min(QUEUE_PAGE_SIZE, len(queue) - shown)} more',
                      icon='expand_more', on_click=_show_more_queue).props('flat color=primary')

    def _show_more_queue() -> None:
        state['queue_shown'] += QUEUE_PAGE_SIZE
        queue_view.refresh()

    async def _claim_run(run) -> None:
        try:
            await service.claim_run(await _current(), run.id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
        await load_tab(QUEUE_TAB, force=True)

    async def _release_claim(run) -> None:
        try:
            await service.release_claim(await _current(), run.id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
        await load_tab(QUEUE_TAB, force=True)

    def _open_review_dialog(run, approved: bool) -> None:
        """One dialog for both verdicts so the two paths cannot drift.

        A rejection's reason is required — the service refuses one without, and
        what the reviewer types is what the runner is told.
        """
        verb = 'Approve' if approved else 'Reject'
        runner = run.user.display_name or run.user.username
        with ui.dialog() as dialog, ui.card().classes('w-[34rem]'):
            ui.label(f'{verb} {runner}\u2019s run').classes('text-h6')
            note_in = ui.textarea(
                'Note (optional)' if approved else 'Reason (shown to the runner)'
            ).classes('w-full').props('rows=3')

            async def submit() -> None:
                try:
                    await service.review_run(
                        await _current(), run.id, approved=approved, note=note_in.value,
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Run approved' if approved else 'Run rejected', color='positive')
                dialog.close()
                # A settled run leaves the queue by definition, so drop its card
                # rather than re-reading the queue to be told the same thing. The
                # reviewer keeps their place and the next card is already there.
                state['queue'] = [r for r in state['queue'] if r.id != run.id]
                with client:
                    queue_view.refresh()
                # The verdict recomputes that permalink's par and rescores every
                # approved run on it, so these two really did change.
                await reload_open_tabs(BOARD_TAB, RUNS_TAB)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                confirm = ui.button(f'{verb} run', icon='check' if approved else 'close',
                                    on_click=submit)
                confirm.props(f'color={"positive" if approved else "negative"}')
                if not approved:
                    # Belt as well as braces: the service is the authority, but a
                    # disabled button explains the rule before the click.
                    confirm.bind_enabled_from(note_in, 'value', lambda v: bool((v or '').strip()))
        dialog.open()

    @ui.refreshable
    def runs_view() -> None:
        """Every run, because a forfeit never reaches the review queue.

        A forfeit is written straight to approved/score 0, so this list is the
        only place a reviewer can find a mis-clicked one and grant a reattempt.
        """
        if state.get('shell') is None or _tab_placeholder(RUNS_TAB):
            return
        runs = state['runs']
        if not runs:
            ui.label('No runs yet. Check back once qualifiers start.').classes('text-grey')
            return
        columns = list(RUNS_COLUMNS)
        rows = run_rows(runs)
        by_id = {r.id: r for r in runs}
        toolbar = ui.row().classes('items-center w-full')
        table = ui.table(columns=columns, rows=rows, row_key='id',
                         pagination=RUNS_PAGE).classes('w-full wiz-table')
        # This is the only place a mis-clicked forfeit can be found, and a real
        # qualifier holds thousands of runs — so the way in is a name, not a scroll.
        with toolbar:
            search_input(table, placeholder='Find a player or pool…')
            ui.space()
            row_count_label(table, 'runs')
        sticky_header(table)
        table.add_slot('body-cell-actions', f'<q-td :props="props">{GRANT_ACTION}</q-td>')
        table.on('grant', lambda e: _open_grant_dialog(by_id.get(e.args.get('id'))))
        table.on('override', lambda e: _open_override_dialog(by_id.get(e.args.get('id'))))
        enable_mobile_grid(table, columns, actions=GRANT_ACTION,
                           table_key=TableKeys.ADMIN_QUALIFIERS)

    def _open_override_dialog(run) -> None:
        """Reverse a settled verdict — the only surface that can, since the queue
        holds only pending runs."""
        if run is None:
            return
        runner = run.user.display_name or run.user.username
        was = enum_value(run.review_status)
        approve = was != 'approved'
        with ui.dialog() as dialog, ui.card().classes('w-[34rem]'):
            ui.label(f'Change the verdict on {runner}’s run').classes('text-h6')
            ui.label(
                f'This run is {was}. Overturning it {"approves" if approve else "rejects"} '
                'it instead, tells the runner their earlier result changed, and records '
                'who changed it.'
            ).classes('text-caption text-grey')
            reason_in = ui.textarea('Reason (shown to the runner)').classes('w-full').props('rows=3')

            async def submit() -> None:
                try:
                    await service.review_run(
                        await _current(), run.id, approved=approve,
                        note=reason_in.value, override=True,
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Verdict changed', color='positive')
                dialog.close()
                await reload_open_tabs(RUNS_TAB, BOARD_TAB, QUEUE_TAB)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                confirm = ui.button(
                    f'{"Approve" if approve else "Reject"} instead', icon='gavel',
                    on_click=submit,
                ).props('color=warning')
                confirm.bind_enabled_from(reason_in, 'value', lambda v: bool((v or '').strip()))
        dialog.open()

    def _open_grant_dialog(run) -> None:
        if run is None:
            return
        runner = run.user.display_name or run.user.username
        with ui.dialog() as dialog, ui.card().classes('w-[34rem]'):
            ui.label(f'Grant {runner} another attempt').classes('text-h6')
            ui.label('This voids the run and frees its pool slot. It does not use up '
                     'the runner\u2019s own reattempt allowance.').classes('text-caption text-grey')
            reason_in = ui.textarea('Reason (shown to the runner)').classes('w-full').props('rows=2')

            async def submit() -> None:
                try:
                    await service.grant_reattempt(
                        await _current(), run.id, reason=reason_in.value,
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Reattempt granted', color='positive')
                dialog.close()
                # Voiding a run refreshes its permalink's par, which rescores every
                # approved run on that seed.
                await reload_open_tabs(RUNS_TAB, QUEUE_TAB, BOARD_TAB)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                grant = ui.button('Grant reattempt', icon='restart_alt', on_click=submit)
                grant.props('color=primary')
                grant.bind_enabled_from(reason_in, 'value', lambda v: bool((v or '').strip()))
        dialog.open()

    @ui.refreshable
    def board_view() -> None:
        if state.get('shell') is None or _tab_placeholder(BOARD_TAB):
            return
        entries = state['board']
        if not entries:
            ui.label('No scored runs yet.').classes('text-grey')
            return
        columns = list(BOARD_COLUMNS)
        rows = board_rows(entries)
        toolbar = ui.row().classes('items-center w-full')
        # Keyed by player, not by rank: ranks are now shared on a tie.
        table = ui.table(columns=columns, rows=rows, row_key='user',
                         pagination=BOARD_PAGE).classes('w-full wiz-table')
        with toolbar:
            search_input(table, placeholder='Find a player…')
            ui.space()
            row_count_label(table, 'players')
        sticky_header(table)
        enable_mobile_grid(table, columns,
                           table_key=TableKeys.ADMIN_QUALIFIER_LEADERBOARD)
        ui.label(BOARD_EXPLAINER).classes('text-caption text-grey')

    # Bound after the views exist; ``load_tab`` reads it by name, and every call
    # happens from a handler long after this module-level wiring has run.
    _TAB_VIEWS.update({
        POOLS_TAB: pools_view,
        LIVE_TAB: live_view,
        QUEUE_TAB: queue_view,
        RUNS_TAB: runs_view,
        BOARD_TAB: board_view,
    })

    # ------------------------------------------------------------------ shell

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Async Qualifiers').classes('page-title')
        ui.separator().classes('separator-spacing')
        ui.label(
            'Self-paced permalink-pool qualifiers — a peer of Tournaments. Create a '
            'qualifier, author permalink pools, then review submitted runs. The '
            'leaderboard and pools stay hidden from players until the qualifier closes.'
        ).classes('text-caption text-grey')
        list_view()
        detail_view()

    await load_list()
    wire_tab_refresh('Qualifiers', load_list)
