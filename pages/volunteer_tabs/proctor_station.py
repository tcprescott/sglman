"""Proctor Station tab — the on-site match board.

One proctor runs a room, so this is a *room* board: every match in play, ordered
by what needs a proctor next. Deliberately not the admin Schedule tab — that one
is for scheduling matches, this one is for running them. It therefore drops the
crew, stage and scheduling columns and carries no create/edit controls.
"""

from nicegui import ui

from application.tenant_context import require_tenant_id
from models import Match
from theme.tables.match import MatchTableView
from theme.tables.match_lifecycle import MatchLifecycleHandlers

# Action-bearing columns first: on a phone-width table the right-hand columns are
# what gets clipped, and the proctor's next action must never be the clipped one.
PROCTOR_COLUMNS = [
    {'name': 'scheduled_at', 'label': 'Time', 'field': 'scheduled_at', 'sortable': True},
    {'name': 'state', 'label': 'Next step', 'field': 'state'},
    {'name': 'players', 'label': 'Players & stations', 'field': 'players'},
    {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament',
     'sortable': True, 'filterable': True},
    {'name': 'id', 'label': '#', 'field': 'id'},
]

# What the proctor has to deal with next, most-urgent first. Within a bucket,
# earliest scheduled time wins.
_URGENCY = {
    'overdue':    0,   # scheduled time has passed and nobody is checked in
    'Checked In': 1,   # seated, waiting on a countdown
    'Started':    2,   # in play, watching for a raised hand
    'Scheduled':  3,   # not due yet
    'Finished':   4,   # proctor's work is done
    'Confirmed':  5,
}


def proctor_row_order(rows: list[dict]) -> list[dict]:
    """Order table rows by what the proctor has to do next."""
    def key(row):
        state = row.get('state') or 'Scheduled'
        bucket = _URGENCY['overdue'] if (state == 'Scheduled' and row.get('is_overdue')) \
            else _URGENCY.get(state, 3)
        return (bucket, row.get('scheduled_ts') or 0)
    return sorted(rows, key=key)


async def proctor_station_tab() -> None:
    with ui.column().classes('page-container-wide') as page_container:
        with ui.row().classes('header-row'):
            ui.label('Proctor Station').classes('page-title')
        ui.label(
            'Every match in this room. Check players in, seat them, roll the seed, '
            'start them, then record the winner.'
        ).classes('text-caption text-grey')
        ui.separator().classes('separator-spacing')

        def get_query():
            return Match.filter(tenant_id=require_tenant_id())

        table_view = None

        # Built before the view so the view can be handed a callback that
        # refreshes it; guarded because the view's first load can land before
        # the local name is bound.
        @ui.refreshable
        def summary() -> None:
            rows = table_view.table.rows if table_view else []
            counts = {
                'To check in': sum(1 for r in rows if r.get('state') == 'Scheduled'),
                'To start':    sum(1 for r in rows if r.get('state') == 'Checked In'),
                'In play':     sum(1 for r in rows if r.get('state') == 'Started'),
                'Overdue':     sum(1 for r in rows if r.get('is_overdue')),
            }
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                for label, n in counts.items():
                    tone = 'wiz-chip--pending' if (label == 'Overdue' and n) else 'wiz-chip--neutral'
                    # ui.element + ui.label rather than ui.html: NiceGUI's raw-HTML
                    # sinks are reserved for static literals (check_markdown_xss).
                    with ui.element('span').classes(f'wiz-chip {tone}'):
                        ui.label(f'{label}: {n}')

        summary()

        handlers = MatchLifecycleHandlers(page_container, can_crud=False)
        table_view = MatchTableView(
            columns=PROCTOR_COLUMNS,
            get_query=get_query,
            admin_controls=True,
            can_crud=False,
            exclude_racetime=True,
            row_sort=proctor_row_order,
            actions_first=True,
            on_rows_changed=lambda _rows: summary.refresh(),
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        # Through the view's _bg so the tab-switch refresh keeps the tenant the
        # request was resolved against (the handler runs in a detached task).
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Proctor Station' else None)
