"""Staff / Crew Activity report.

Coverage-by-match table plus contribution-by-person table.
"""

from typing import Optional

from nicegui import app, ui

from application.services import AuthService, ReportsService, get_user_from_discord_id
from application.utils.timezone import format_local_display
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.tables.mobile_grid import enable_mobile_grid
from .shared import (
    clicked_row,
    csv_export_button,
    date_range_filter,
    default_date_range,
    display_bounds,
    enable_drill_link,
    navigate_with_params,
    parse_int,
    report_page_shell,
    tournament_filter,
)


APPROVAL_OPTIONS = ['All', 'Approved only', 'Pending only']


async def crew_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    tournament_id: Optional[int] = None,
    user_id: Optional[int] = None,
    approval: Optional[str] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    selected_approval = approval if approval in APPROVAL_OPTIONS else 'All'
    user_id_int = parse_int(user_id)
    # Resolved once, not per row: this report is readable by staff, tournament
    # admins and crew coordinators, and all three also have the Schedule tab —
    # but that is the destination's predicate, so ask it rather than assume it.
    viewer = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_open_board = await AuthService.can_view_schedule_board(viewer)

    with report_page_shell('Staff / Crew Activity'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='crew',
                        start=s, end=e,
                        tournament_id=tournament_id,
                        user_id=user_id_int,
                        approval=None if selected_approval == 'All' else selected_approval,
                    ),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: navigate_with_params(
                        report='crew',
                        start=start_d, end=end_d,
                        tournament_id=t_id,
                        user_id=user_id_int,
                        approval=None if selected_approval == 'All' else selected_approval,
                    ),
                )
                approval_select = ui.select(
                    APPROVAL_OPTIONS,
                    value=selected_approval,
                    label='Approval',
                ).props('dense').classes('control-width')

                def _on_approval(_e):
                    navigate_with_params(
                        report='crew',
                        start=start_d, end=end_d,
                        tournament_id=tournament_id,
                        user_id=user_id_int,
                        approval=None if approval_select.value == 'All' else approval_select.value,
                    )
                approval_select.on('update:model-value', _on_approval)

                if user_id_int is not None:
                    ui.button(
                        'Clear user filter', icon='close',
                        on_click=lambda: navigate_with_params(
                            report='crew',
                            start=start_d, end=end_d,
                            tournament_id=tournament_id,
                            approval=None if selected_approval == 'All' else selected_approval,
                        ),
                    ).props('flat dense')

        bounds_start, bounds_end = display_bounds(start_d, end_d)
        data = await ReportsService().crew_coverage(
            bounds_start, bounds_end,
            tournament_id=tournament_id,
            user_id=user_id_int,
        )

        coverage_rows = data['coverage_rows']
        if selected_approval == 'Approved only':
            coverage_rows = [
                r for r in coverage_rows
                if r['commentators_approved'] > 0 or r['trackers_approved'] > 0
            ]
        elif selected_approval == 'Pending only':
            coverage_rows = [
                r for r in coverage_rows
                if r['commentators_total'] > r['commentators_approved']
                or r['trackers_total'] > r['trackers_approved']
            ]

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label('Coverage by match').classes('text-h6')
                cov_rows_display = [
                    {
                        'match_id': r['match_id'],
                        'tournament': r['tournament_name'],
                        'scheduled_at': format_local_display(r['scheduled_at']),
                        'stream_room': r['stream_room'],
                        'stream_candidate': 'yes' if r['is_stream_candidate'] else '',
                        # The requirement is per-tournament, so "0/0" only means a
                        # gap when the tournament actually asks for the role.
                        'commentators': (
                            f"{r['commentators_approved']}/{r['commentators_total']}"
                            f" · need {r['commentators_required']}"
                        ),
                        'trackers': (
                            f"{r['trackers_approved']}/{r['trackers_total']}"
                            f" · need {r['trackers_required']}"
                        ),
                        'gap': 'GAP' if r['coverage_gap'] else '',
                    }
                    for r in coverage_rows
                ]
                cov_columns = [
                    {'name': 'match_id', 'label': 'Match', 'field': 'match_id', 'sortable': True},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
                    {'name': 'scheduled_at', 'label': 'Scheduled', 'field': 'scheduled_at', 'sortable': True},
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room', 'sortable': True},
                    {'name': 'stream_candidate', 'label': 'Candidate', 'field': 'stream_candidate'},
                    {'name': 'commentators', 'label': 'Comms (apprv/total)', 'field': 'commentators'},
                    {'name': 'trackers', 'label': 'Trackers (apprv/total)', 'field': 'trackers'},
                    {'name': 'gap', 'label': 'Coverage gap', 'field': 'gap'},
                ]
                csv_export_button(
                    f'crew-coverage-{start_d}-to-{end_d}',
                    lambda: cov_columns,
                    lambda: cov_rows_display,
                )
            cov_table = ui.table(
                columns=cov_columns,
                rows=cov_rows_display,
                pagination=25,
                row_key='match_id',
            ).classes('full-width')
            # The crew cell that approves a pending signup lives on the board;
            # this report is the only surface that can see the gap.
            drill_actions = enable_drill_link(
                cov_table, cov_columns, cov_rows_display,
                lambda r: admin_url(SCHEDULE, match_id=r['match_id']),
                enabled=can_open_board,
                hint='Open on the schedule board',
            )
            enable_mobile_grid(cov_table, cov_columns, actions=drill_actions)

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label('Contribution by person').classes('text-h6')
                contribution_rows = data['contribution_rows']
                contrib_display = []
                for r in contribution_rows:
                    contrib_display.append({
                        **r,
                        'commentary_pct': _ratio_pct(r['commentator_approved'], r['commentator_total']),
                        'tracker_pct': _ratio_pct(r['tracker_approved'], r['tracker_total']),
                    })
                contrib_columns = [
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                    {'name': 'commentator_total', 'label': 'Commentary signups', 'field': 'commentator_total', 'sortable': True},
                    {'name': 'commentator_approved', 'label': 'Commentary approved', 'field': 'commentator_approved', 'sortable': True},
                    {'name': 'commentary_pct', 'label': 'Commentary %', 'field': 'commentary_pct', 'sortable': True},
                    {'name': 'tracker_total', 'label': 'Tracker signups', 'field': 'tracker_total', 'sortable': True},
                    {'name': 'tracker_approved', 'label': 'Tracker approved', 'field': 'tracker_approved', 'sortable': True},
                    {'name': 'tracker_pct', 'label': 'Tracker %', 'field': 'tracker_pct', 'sortable': True},
                    {'name': 'hours_covered', 'label': 'Hours covered', 'field': 'hours_covered', 'sortable': True},
                ]
                csv_export_button(
                    f'crew-contribution-{start_d}-to-{end_d}',
                    lambda: contrib_columns,
                    lambda: contrib_display,
                )

            def _row_clicked(e):
                clicked_uid = clicked_row(e).get('user_id')
                if clicked_uid:
                    navigate_with_params(
                        report='crew',
                        start=start_d, end=end_d,
                        tournament_id=tournament_id,
                        user_id=clicked_uid,
                        approval=None if selected_approval == 'All' else selected_approval,
                    )

            contrib_table = ui.table(
                columns=contrib_columns,
                rows=contrib_display,
                pagination=25,
                row_key='user_id',
            ).classes('full-width wiz-rowclick')
            contrib_table.on('row-click', _row_clicked)
            enable_mobile_grid(contrib_table, contrib_columns, row_click_event='row-click')
            if user_id_int is None:
                ui.label('Click a row to filter both tables to that person.').classes('italic-note')


def _ratio_pct(num: int, denom: int) -> Optional[float]:
    if not denom:
        return None
    return round(num / denom * 100, 1)
