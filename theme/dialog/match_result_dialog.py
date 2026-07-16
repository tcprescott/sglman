"""Match Result Dialog - Enter match results and finish rankings"""

from typing import Optional, Callable

from nicegui import app, ui

from application.services import MatchService, get_user_from_discord_id
from models import Match
from theme.dialog._helpers import dialog_actions, mobile_sheet
from theme.notify import notify_error


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
        self.match_service = MatchService()

    async def open(self):
        """Open the dialog and load match data."""
        await self.match.fetch_related('tournament', 'players', 'players__user')

        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 500px; width: 100%;'):
            mobile_sheet(self.dialog)
            with ui.row().classes('dialog-header'):
                ui.label(f'Enter Match Results - Match #{self.match.id}').classes('dialog-title')
                ui.space()
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense').tooltip('Close')

            ui.separator()

            with ui.column().classes('q-pa-md'):
                if self.match.tournament:
                    ui.label(f'Tournament: {self.match.tournament.name}').classes('text-subtitle1')

                if self.match.scheduled_at:
                    from application.utils.timezone import format_eastern_datetime
                    ui.label(f'Scheduled: {format_eastern_datetime(self.match.scheduled_at)}').classes('text-body2 text-grey-7')

            ui.separator()

            with ui.column().classes('q-pa-md q-gutter-md full-width'):
                if not self.match.players:
                    ui.label('No players assigned to this match').classes('text-grey-7')
                else:
                    ui.label('Select Winner:').classes('text-subtitle2')
                    ui.label('* required').classes('required-legend')

                    player_options = {}
                    for player in self.match.players:
                        player_name = player.user.preferred_name or player.user.username
                        player_options[player.id] = player_name

                    self.winner_select = ui.select(
                        options=player_options,
                        label='Winner',
                        with_input=True
                    ).props('outlined required').classes('full-width')

            with dialog_actions():
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                submit_button = ui.button(
                    'Submit Results', on_click=self._handle_submit,
                ).props('color=primary')
                if self.winner_select is not None:
                    submit_button.bind_enabled_from(
                        self.winner_select, 'value',
                        backward=lambda v: v is not None,
                    )

        self.dialog.open()

    async def _handle_submit(self):
        """Handle match result submission."""
        if not self.winner_select.value:
            ui.notify('Please select a winner', color='warning')
            return

        winner_id = self.winner_select.value

        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if actor is None:
            ui.notify('You must be logged in to record match results.', color='negative')
            return

        try:
            self.match = await self.match_service.record_match_result(
                match_id=self.match.id,
                winner_id=winner_id,
                actor=actor,
            )
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return

        winner = next((p for p in self.match.players if p.id == winner_id), None)
        winner_name = winner.user.preferred_name or winner.user.username if winner else 'Unknown'
        ui.notify(f'Match results saved: {winner_name} wins!', color='positive')

        if self.on_submit:
            await self.on_submit(self.match)

        self.dialog.close()
