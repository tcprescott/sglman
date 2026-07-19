"""Player-facing Async Qualifier pages — list, run execution, and leaderboard.

- ``/qualifiers`` lists active qualifiers.
- ``/qualifiers/{qualifier_id}`` is the run surface: pick an eligible pool → an
  atomic draw reveals a spoiler-safe permalink and starts a server-timed run →
  submit finish time + VoD (→ review) or forfeit. It also shows the player's own
  runs and the leaderboard — which stays hidden until the qualifier closes
  (active-window information lockdown), except for staff.
"""

from datetime import datetime, timezone

from nicegui import app, ui
from middleware.auth import protected_page

from application.services import AsyncQualifierService, AuthService, TenantService, get_user_from_discord_id
from application.utils.timezone import format_eastern_display
from models import FeatureFlag
from theme.base import BaseLayout
from theme.tables.mobile_grid import enable_mobile_grid


def _fmt(dt) -> str:
    return format_eastern_display(dt) if dt else '—'


def _fmt_hms(seconds) -> str:
    if not seconds:
        return '—'
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}'


def _parse_hms(text: str) -> int:
    """Parse ``H:MM:SS`` / ``MM:SS`` / ``SS`` into whole seconds (raises on junk)."""
    text = (text or '').strip()
    if not text:
        raise ValueError("Enter a finish time as H:MM:SS")
    parts = text.split(':')
    try:
        nums = [int(p) for p in parts]
    except ValueError as e:
        raise ValueError("Finish time must be numbers separated by ':'") from e
    if any(n < 0 for n in nums) or len(nums) > 3:
        raise ValueError("Enter a finish time as H:MM:SS")
    total = 0
    for n in nums:
        total = total * 60 + n
    if total <= 0:
        raise ValueError("Finish time must be greater than zero")
    return total


