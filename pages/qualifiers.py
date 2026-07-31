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
from application.services.async_qualifier.async_qualifier_rules import (
    ClaimVerdict,
    classify_claim,
    measure_elapsed,
)
from application.utils.duration import format_hms, parse_hms
from application.utils.timezone import format_local_display
from models import FeatureFlag
from theme.base import BaseLayout
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.qualifier_copy import BOARD_EXPLAINER, SCORE_EXPLAINER
from theme.tables.mobile_grid import enable_mobile_grid


def _fmt(dt) -> str:
    return format_local_display(dt) if dt else '—'


# Run states a reattempt can void — an in-progress run is finished or forfeited
# first, which is what reattempt_run enforces.
_TERMINAL_STATUSES = {'finished', 'forfeit', 'disqualified'}

_REATTEMPT_ACTION = '''
    <q-btn v-if="props.row.reattemptable" flat dense icon="restart_alt" color="primary"
           label="Reattempt"
           @click="$parent.$emit('reattempt', props.row)">
        <q-tooltip>Void this run and free its pool slot</q-tooltip>
    </q-btn>
'''


def _latest_note(run) -> str:
    """The most recent reviewer note on a run — the reason behind its verdict.

    Not a disclosure change: ``get_run_notes`` already lets a run's own owner read
    its notes. The page simply never asked.
    """
    notes = [n for n in (getattr(run, 'review_notes', None) or []) if getattr(n, 'note', '')]
    if not notes:
        return ''
    latest = max(notes, key=lambda n: (n.created_at, n.id))
    return latest.note


