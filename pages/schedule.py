
from nicegui import ui
from models import Match
import asyncio
from pages.match_table_common import MatchTableView

def create() -> None:
    @ui.page('/schedule')
    def schedule():
        ui.label('Scheduled Matches').style('font-size: 2em; margin-bottom: 1em;')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'players', 'label': 'Players', 'field': 'players', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room', 'sortable': True, 'filterable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
        ]

        def get_query():
            return Match.all().prefetch_related('tournament', 'players', 'stream_room', 'generated_seed').order_by('scheduled_at')

        # No admin controls or extra slots for schedule view
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False
        )

        # Initial table load
        asyncio.create_task(table_view.refresh())