def create() -> None:
    service = AsyncQualifierService()

    @protected_page('/qualifiers', feature=FeatureFlag.ASYNC_QUALIFIERS)
    async def qualifiers_list() -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Async Qualifiers')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(user=user, show_admin=show_admin, show_volunteer=user is not None).render()

        with ui.column().classes('page-container'):
            ui.label('Async Qualifiers').classes('page-title')
            ui.separator()
            qualifiers = await service.list_open_qualifiers()
            if not qualifiers:
                ui.label('No active qualifiers right now.').classes('text-grey')
                return
            for q in qualifiers:
                with ui.card().classes('w-full'):
                    with ui.row().classes('items-center full-width'):
                        ui.label(q.name).classes('text-h6')
                        ui.space()
                        ui.button('Open', icon='arrow_forward',
                                  on_click=lambda qid=q.id: ui.navigate.to(f'/qualifiers/{qid}')
                                  ).props('flat color=primary')
                    ui.label(f'Window: {_fmt(q.opens_at)} → {_fmt(q.closes_at)}').classes(
                        'text-caption text-grey')
                    if q.description:
                        ui.label(q.description).classes('text-caption')

    @protected_page('/qualifiers/{qualifier_id}', feature=FeatureFlag.ASYNC_QUALIFIERS)
    async def qualifier_detail(qualifier_id: int) -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Async Qualifier')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(user=user, show_admin=show_admin, show_volunteer=user is not None).render()

        if user is None:
            ui.label('You must be logged in.').classes('text-error')
            return

        try:
            qualifier = await service.get_qualifier_for_player(qualifier_id)
        except ValueError as e:
            ui.label(str(e)).classes('text-error')
            return

        container = ui.column().classes('page-container')

        @ui.refreshable
        async def render() -> None:
            container.clear()
            with container:
                with ui.row().classes('items-center full-width'):
                    ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/qualifiers')
                              ).props('flat round')
                    ui.label(qualifier.name).classes('page-title')
                is_public = service.is_results_public(qualifier)
                open_now = _window_open(qualifier)
                ui.label(f'Window: {_fmt(qualifier.opens_at)} → {_fmt(qualifier.closes_at)}  ·  '
                         f'{"Open" if open_now else "Closed"}').classes('text-caption text-grey')
                ui.separator()

                active = await service.get_active_run(user, qualifier_id)
                if active is not None:
                    await _render_active_run(active)
                elif open_now:
                    await _render_start(qualifier, user)
                else:
                    ui.label('This qualifier is not open for runs.').classes('text-grey')

                ui.separator()
                await _render_my_runs(user)
                ui.separator()
                await _render_leaderboard(user, is_public)

        async def _render_start(qual, current) -> None:
            pools = await service.get_player_pools(current, qualifier_id)
            ui.label('Start a run').classes('text-subtitle1')
            if not pools:
                ui.label('No pools available to run right now.').classes('text-grey')
                return
            ui.label('Pick a pool. A permalink is drawn and revealed only when your '
                     'run starts — and your timer begins immediately.').classes('text-caption text-grey')
            for pool in pools:
                with ui.row().classes('items-center'):
                    ui.button(f'Start: {pool.name}', icon='play_arrow',
                              on_click=lambda pid=pool.id: _start(pid)).props('color=primary')

        async def _start(pool_id: int) -> None:
            try:
                await service.start_run(user, qualifier_id, pool_id)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Run started — good luck!', color='positive')
            await render.refresh()

        async def _render_active_run(run) -> None:
            with ui.card().classes('w-full'):
                ui.label('Your run is in progress').classes('text-subtitle1 text-positive')
                pool_name = run.permalink.pool.name if run.permalink and run.permalink.pool else '—'
                ui.label(f'Pool: {pool_name}').classes('text-caption text-grey')
                if run.permalink:
                    ui.link('Your permalink (open the seed)', run.permalink.url, new_tab=True)
                elapsed_label = ui.label('Elapsed: 0:00:00').classes('text-h6')

                def _tick():
                    started = run.started_at
                    if started is None:
                        return
                    if started.tzinfo is None:
                        started_aware = started.replace(tzinfo=timezone.utc)
                    else:
                        started_aware = started
                    delta = int((datetime.now(timezone.utc) - started_aware).total_seconds())
                    elapsed_label.text = f'Elapsed: {_fmt_hms(max(0, delta))}'

                ui.timer(1.0, _tick)

                ui.separator()
                ui.label('Submit your result').classes('text-subtitle2')
                time_in = ui.input('Finish time (H:MM:SS)', placeholder='1:23:45').classes('w-full')
                vod_in = ui.input('VoD URL (optional)').classes('w-full')

                async def _submit():
                    try:
                        seconds = _parse_hms(time_in.value)
                        await service.submit_run(user, run.id, elapsed_seconds=seconds,
                                                 runner_vod_url=vod_in.value)
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify('Submitted for review!', color='positive')
                    await render.refresh()

                async def _forfeit():
                    try:
                        await service.forfeit_run(user, run.id)
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify('Run forfeited.', color='info')
                    await render.refresh()

                with ui.row().classes('justify-end w-full'):
                    ui.button('Forfeit', icon='flag', on_click=_forfeit).props('flat color=negative')
                    ui.button('Submit', icon='send', on_click=_submit).props('color=primary')

        async def _render_my_runs(current) -> None:
            runs = await service.list_user_runs(current, qualifier_id)
            ui.label('My runs').classes('text-subtitle1')
            if not runs:
                ui.label('You have no runs yet.').classes('text-grey')
                return
            columns = [
                {'name': 'pool', 'label': 'Pool', 'field': 'pool', 'align': 'left'},
                {'name': 'status', 'label': 'Status', 'field': 'status'},
                {'name': 'review', 'label': 'Review', 'field': 'review'},
                {'name': 'time', 'label': 'Time', 'field': 'time'},
                {'name': 'score', 'label': 'Score', 'field': 'score'},
            ]
            rows = []
            for r in runs:
                pool_name = r.permalink.pool.name if r.permalink and r.permalink.pool else '—'
                rows.append({
                    'pool': pool_name + (' (reattempted)' if r.reattempted else ''),
                    'status': r.status.value if hasattr(r.status, 'value') else str(r.status),
                    'review': r.review_status.value if hasattr(r.review_status, 'value') else str(r.review_status),
                    'time': _fmt_hms(r.elapsed_seconds),
                    'score': '' if r.score is None else round(r.score, 1),
                })
            table = ui.table(columns=columns, rows=rows, row_key='pool').classes('w-full wiz-table')
            enable_mobile_grid(table, columns)

        async def _render_leaderboard(current, is_public) -> None:
            ui.label('Leaderboard').classes('text-subtitle1')
            try:
                entries = await service.get_leaderboard(current, qualifier_id)
            except PermissionError:
                ui.label('The leaderboard is hidden until this qualifier closes.').classes('text-grey')
                return
            if not entries:
                ui.label('No scored runs yet.').classes('text-grey')
                return
            columns = [
                {'name': 'rank', 'label': '#', 'field': 'rank'},
                {'name': 'user', 'label': 'Player', 'field': 'user', 'align': 'left'},
                {'name': 'actual', 'label': 'Score', 'field': 'actual'},
                {'name': 'estimate', 'label': 'Estimate', 'field': 'estimate'},
            ]
            rows = [
                {'rank': i + 1, 'user': e.username, 'actual': e.actual, 'estimate': e.estimate}
                for i, e in enumerate(entries)
            ]
            table = ui.table(columns=columns, rows=rows, row_key='rank').classes('w-full wiz-table')
            enable_mobile_grid(table, columns)

        await render()


def _window_open(qualifier) -> bool:
    if not qualifier.is_active:
        return False
    now = datetime.now(timezone.utc)
    if qualifier.opens_at is not None and now < qualifier.opens_at:
        return False
    if qualifier.closes_at is not None and now >= qualifier.closes_at:
        return False
    return True
