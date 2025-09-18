from theme.match_table import MatchTable

from nicegui import ui, events, app
from models import Match
from pages.dialogues import MatchSubmissionDialog
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
                show_upcoming_checkbox = ui.checkbox('Show only upcoming races', value=True)

                async def refresh():
                    now = datetime.now()
                    match_query = Match.filter(players__user__discord_id=discord_id)
                    if show_upcoming_checkbox.value:
                        match_query = match_query.filter(scheduled_at__gte=now - timedelta(minutes=30))
                    all_matches = await match_query.prefetch_related(
                        'tournament', 'players', 'players__user', 'stream_room', 'generated_seed'
                    ).order_by('scheduled_at')
                    rows = []
                    for m in all_matches:
                        player_names = ', '.join([p.user.username for p in m.players])
                        rows.append({
                            'id': m.id,
                            'tournament': m.tournament.name if m.tournament else '',
                            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
                            'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else '',
                            'players': player_names,
                            'stream_room': m.stream_room.name if m.stream_room else '',
                            'generated_seed': m.generated_seed.seed_url if m.generated_seed else ''
                        })
                    table.rows = rows
                    table.update()

                show_upcoming_checkbox.on('change', lambda e: asyncio.create_task(refresh()))

                async def submit_match():
                    dialog = MatchSubmissionDialog(discord_id)
                    await dialog.open()

                with ui.row().style('width: 100%;'):
                    ui.button('Submit Match', on_click=submit_match)
                    ui.button(on_click=refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id'},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                    {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
                    {'name': 'players', 'label': 'Players', 'field': 'players'},
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                    {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
                ]
                match_table = MatchTable(columns=columns)
                table = match_table.render()

                # Refresh table on page load
                asyncio.create_task(refresh())

        # Refresh table on page load
        asyncio.create_task(refresh())
        # Refresh table on page load
        asyncio.create_task(refresh())
