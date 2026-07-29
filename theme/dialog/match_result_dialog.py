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
        # Only set on the fallback path; the two-player path has no select, so
        # everything that dereferences it must stay guarded.
        self.winner_select = None
        self._submitting = False
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
                    ui.label('Who won?').classes('text-subtitle2')

                    if len(self.match.players) == 2:
                        # The overwhelmingly common case, and the one that happens
                        # under time pressure: one tap, name and station on the
                        # button so it can be checked against the room.
                        for player in self.match.players:
                            name = player.user.preferred_name or player.user.username
                            station = (
                                f'  ·  Station {player.assigned_station}'
                                if player.assigned_station else ''
                            )
                            ui.button(
                                f'{name}{station}',
                                on_click=lambda _, pid=player.id: self._submit_winner(pid),
                            ).props('color=primary size=lg no-caps').classes('full-width q-mb-sm')
                    else:
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
                # On the two-player path tapping a name *is* the submit, so there
                # is nothing left for a Submit button to do.
                if self.winner_select is not None:
                    ui.button(
                        'Submit Results', on_click=self._handle_submit,
                    ).props('color=primary').bind_enabled_from(
                        self.winner_select, 'value',
                        backward=lambda v: v is not None,
                    )

        self.dialog.open()

    async def _handle_submit(self):
        """Submit the winner chosen in the select (the non-two-player path)."""
        if self.winner_select is None or not self.winner_select.value:
            ui.notify('Please select a winner', color='warning')
            return

        await self._submit_winner(self.winner_select.value)

    async def _submit_winner(self, winner_id: int):
        """Record ``winner_id`` (a ``MatchPlayers`` row id) as the winner.

        Both paths land here. Tapping a name is now a single interaction, so an
        impatient double-tap would otherwise fire the service twice.
        """
        if self._submitting:
            return
        self._submitting = True
        try:
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
        finally:
            self._submitting = False
