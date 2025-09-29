from datetime import datetime, timedelta
from typing import Optional
from models import Match, MatchPlayers
from tortoise.expressions import Q
from nicegui import ui

from application.room_usage import count_active_race_players_over_range

async def player_activity():
    # Example: generate time intervals for the last 2 hours, every 10 minutes
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=2)
    time_intervals = []
    current = start_time
    while current <= end_time:
        time_intervals.append(current)
        current += timedelta(minutes=10)

    # Fetch data (adjust arguments as needed)
    results = await count_active_race_players_over_range(time_intervals, future_prediction=True)

    # Prepare data for Plotly
    x = [r['timestamp'] for r in results]
    player_y = [r['player_count'] for r in results]
    match_y = [r['match_count'] for r in results]

    # Plotly figure dict
    fig = {
        'data': [
            {'x': x, 'y': player_y, 'type': 'scatter', 'mode': 'lines+markers', 'name': 'Players'},
            # {'x': x, 'y': match_y, 'type': 'scatter', 'mode': 'lines+markers', 'name': 'Matches'},
        ],
        'layout': {
            'title': 'Active Players and Matches Over Time',
            'xaxis': {'title': 'Time'},
            'yaxis': {'title': 'Count'},
        }
    }

    ui.plotly(fig)