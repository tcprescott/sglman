"""Match Result Dialog - Enter match results and finish rankings"""

from typing import Optional, Callable

from nicegui import ui

from models import Match


class MatchResultDialog:
    """Dialog for entering match results and finish rankings."""
    
    def __init__(
        self,
        match: Match,
        on_submit: Optional[Callable] = None
    ):
        """
        Initialize the match result dialog.
        
        Args:
            match: The match to enter results for
            on_submit: Optional callback when results are submitted
        """
        self.match = match
        self.on_submit = on_submit
        self.dialog = None
        self.winner_select = None
        
    async def open(self):
        """Open the dialog and load match data."""
        # Ensure match has players and tournament loaded
        await self.match.fetch_related('tournament', 'players', 'players__user')
        
        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 500px; width: 100%;'):
            # Header
            with ui.row().classes('dialog-header'):
                ui.label(f'Enter Match Results - Match #{self.match.id}').classes('dialog-title')
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
            
            # Winner selection
            with ui.column().classes('q-pa-md q-gutter-md full-width'):
                if not self.match.players:
                    ui.label('No players assigned to this match').classes('text-grey-7')
                else:
                    ui.label('Select Winner:').classes('text-subtitle2')
                    
                    # Build player options
                    player_options = {}
                    for player in self.match.players:
                        player_name = player.user.preferred_name or player.user.username
                        player_options[player.id] = player_name
                    
                    # Winner select dropdown
                    self.winner_select = ui.select(
                        options=player_options,
                        label='Winner',
                        with_input=True
                    ).props('outlined').classes('full-width')
            
            ui.separator()
            
            # Action buttons
            with ui.row().classes('dialog-actions'):
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                ui.button('Submit Results', on_click=self._handle_submit).props('color=primary')
        
        self.dialog.open()
    
    async def _handle_submit(self):
        """Handle match result submission."""
        try:
            if not self.winner_select.value:
                ui.notify('Please select a winner', color='warning')
                return
            
            winner_id = self.winner_select.value
            
            # Update finish ranks for all players
            # Winner gets rank 1, others get rank 2 (for now, simple 2-player logic)
            for player in self.match.players:
                if player.id == winner_id:
                    player.finish_rank = 1
                else:
                    player.finish_rank = 2
                await player.save()
            
            winner = next((p for p in self.match.players if p.id == winner_id), None)
            winner_name = winner.user.preferred_name or winner.user.username if winner else 'Unknown'
            
            ui.notify(
                f'Match results saved: {winner_name} wins!',
                color='positive'
            )
            
            # Call the on_submit callback if provided
            if self.on_submit:
                await self.on_submit(self.match)
            
            self.dialog.close()
            
        except Exception as e:
            ui.notify(f'Error saving results: {str(e)}', color='negative')
