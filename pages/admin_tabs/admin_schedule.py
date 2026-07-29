"""Admin Schedule Management Page"""


from nicegui import ui

from application.tenant_context import require_tenant_id
from models import Match
from theme.dialog.match_dialog import AdminMatchDialog
from theme.tables.match import MatchTableView
from theme.tables.match_lifecycle import MatchLifecycleHandlers


def admin_schedule_page(can_crud: bool = True) -> None:
    with ui.column().classes('page-container-wide') as page_container:
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Schedule Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament',
                'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At',
                'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'state', 'label': 'State', 'field': 'state',
                'sortable': True, 'filterable': True},
            {'name': 'players', 'label': 'Players',
                'field': 'players', 'filterable': True},
            {'name': 'commentators', 'label': 'Commentators',
                'field': 'commentators', 'filterable': True},
            {'name': 'trackers', 'label': 'Trackers',
                'field': 'trackers', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage',
                'field': 'stream_room', 'sortable': True, 'filterable': True, 'clickable': True},
            {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
        ]

        def get_query():
            return Match.filter(tenant_id=require_tenant_id())

        # Creating a match is a scheduling action, not a lifecycle one, so it
        # stays here rather than moving into MatchLifecycleHandlers.
        async def submit_admin_match():
            async def after_submit():
                await table_view.refresh()
            with page_container:
                dialog = AdminMatchDialog(on_submit=after_submit)
                await dialog.open()

        extra_slots = {}

        table_view = None

        # Built before the view so the view can be handed a callback that
        # refreshes it; guarded because the view's first load can land before
        # the local name is bound.
        @ui.refreshable
        def review_queue() -> None:
            rows = table_view.table.rows if table_view else []
            pending = [r for r in rows if r.get('state') == 'Finished']
            if not pending:
                return
            # A proctor flagged these as contested. Counted separately and shown
            # first: a disputed result needs a decision, an unflagged one only
            # needs a click.
            flagged = [r for r in pending if r.get('needs_review')]
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                # ui.element + ui.label rather than ui.html: NiceGUI's raw-HTML
                # sinks are reserved for static literals (check_markdown_xss).
                if flagged:
                    with ui.element('span').classes('wiz-chip wiz-chip--cancelled'):
                        ui.icon('report_problem', size='14px')
                        ui.label(f'Flagged for review: {len(flagged)}')
                with ui.element('span').classes('wiz-chip wiz-chip--pending'):
                    ui.icon('flag', size='14px')
                    ui.label(f'Awaiting confirmation: {len(pending)}')
                ui.button(
                    'Show only these', icon='filter_alt', on_click=lambda: _only_finished(),
                ).props('flat dense color=primary')

        def _only_finished() -> None:
            # Assigning the select's value fires _on_state_filter_change, which
            # stores the choice and reloads the table.
            table_view.state_filter.value = ['Finished']

        review_queue()

        handlers = MatchLifecycleHandlers(page_container, can_crud=can_crud)
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            can_crud=can_crud,
            submit_match_callback=submit_admin_match if can_crud else None,
            extra_slots=extra_slots,
            storage_key='admin_schedule',
            # The admin's job *is* the Finished-not-yet-Confirmed set, so it
            # must be on screen without them discovering the State filter.
            default_state_filter=['Scheduled', 'Checked In', 'Started', 'Finished'],
            on_rows_changed=lambda _rows: review_queue.refresh(),
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        # Route through the view's _bg so the tab-switch refresh rebinds the
        # tenant (the selected_tab handler runs in a detached task that lost it).
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
