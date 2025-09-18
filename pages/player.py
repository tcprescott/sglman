from theme.match_table import MatchTable

from nicegui import ui, events, app
from models import Match
from pages.dialogues import MatchDialog
import asyncio
from datetime import datetime, timedelta

def create() -> None:
    @ui.page('/player')
    def player_page() -> None:
        ui.label('Player Page').style('font-size: 2em; margin-bottom: 1em;')
        ui.label('This is the player dashboard where players can view their upcoming or in-progress matches, submit match results, and confirm matches assigned to them.')

        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return


        with ui.card().style('width: 100%; max-width: 900px; margin: 0 auto; padding: 0;'):
            with ui.column().style('width: 100%;'):
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id'},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                    {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
                    {'name': 'players', 'label': 'Players', 'field': 'players'},
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                    {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
                ]
                from pages.match_table_common import render_match_table
                async def submit_match():
                    dialog = MatchDialog(discord_id)
                    await dialog.open()
                def get_query():
                    return Match.filter(players__user__discord_id=discord_id)
                table, refresh = render_match_table(
                    columns=columns,
                    get_query=get_query,
                    admin_controls=False,
                    submit_match_callback=submit_match
                )

                # Refresh table on page load
                asyncio.create_task(refresh())
