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

        handlers = MatchLifecycleHandlers(page_container, can_crud=can_crud)
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            can_crud=can_crud,
            submit_match_callback=submit_admin_match if can_crud else None,
            extra_slots=extra_slots,
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        # Route through the view's _bg so the tab-switch refresh rebinds the
        # tenant (the selected_tab handler runs in a detached task that lost it).
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
