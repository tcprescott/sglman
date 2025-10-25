"""Admin Settings/Tournaments Management Page"""

import asyncio

from nicegui import ui

from models import Tournament
from theme.dialog import TournamentDialog
from theme.tables.tournament import TournamentTableView


def admin_settings_page() -> None:
    admin_tournaments_page()


def admin_tournaments_page() -> None:
    with ui.row().style('width: 100%;'):
        ui.label('Tournament Management').style('font-size: 2em; margin-bottom: 1em;')
    
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
        {'name': 'name', 'label': 'Name', 'field': 'name'},
        {'name': 'description', 'label': 'Description', 'field': 'description'},
        {'name': 'seed_generator', 'label': 'Seed Generator', 'field': 'seed_generator'},
        {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
        {'name': 'players_per_match', 'label': 'Players/Match', 'field': 'players_per_match'},
        {'name': 'average_match_duration', 'label': 'Avg Match Duration (min)', 'field': 'average_match_duration'},
        {'name': 'max_match_duration', 'label': 'Max Match Duration (min)', 'field': 'max_match_duration'},
        {'name': 'staff_administered', 'label': 'Staff Administered', 'field': 'staff_administered'},
        {'name': 'player_count', 'label': 'Player Count', 'field': 'player_count'},
    ]

    async def add_tournament():
        async def after_submit(_):
            await table_view.refresh()
        dialog = TournamentDialog(on_submit=after_submit)
        await dialog.open()

    def get_query():
        return Tournament.all()
    
    table_view = TournamentTableView(
        columns=columns, get_query=get_query, submit_tournament_callback=add_tournament)
    
    def on_tab_selected():
        asyncio.create_task(table_view.refresh())
    ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Tournaments' else None)
