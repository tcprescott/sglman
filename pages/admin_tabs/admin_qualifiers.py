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
from application.utils.duration import format_hms
from application.utils.timezone import format_local_display, parse_local_datetime
from theme.dialog._helpers import native_date_input, native_time_input
from theme.notify import notify_error
from theme.qualifier_copy import BOARD_EXPLAINER
from theme.tables.admin_crud import wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys


def _fmt(dt) -> str:
    return format_local_display(dt) if dt else '—'


def _enum_value(value) -> str:
    return value.value if hasattr(value, 'value') else str(value)


# Terminal run states a reattempt can be granted on — an in-progress run is
# finished or forfeited first.
_GRANTABLE_STATUSES = {'finished', 'forfeit', 'disqualified'}

# ``v-if`` on the row's own flag: a voided or in-progress run offers nothing.
_GRANT_ACTION = '''
    <q-btn v-if="props.row.grantable" flat dense icon="restart_alt" color="primary"
           label="Grant reattempt"
           @click="$parent.$emit('grant', props.row)">
        <q-tooltip>Void this run and free its pool slot</q-tooltip>
    </q-btn>
'''


def _short_url(url: str, limit: int = 60) -> str:
    url = url or ''
    return url if len(url) <= limit else f'{url[:limit]}…'


def _other_runs_summary(all_runs, run) -> str:
    """"Player Two: 2 other runs in this qualifier (1 approved, 1 forfeit)".

    Re-reviewing without seeing a runner's other attempts is how two reviewers
    reach different conclusions about the same person.
    """
    others = [r for r in all_runs if r.user_id == run.user_id and r.id != run.id]
    if not others:
        return ''
    tally: dict[str, int] = {}
    for other in others:
        key = ('voided' if other.reattempted
               else _enum_value(other.review_status) if _enum_value(other.status) == 'finished'
               else _enum_value(other.status))
        tally[key] = tally.get(key, 0) + 1
    breakdown = ', '.join(f'{count} {label}' for label, count in sorted(tally.items()))
    runner = run.user.display_name or run.user.username
    plural = '' if len(others) == 1 else 's'
    return f'{runner}: {len(others)} other run{plural} in this qualifier ({breakdown})'


def _existing_notes(run) -> list:
    notes = list(getattr(run, 'review_notes', []) or [])
    return [n.note for n in notes if getattr(n, 'note', '')]


def _live_race_color(status) -> str:
    return {
        'scheduled': 'grey',
        'pending': 'blue',
        'in_progress': 'orange',
        'finished': 'green',
    }.get(status.value, 'grey')


