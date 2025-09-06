
from nicegui import ui
from models import Match, Tournament, User, StreamRoom
import asyncio



def create() -> None:
    @ui.page('/schedule')
    async def schedule():
        ui.label('Scheduled Matches').style('font-size: 2em; margin-bottom: 1em;')
        # Fetch scheduled matches (those with scheduled_at not None)
        matches = await Match.filter(scheduled_at__not=None).prefetch_related('tournament', 'player1', 'player2', 'player3', 'player4', 'stream_room')
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
            {'name': 'player1', 'label': 'Player 1', 'field': 'player1'},
            {'name': 'player2', 'label': 'Player 2', 'field': 'player2'},
            {'name': 'player3', 'label': 'Player 3', 'field': 'player3'},
            {'name': 'player4', 'label': 'Player 4', 'field': 'player4'},
            {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
        ]
        rows = []
        for m in matches:
            rows.append({
                'id': m.id,
                'tournament': m.tournament.name if m.tournament else '',
                'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
                'player1': m.player1.username if m.player1 else '',
                'player2': m.player2.username if m.player2 else '',
                'player3': m.player3.username if m.player3 else '',
                'player4': m.player4.username if m.player4 else '',
                'stream_room': m.stream_room.name if m.stream_room else '',
            })
        ui.table(columns=columns, rows=rows, row_key='id').style('margin-top: 1em;')