"""Match Result Dialog - Enter match results and finish rankings"""

from typing import Optional, Callable

from nicegui import app, ui

from application.services import MatchService, get_user_from_discord_id
from models import Match
from theme.dialog._helpers import dialog_actions, mobile_sheet
from theme.notify import notify_error


class MatchResultDialog:
    """Dialog for entering match results and finish rankings.

    Two modes, one service call. ``'record'`` is the proctor finishing a live
    match; ``'edit'`` is an admin correcting a result that is already on the
    board. Edit mode only changes what the dialog *says* and which button leads
    — the caller's ``on_submit`` decides what happens next, and for an edit it
    must not re-finish an already-finished match.
    """

    def __init__(
        self,
        match: Match,
        on_submit: Optional[Callable] = None,
        mode: str = 'record',
    ):
        """
        Initialize the match result dialog.

        Args:
            match: The match to enter results for
            on_submit: Optional callback when results are submitted
            mode: ``'record'`` (finishing a match) or ``'edit'`` (correcting a
                result that is already recorded)
        """
        self.match = match
        self.on_submit = on_submit
        self.mode = mode
        self.dialog = None
        # Only set on the fallback path; the two-player path has no select, so
        # everything that dereferences it must stay guarded.
        self.winner_select = None
        self._submitting = False
        self.match_service = MatchService()

    @property
    def is_edit(self) -> bool:
        return self.mode == 'edit'

    def _current_winner(self):
        """The ``MatchPlayers`` row already ranked first, if any."""
        return next((p for p in self.match.players if p.finish_rank == 1), None)

    @staticmethod
    def _player_name(player) -> str:
        return player.user.preferred_name or player.user.username

    async def open(self):
        """Open the dialog and load match data."""
        await self.match.fetch_related('tournament', 'players', 'players__user')

        current_winner = self._current_winner() if self.is_edit else None

        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 500px; width: 100%;'):
            mobile_sheet(self.dialog)
            with ui.row().classes('dialog-header'):
                title = (f'Change result — Match #{self.match.id}' if self.is_edit
                         else f'Enter Match Results - Match #{self.match.id}')
                ui.label(title).classes('dialog-title')
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
                    if self.is_edit:
                        recorded = (self._player_name(current_winner) if current_winner
                                    else 'nobody yet')
                        ui.label(f'Currently recorded: {recorded}').classes('text-body2 text-grey-7')

                    if len(self.match.players) == 2:
                        # The overwhelmingly common case, and the one that happens
                        # under time pressure: one tap, name and station on the
                        # button so it can be checked against the room.
                        for player in self.match.players:
                            name = self._player_name(player)
                            station = (
                                f'  ·  Station {player.assigned_station}'
                                if player.assigned_station else ''
                            )
                            # Correcting a result: the tap that *changes* something
                            # is the solid one, so the already-recorded winner
                            # cannot be mistaken for the action.
                            props = 'color=primary size=lg no-caps'
                            if current_winner is not None and player.id == current_winner.id:
                                props += ' outline'
                            ui.button(
                                f'{name}{station}',
                                on_click=lambda _, pid=player.id: self._submit_winner(pid),
                            ).props(props).classes('full-width q-mb-sm')
                    else:
                        ui.label('* required').classes('required-legend')

                        player_options = {}
                        for player in self.match.players:
                            player_options[player.id] = self._player_name(player)

                        self.winner_select = ui.select(
                            options=player_options,
                            value=current_winner.id if current_winner else None,
                            label='Winner',
                            with_input=True
                        ).props('outlined required').classes('full-width')

            with dialog_actions():
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                # On the two-player path tapping a name *is* the submit, so there
                # is nothing left for a Submit button to do.
                if self.winner_select is not None:
                    ui.button(
                        'Save result' if self.is_edit else 'Submit Results',
                        on_click=self._handle_submit,
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
            winner_name = self._player_name(winner) if winner else 'Unknown'
            ui.notify(
                f'Result changed: {winner_name} wins.' if self.is_edit
                else f'Match results saved: {winner_name} wins!',
                color='positive',
            )

            if self.on_submit:
                await self.on_submit(self.match)

            self.dialog.close()
        finally:
            self._submitting = False