async def admin_qualifiers_page() -> None:
    service = AsyncQualifierService()
    live_race_service = AsyncQualifierLiveRaceService()
    preset_service = PresetService()
    client = context.client
    state: dict = {'qualifiers': [], 'managing': None, 'detail': None, 'list_error': None}

    async def _current():
        return await get_user_from_discord_id(app.storage.user.get('discord_id'))

    # ---------------------------------------------------------------- loaders

    async def load_list() -> None:
        try:
            state['qualifiers'] = await service.list_qualifiers(await _current())
            state['list_error'] = None
        except PermissionError as e:
            state['qualifiers'] = []
            state['list_error'] = str(e)
        with client:
            list_view.refresh()

    async def load_detail() -> None:
        qid = state.get('managing')
        if qid is None:
            state['detail'] = None
        else:
            current = await _current()
            try:
                state['detail'] = {
                    'qualifier': await service.get_qualifier(current, qid),
                    'pools': await service.list_pools(current, qid),
                    'queue': await service.list_review_queue(current, qid),
                    'runs': await service.list_runs(current, qid),
                    'leaderboard': await service.get_leaderboard(current, qid),
                    'presets': await preset_service.list_selectable(),
                    'live_races': await live_race_service.list_live_races(current, qid),
                }
            except (ValueError, PermissionError) as e:
                state['detail'] = {'error': str(e)}
        with client:
            detail_view.refresh()

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
            ui.label('No qualifiers yet.').classes('text-grey')
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
                    f'Window: {_fmt(q.opens_at)} → {_fmt(q.closes_at)}  ·  '
                    f'Runs/pool: {q.runs_per_pool}  ·  Reattempts: {q.allowed_reattempts}'
                ).classes('text-caption text-grey')
                if q.event_name:
                    ui.label(f'Feeds: {q.event_name}').classes('text-caption text-grey')

    async def _manage(qid: int) -> None:
        state['managing'] = qid
        await load_detail()

    async def _delete_qualifier(qid: int) -> None:
        try:
            await service.delete_qualifier(await _current(), qid)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Qualifier deleted', color='positive')
        if state['managing'] == qid:
            state['managing'] = None
            await load_detail()
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
        detail = state.get('detail')
        if not detail:
            return
        if detail.get('error'):
            ui.label(detail['error']).classes('text-warning')
            return
        qualifier = detail['qualifier']
        ui.separator()
        with ui.row().classes('items-center full-width'):
            ui.label(f'Managing: {qualifier.name}').classes('text-h6')
            ui.space()
            ui.button(icon='close', on_click=_close_manage).props('flat round').tooltip('Close')
        with ui.tabs().classes('w-full') as tabs:
            pools_tab = ui.tab('Pools')
            live_tab = ui.tab('Live Races')
            review_tab = ui.tab('Review Queue')
            runs_tab = ui.tab('Runs')
            board_tab = ui.tab('Leaderboard')
        with ui.tab_panels(tabs, value=pools_tab).classes('w-full'):
            with ui.tab_panel(pools_tab):
                _render_pools(detail)
            with ui.tab_panel(live_tab):
                _render_live_races(detail)
            with ui.tab_panel(review_tab):
                _render_queue(detail['queue'], detail['runs'])
            with ui.tab_panel(runs_tab):
                _render_runs(detail['runs'])
            with ui.tab_panel(board_tab):
                _render_leaderboard(detail['leaderboard'])

    async def _close_manage() -> None:
        state['managing'] = None
        await load_detail()

    def _render_pools(detail: dict) -> None:
        qid = detail['qualifier'].id
        preset_options = {p.id: f'{p.randomizer}/{p.name}' for p in detail['presets']}
        with ui.row().classes('items-center'):
            ui.button('Add Pool', icon='add',
                      on_click=lambda: _open_pool_dialog(qid, preset_options)).props('color=primary')
        if not detail['pools']:
            ui.label('No pools yet — add one, then paste or roll permalinks.').classes('text-grey')
        for pool in detail['pools']:
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
                for pl in permalinks:
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
                    await load_detail()
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
                    await load_detail()
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
                    await load_detail()
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
        await load_detail()

    def _render_live_races(detail: dict) -> None:
        pools = detail['pools']
        with ui.row().classes('items-center'):
            ui.button('New Live Race', icon='add',
                      on_click=lambda: _open_live_race_dialog(pools)
                      ).props('color=primary')
        ui.label(
            'A live race runs a pool permalink synchronously on racetime; each '
            'entrant\'s result is captured as an approved, par-scored run.'
        ).classes('text-caption text-grey')
        if not pools:
            ui.label('Add a pool first, then schedule a live race for it.').classes('text-grey')
            return
        if not detail['live_races']:
            ui.label('No live races scheduled.').classes('text-grey')
        for lr in detail['live_races']:
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(lr.match_title).classes('text-subtitle1')
                    ui.badge(lr.status.value, color=_live_race_color(lr.status))
                    ui.badge(f'pool: {lr.pool.name}', color='grey')
                    ui.space()
                    if not lr.racetime_slug:
                        ui.button('Open room', icon='meeting_room',
                                  on_click=lambda lid=lr.id: _open_room(lid)
                                  ).props('flat color=primary')
                    ui.button(icon='delete',
                              on_click=lambda lid=lr.id: _cancel_live_race(lid)
                              ).props('flat round color=negative').tooltip('Cancel')
                if lr.racetime_slug:
                    ui.label(f'racetime: {lr.racetime_slug}').classes('text-caption text-grey')

    def _open_live_race_dialog(pools) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
            ui.label('New Live Race').classes('text-h6')
            title_in = ui.input('Race title').classes('w-full')
            pool_options = {p.id: p.name for p in pools}
            pool_in = ui.select(pool_options, label='Pool',
                                value=pools[0].id if pools else None).classes('w-full')
            permalink_options = {None: '(assign later)'}
            for p in pools:
                for pl in p.permalinks:
                    permalink_options[pl.id] = f'{p.name}: {pl.url[:48]}'
            permalink_in = ui.select(permalink_options, label='Permalink (optional)',
                                     value=None).classes('w-full')

            async def submit():
                try:
                    await live_race_service.create_live_race(
                        await _current(), int(pool_in.value),
                        match_title=title_in.value, permalink_id=permalink_in.value,
                    )
                    ui.notify('Live race scheduled', color='positive')
                    dialog.close()
                    await load_detail()
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Create', icon='add', on_click=submit).props('color=primary')
        dialog.open()

    async def _open_room(live_race_id: int) -> None:
        try:
            await live_race_service.open_room(await _current(), live_race_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Room opened', color='positive')
        await load_detail()

    async def _cancel_live_race(live_race_id: int) -> None:
        try:
            await live_race_service.cancel_live_race(await _current(), live_race_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Live race cancelled', color='positive')
        await load_detail()

    def _render_queue(queue, all_runs=()) -> None:
        if not queue:
            ui.label('No runs awaiting review.').classes('text-grey')
            return
        for run in queue:
            runner = run.user.display_name or run.user.username
            pool_name = run.permalink.pool.name if run.permalink and run.permalink.pool else '—'
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(runner).classes('text-subtitle1')
                    ui.badge(format_hms(run.elapsed_seconds), color='blue')
                    ui.badge(pool_name, color='grey')
                    if run.review_claimed_by_id:
                        ui.badge('claimed', color='orange')
                    ui.space()
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
                ui.label(f'Started {_fmt(run.started_at)} · Finished {_fmt(run.finished_at)}').classes(
                    'text-caption text-grey')
                if run.permalink:
                    ui.link(f'Permalink played: {_short_url(run.permalink.url)}',
                            run.permalink.url, new_tab=True).classes('text-caption')
                if run.runner_vod_url:
                    ui.link('VoD', run.runner_vod_url, new_tab=True).classes('text-caption')
                others = _other_runs_summary(all_runs, run)
                if others:
                    ui.label(others).classes('text-caption text-grey')
                for note in _existing_notes(run):
                    ui.label(f'Note — {note}').classes('text-caption text-italic')

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
                await load_detail()

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

    def _render_runs(runs) -> None:
        """Every run, because a forfeit never reaches the review queue.

        A forfeit is written straight to approved/score 0, so this list is the
        only place a reviewer can find a mis-clicked one and grant a reattempt.
        """
        if not runs:
            ui.label('No runs yet.').classes('text-grey')
            return
        columns = [
            {'name': 'player', 'label': 'Player', 'field': 'player', 'align': 'left',
             'sortable': True},
            {'name': 'pool', 'label': 'Pool', 'field': 'pool', 'align': 'left',
             'sortable': True},
            {'name': 'status', 'label': 'Status', 'field': 'status', 'sortable': True},
            {'name': 'review', 'label': 'Review', 'field': 'review', 'sortable': True},
            # HH:MM:SS is zero-padded, so a lexical sort is a chronological one.
            {'name': 'claimed', 'label': 'Claimed', 'field': 'claimed', 'sortable': True},
            {'name': 'timed', 'label': 'Timed', 'field': 'timed', 'sortable': True},
            {'name': 'score', 'label': 'Score', 'field': 'score', 'sortable': True},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]
        rows = []
        for run in runs:
            rows.append({
                'id': run.id,
                'player': run.user.display_name or run.user.username,
                'pool': (run.permalink.pool.name if run.permalink and run.permalink.pool else '—'),
                'status': _enum_value(run.status) + (' (voided)' if run.reattempted else ''),
                'review': _enum_value(run.review_status),
                'claimed': format_hms(run.elapsed_seconds),
                'timed': format_hms(run.measured_seconds),
                'score': '' if run.score is None else round(run.score, 1),
                'grantable': (not run.reattempted
                              and _enum_value(run.status) in _GRANTABLE_STATUSES),
            })
        by_id = {r.id: r for r in runs}
        table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full wiz-table')
        table.add_slot('body-cell-actions', f'<q-td :props="props">{_GRANT_ACTION}</q-td>')
        table.on('grant', lambda e: _open_grant_dialog(by_id.get(e.args.get('id'))))
        enable_mobile_grid(table, columns, actions=_GRANT_ACTION,
                           table_key=TableKeys.ADMIN_QUALIFIERS)

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
                await load_detail()

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                grant = ui.button('Grant reattempt', icon='restart_alt', on_click=submit)
                grant.props('color=primary')
                grant.bind_enabled_from(reason_in, 'value', lambda v: bool((v or '').strip()))
        dialog.open()

    def _render_leaderboard(entries) -> None:
        if not entries:
            ui.label('No scored runs yet.').classes('text-grey')
            return
        columns = [
            {'name': 'rank', 'label': '#', 'field': 'rank', 'sortable': True},
            {'name': 'user', 'label': 'Player', 'field': 'user', 'align': 'left',
             'sortable': True},
            {'name': 'actual', 'label': 'Score', 'field': 'actual', 'sortable': True},
            {'name': 'estimate', 'label': 'Estimate', 'field': 'estimate', 'sortable': True},
            # Not sortable: 'filled/total' is a composite, and 2/9 would sort above 10/10.
            {'name': 'slots', 'label': 'Slots', 'field': 'slots'},
        ]
        rows = [
            {'rank': i + 1, 'user': e.username, 'actual': e.actual,
             'estimate': e.estimate, 'slots': f'{e.slots_filled}/{e.slots_total}'}
            for i, e in enumerate(entries)
        ]
        table = ui.table(columns=columns, rows=rows, row_key='rank').classes('w-full wiz-table')
        enable_mobile_grid(table, columns,
                           table_key=TableKeys.ADMIN_QUALIFIER_LEADERBOARD)
        ui.label(BOARD_EXPLAINER).classes('text-caption text-grey')

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
