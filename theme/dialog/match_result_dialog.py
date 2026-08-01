"""Match Result Dialog - Enter match results and finish rankings"""

from typing import Callable, Optional

from nicegui import app, ui

from application.services import MatchService, get_user_from_discord_id
from application.utils.match_labels import match_model_label
from models import Match
from theme.dialog._helpers import dialog_actions, mobile_sheet
from theme.help import help_icon
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
        # The dispute flag, built only in 'record' mode — see open().
        self.review_flag = None
        self.review_note = None
        # Two-player path only: the winner picked but not yet recorded, and the
        # refresh hook that swaps the picker between its two steps.
        self._pending_winner_id = None
        self._refresh_choice = None
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

    def _player_label(self, player) -> str:
        station = (f'  ·  Station {player.assigned_station}'
                   if player.assigned_station else '')
        return f'{self._player_name(player)}{station}'

    def _render_heading(self, current_winner) -> None:
        """The Who-won heading, plus what is already recorded when correcting one."""
        ui.label('Who won?').classes('text-subtitle2')
        if self.is_edit:
            recorded = (self._player_name(current_winner) if current_winner
                        else 'nobody yet')
            ui.label(f'Currently recorded: {recorded}').classes('text-body2 text-grey-7')

    def _render_player_buttons(self, current_winner) -> None:
        """Step one: pick a winner. Picking does not record anything.

        Carries the heading so step two replaces it rather than sitting under a
        "Who won?" it has already answered.
        """
        self._render_heading(current_winner)
        for player in self.match.players:
            # Correcting a result: the tap that *changes* something is the solid
            # one, so the already-recorded winner cannot be mistaken for the action.
            props = 'color=primary size=lg no-caps'
            if current_winner is not None and player.id == current_winner.id:
                props += ' outline'
            ui.button(
                self._player_label(player),
                on_click=lambda _, pid=player.id: self._choose(pid),
            ).props(props).classes('full-width q-mb-sm')

    def _render_confirm_step(self, pending) -> None:
        """Step two: say what is about to happen, then commit."""
        name = self._player_name(pending)
        ui.label(f'{name} wins?').classes('text-subtitle1 text-weight-medium')
        ui.label(
            'This replaces the winner already on the board.' if self.is_edit
            else 'This records the result and hands the match to an admin.'
        ).classes('text-body2 text-grey-7')
        ui.button(
            f'Yes — {name} wins',
            on_click=lambda _, pid=pending.id: self._submit_winner(pid),
        ).props('color=primary size=lg no-caps').classes('full-width q-mb-sm')
        ui.button('Back', on_click=lambda _: self._choose(None)).props(
            'flat no-caps',
        ).classes('full-width')

    def _choose(self, winner_id: Optional[int]) -> None:
        """Select (or clear) the pending winner and re-render the picker."""
        self._pending_winner_id = winner_id
        if self._refresh_choice is not None:
            self._refresh_choice()

    async def open(self):
        """Open the dialog and load match data."""
        await self.match.fetch_related('tournament', 'players', 'players__user')

        current_winner = self._current_winner() if self.is_edit else None

        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 500px; width: 100%;'):
            mobile_sheet(self.dialog)
            with ui.row().classes('dialog-header'):
                # Named by its players, not its primary key — the dialog body
                # already repeats the tournament, so with_context=False keeps
                # the heading to the matchup.
                label = match_model_label(self.match, with_context=False)
                title = (f'Change result — {label}' if self.is_edit
                         else f'Enter match results — {label}')
                ui.label(title).classes('dialog-title')
                ui.space()
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense').tooltip('Close')

            ui.separator()

            with ui.column().classes('q-pa-md'):
                if self.match.tournament:
                    ui.label(f'Tournament: {self.match.tournament.name}').classes('text-subtitle1')

                if self.match.scheduled_at:
                    from application.utils.timezone import format_local_datetime
                    ui.label(f'Scheduled: {format_local_datetime(self.match.scheduled_at)}').classes('text-body2 text-grey-7')

            ui.separator()

            with ui.column().classes('q-pa-md q-gutter-md full-width'):
                if not self.match.players:
                    ui.label('No players assigned to this match').classes('text-grey-7')
                else:
                    if len(self.match.players) == 2:
                        # The overwhelmingly common case, and the one that happens
                        # under time pressure: name and station on the button so it
                        # can be checked against the room. Two steps, not one — the
                        # first tap only *picks*. Recording a winner settles the
                        # match and advances the bracket, and it was the single
                        # irreversible step in the whole flow that committed on one
                        # tap while check-in, start and confirm all ask first.
                        @ui.refreshable
                        def winner_choice() -> None:
                            pending = next(
                                (p for p in self.match.players
                                 if p.id == self._pending_winner_id), None,
                            )
                            if pending is None:
                                self._render_player_buttons(current_winner)
                            else:
                                self._render_confirm_step(pending)

                        self._refresh_choice = winner_choice.refresh
                        winner_choice()
                    else:
                        self._render_heading(current_winner)
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

                    if not self.is_edit:
                        # Record mode only. This is the proctor saying "I wrote
                        # down my best guess and an admin should look at it" —
                        # the admin correcting a result in edit mode is already
                        # the review, so offering the flag there would let them
                        # raise a dispute with themselves. Clearing it is the
                        # admin's own action (confirming, or the REST route).
                        ui.separator()
                        with ui.row().classes('items-center gap-1 no-wrap'):
                            self.review_flag = ui.checkbox('Flag for admin review')
                            await help_icon('proctor-result')
                        self.review_note = ui.textarea(
                            label='What happened?',
                        ).props('outlined dense autogrow').classes('full-width')
                        self.review_note.bind_visibility_from(self.review_flag, 'value')

            with dialog_actions():
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                # The two-player path submits from its own step-two button, which
                # is where the winner it is about to record is named; a footer
                # Submit would be a second, less specific way to do the same thing.
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

        Both paths land here — step two of the two-player picker, and the select
        path's Submit. The guard is released only on the ways *out* that leave the
        dialog usable: once a result is recorded the dialog is closing, and a tap
        landing during that transition would write a second audit row and fire a
        second ``match.result_recorded`` event for the same match.
        """
        if self._submitting:
            return
        self._submitting = True

        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if actor is None:
            ui.notify('You must be logged in to record match results.', color='negative')
            self._submitting = False
            return

        try:
            self.match = await self.match_service.record_match_result(
                match_id=self.match.id,
                winner_id=winner_id,
                actor=actor,
            )
        except (ValueError, PermissionError) as e:
            notify_error(e)
            self._submitting = False
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

        await self._flag_if_requested(actor)

        self.dialog.close()

    async def _flag_if_requested(self, actor) -> None:
        """Raise the dispute flag, if the proctor ticked it.

        Runs *after* ``on_submit`` on purpose: in record mode that callback is
        what marks the match finished, and ``flag_for_review`` refuses a match
        that is not finished yet. The result is already recorded by this point,
        so a failure here is reported and swallowed rather than unwound.
        """
        if self.review_flag is None or not self.review_flag.value:
            return
        note = self.review_note.value if self.review_note is not None else None
        try:
            await self.match_service.flag_for_review(self.match.id, note, actor)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Flagged for admin review.', color='warning')
