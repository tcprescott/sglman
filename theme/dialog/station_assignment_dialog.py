"""Station Assignment Dialog - Assign stations to match players"""

from typing import Optional, Callable

from nicegui import ui

from models import Match
from application.services import MatchService


class StationAssignmentDialog:
    """Dialog for assigning stations to players in a match."""
    
    def __init__(
        self,
        match: Match,
        on_submit: Optional[Callable] = None
    ):
        """
        Initialize the station assignment dialog.
        
        Args:
            match: The match with players to assign stations to
            on_submit: Optional callback when stations are assigned
        """
        self.match = match
        self.on_submit = on_submit
        self.match_service = MatchService()
        self.dialog = None
        self.station_inputs = {}  # Dict to store station input fields by player ID
        
    async def open(self):
        """Open the dialog and load match data."""
        # Ensure match has players and tournament loaded
        await self.match.fetch_related('tournament', 'players', 'players__user')
        
        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 600px; width: 100%;'):
            # Header
            with ui.row().classes('dialog-header'):
                ui.label(f'Assign Stations - Match #{self.match.id}').classes('dialog-title')
                ui.space()
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense')
            
            ui.separator()
            
            # Match info
            with ui.column().classes('q-pa-md'):
                if self.match.tournament:
                    ui.label(f'Tournament: {self.match.tournament.name}').classes('text-subtitle1')
                
                if self.match.scheduled_at:
                    from application.utils.timezone import format_eastern_datetime
                    ui.label(f'Scheduled: {format_eastern_datetime(self.match.scheduled_at)}').classes('text-body2 text-grey-7')
            
            ui.separator()
            
            # Players and station assignments
            with ui.column().classes('q-pa-md q-gutter-md full-width'):
                if not self.match.players:
                    ui.label('No players assigned to this match').classes('text-grey-7')
                else:
                    ui.label('Assign Stations to Players:').classes('text-subtitle2')
                    
                    for player in self.match.players:
                        with ui.column().classes('q-gutter-xs full-width'):
                            # Player name
                            ui.label(player.user.preferred_name or player.user.username).classes('text-weight-medium')
                            
                            # Station input
                            station_input = ui.input(
                                label='Station',
                                placeholder='e.g., A1, B2, Station 3'
                            ).props('outlined dense').classes('full-width')
                            
                            # Pre-fill existing station if available
                            if player.assigned_station:
                                station_input.value = player.assigned_station
                            
                            # Store reference to input
                            self.station_inputs[player.id] = station_input
            
            ui.separator()
            
            # Action buttons
            with ui.row().classes('dialog-actions'):
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                ui.button('Assign Stations', on_click=self._handle_submit).props('color=primary')
        
        self.dialog.open()
    
    async def _handle_submit(self):
        """Handle station assignment submission."""
        try:
            # Collect station assignments
            assignments = {}
            for player_id, station_input in self.station_inputs.items():
                station = station_input.value.strip() if station_input.value else None
                assignments[player_id] = station
            
            # Update each player's assigned station
            for player in self.match.players:
                if player.id in assignments:
                    player.assigned_station = assignments[player.id]
                    await player.save()
            
            ui.notify(
                f'Stations assigned successfully for match #{self.match.id}',
                color='positive'
            )
            
            # Call the on_submit callback if provided
            if self.on_submit:
                await self.on_submit(self.match)
            
            self.dialog.close()
            
        except Exception as e:
            ui.notify(f'Error assigning stations: {str(e)}', color='negative')
