
from nicegui import app, ui
from theme.base import BaseLayout
from models import Match, User, Permissions
from theme.tables.match import MatchTableView

def create() -> None:
    @ui.page('/schedule')
    async def schedule():
        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id) if discord_id else None
        ui.label('Scheduled Matches').style('font-size: 2em; margin-bottom: 1em;')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'players', 'label': 'Players', 'field': 'players', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room', 'sortable': True, 'filterable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
        ]

        def get_query():
            return Match.all().prefetch_related('tournament', 'players', 'stream_room', 'generated_seed').order_by('scheduled_at')

        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id) if discord_id else None

        # No admin controls or extra slots for schedule view
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False
        )

        # Initial table load
        await table_view.refresh()
        await BaseLayout(page_name='schedule', user=user).render()