def _words(seconds: int) -> str:
    """``5025`` → ``'1 hour, 23 minutes, 45 seconds'`` — display copy for the echo."""
    parts = []
    for value, unit in ((seconds // 3600, 'hour'), (seconds % 3600 // 60, 'minute'),
                        (seconds % 60, 'second')):
        if value:
            parts.append(f'{value} {unit}' + ('' if value == 1 else 's'))
    return ', '.join(parts) or '0 seconds'


def create() -> None:
    service = AsyncQualifierService()

    @protected_page('/qualifiers', feature=FeatureFlag.ASYNC_QUALIFIERS)
    async def qualifiers_list() -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Async Qualifiers')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(user=user, show_admin=show_admin).render()

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
        await BaseLayout(user=user, show_admin=show_admin).render()

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
                else:
                    await _render_start(user)

                ui.separator()
                await _render_my_runs(user)
                ui.separator()
                await _render_leaderboard(user, is_public)

        async def _render_start(current) -> None:
            # One read answers both "can I run?" and "why not?" — the page no
            # longer has to infer a reason from an empty list.
            availability = await service.get_run_availability(current, qualifier_id)
            ui.label('Start a run').classes('text-subtitle1')
            if not availability.pools:
                ui.label(availability.message).classes('text-grey')
                return
            ui.label('Pick a pool. A permalink is drawn and revealed only when your '
                     'run starts — and your timer begins immediately.').classes('text-caption text-grey')
            eligible = {p.id for p in availability.pools}
            for usage in availability.usage:
                with ui.row().classes('items-center'):
                    if usage.pool_id in eligible:
                        ui.button(f'Start: {usage.name}', icon='play_arrow',
                                  on_click=lambda pid=usage.pool_id: _start(pid)
                                  ).props('color=primary')
                    else:
                        ui.label(usage.name).classes('text-grey')
                    detail = f'{usage.used} of {usage.allowed} runs used'
                    if usage.slots_left and not usage.has_candidates:
                        detail += ' · no unplayed seeds left'
                    ui.label(detail).classes('text-caption text-grey')

        async def _start(pool_id: int) -> None:
            try:
                await service.start_run(user, qualifier_id, pool_id)
            except (ValueError, PermissionError) as e:
                notify_error(e)
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
                    measured = measure_elapsed(run.started_at)
                    if measured is None:
                        return
                    elapsed_label.text = f'Elapsed: {format_hms(measured)}'

                ui.timer(1.0, _tick)

                ui.separator()
                ui.label('Submit your result').classes('text-subtitle2')
                time_in = ui.input('Finish time (H:MM:SS)', placeholder='1:23:45').classes('w-full')
                echo = ui.label('').classes('text-caption text-grey')
                vod_in = ui.input('VoD URL (optional)').classes('w-full')

                def _echo() -> None:
                    try:
                        seconds = parse_hms(time_in.value)
                    except ValueError:
                        echo.text = ''
                        return
                    echo.text = f'Submitting {format_hms(seconds)} — {_words(seconds)}'

                time_in.on_value_change(lambda _: _echo())

                async def _do_submit(seconds: int) -> None:
                    try:
                        await service.submit_run(user, run.id, elapsed_seconds=seconds,
                                                 runner_vod_url=vod_in.value)
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify('Submitted for review!', color='positive')
                    await render.refresh()

                def _ask_about_drift(seconds: int, measured: int) -> None:
                    async def _confirmed() -> None:
                        confirm.dialog.close()
                        await _do_submit(seconds)

                    confirm = ConfirmationDialog(
                        title='Is that the right time?',
                        message=(f'Your timer says {format_hms(measured)}. '
                                 f'You typed {format_hms(seconds)}.\n\n'
                                 'If you finished a while ago and are only submitting now, '
                                 'your time is fine — submit it. If you dropped a segment, '
                                 'go back and fix it.'),
                        confirm_text=f'Submit {format_hms(seconds)}',
                        cancel_text='Let me fix it',
                        tone='primary',
                        on_confirm=_confirmed,
                    )
                    confirm.open()

                async def _submit():
                    try:
                        seconds = parse_hms(time_in.value)
                    except ValueError as e:
                        notify_error(e)
                        return
                    # An impossible claim is the service's refusal to make — its
                    # clock is the authority. The page only asks about the gap the
                    # runner can explain.
                    measured = measure_elapsed(run.started_at)
                    if classify_claim(seconds, measured) is ClaimVerdict.IMPLAUSIBLE:
                        _ask_about_drift(seconds, measured)
                        return
                    await _do_submit(seconds)

                async def _forfeit():
                    try:
                        await service.forfeit_run(user, run.id)
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify('Run forfeited.', color='info')
                    await render.refresh()

                async def _confirm_forfeit() -> None:
                    # ConfirmationDialog does not close itself once on_confirm is
                    # supplied, so the handler closes it before refreshing.
                    async def _confirmed() -> None:
                        confirm.dialog.close()
                        await _forfeit()

                    allowance = await service.get_reattempt_allowance(user, qualifier_id)
                    remedy = ''
                    if allowance.remaining:
                        # Never "you can undo this" — a reattempt is a fresh draw on
                        # a new permalink, not an undo of this one.
                        plural = '' if allowance.remaining == 1 else 's'
                        remedy = (f'\n\nYou would have {allowance.remaining} reattempt{plural} '
                                  f'left, which starts a new run on a new permalink.')
                    confirm = ConfirmationDialog(
                        title='Forfeit this run?',
                        message=('Forfeiting ends this attempt now.\n\n'
                                 'The run scores 0, the pool slot is spent, and this '
                                 'cannot be undone.' + remedy),
                        confirm_text='Forfeit run',
                        tone='negative',
                        on_confirm=_confirmed,
                    )
                    confirm.open()

                with ui.row().classes('justify-end w-full'):
                    ui.button('Forfeit', icon='flag',
                              on_click=_confirm_forfeit).props('flat color=negative')
                    ui.button('Submit', icon='send', on_click=_submit).props('color=primary')

        async def _render_my_runs(current) -> None:
            runs = await service.list_user_runs(current, qualifier_id)
            allowance = await service.get_reattempt_allowance(current, qualifier_id)
            ui.label('My runs').classes('text-subtitle1')
            # A reattempt after the window closes would delete the runner's own
            # score with no way to replace it, so neither the action nor the
            # sentence promising it appears once the window shuts. The service
            # deliberately allows it either way, because a reviewer may need to
            # void a run after close.
            window_open = _window_open(qualifier)
            if allowance.allowed and window_open:
                ui.label(f'Reattempts: {allowance.remaining} of {allowance.allowed} remaining. '
                         'Spending one voids a finished or forfeited run and frees its pool '
                         'slot for a new draw.').classes('text-caption text-grey')
            if not runs:
                ui.label('You have no runs yet.').classes('text-grey')
                return
            can_reattempt = window_open and allowance.remaining > 0
            columns = [
                {'name': 'pool', 'label': 'Pool', 'field': 'pool', 'align': 'left'},
                {'name': 'status', 'label': 'Status', 'field': 'status'},
                {'name': 'review', 'label': 'Review', 'field': 'review'},
                {'name': 'time', 'label': 'Time', 'field': 'time'},
                {'name': 'score', 'label': 'Score', 'field': 'score'},
                # Capped and wrapping: a full rejection reason is the longest text
                # on the row, and left to itself it pushes the row action off the
                # right edge of a desktop table.
                {'name': 'note', 'label': 'Reviewer note', 'field': 'note', 'align': 'left',
                 'style': 'max-width: 20rem; white-space: normal'},
            ]
            if can_reattempt:
                columns.append({'name': 'actions', 'label': '', 'field': 'actions'})
            rows = []
            for r in runs:
                pool_name = r.permalink.pool.name if r.permalink and r.permalink.pool else '—'
                status = r.status.value if hasattr(r.status, 'value') else str(r.status)
                rows.append({
                    'id': r.id,
                    'pool': pool_name + (' (reattempted)' if r.reattempted else ''),
                    'status': status,
                    'review': r.review_status.value if hasattr(r.review_status, 'value') else str(r.review_status),
                    'time': format_hms(r.elapsed_seconds),
                    'score': '' if r.score is None else round(r.score, 1),
                    'note': _latest_note(r),
                    'reattemptable': not r.reattempted and status in _TERMINAL_STATUSES,
                })
            table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full wiz-table')
            if can_reattempt:
                table.add_slot('body-cell-actions',
                               f'<q-td :props="props">{_REATTEMPT_ACTION}</q-td>')
                table.on('reattempt', lambda e: _open_reattempt_dialog(e.args.get('id')))
                enable_mobile_grid(table, columns, actions=_REATTEMPT_ACTION)
            else:
                enable_mobile_grid(table, columns)
            ui.label(SCORE_EXPLAINER).classes('text-caption text-grey')

        def _open_reattempt_dialog(run_id) -> None:
            with ui.dialog() as dialog, ui.card().classes('w-[30rem]'):
                ui.label('Use a reattempt?').classes('text-h6')
                ui.label('This voids that run — it stops counting and its score is '
                         'discarded — and frees the pool slot so you can draw a new '
                         'permalink. It does not restore the run you already played.'
                         ).classes('text-caption text-grey')
                reason_in = ui.textarea('Why? (required)').classes('w-full').props('rows=2')

                async def submit() -> None:
                    try:
                        await service.reattempt_run(user, int(run_id), reason=reason_in.value)
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify('Reattempt used — that pool is open again.', color='positive')
                    dialog.close()
                    await render.refresh()

                with ui.row().classes('justify-end w-full'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    spend = ui.button('Use reattempt', icon='restart_alt', on_click=submit)
                    spend.props('color=primary')
                    spend.bind_enabled_from(reason_in, 'value', lambda v: bool((v or '').strip()))
            dialog.open()

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
                # Without this the caption's "unrun slots" names something the
                # player cannot see; the admin board has always had it.
                {'name': 'slots', 'label': 'Slots', 'field': 'slots'},
            ]
            rows = [
                {'rank': i + 1, 'user': e.username, 'actual': e.actual, 'estimate': e.estimate,
                 'slots': f'{e.slots_filled}/{e.slots_total}'}
                for i, e in enumerate(entries)
            ]
            table = ui.table(columns=columns, rows=rows, row_key='rank').classes('w-full wiz-table')
            enable_mobile_grid(table, columns)
            ui.label(BOARD_EXPLAINER).classes('text-caption text-grey')

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
