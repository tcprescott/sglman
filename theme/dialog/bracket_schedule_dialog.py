"""Dialog for scheduling one game of a native bracket matchup.

The tournament and both players come from the bracket, so this dialog only
collects a date/time and delegates to ``BracketService.schedule_bracket_match``,
which routes staff through ``create_match`` and the matchup's own entrants
through ``submit_match_request``. Peer of
:mod:`theme.dialog.challonge_schedule_dialog`, and shared by the player dashboard
and the staff bracket view so both surfaces get the same wording and the same
date/time inputs.

Two modes, because the two surfaces address different people: pass
``opponent_name`` for a player scheduling their own matchup ("Schedule vs Bob"),
or ``matchup_label`` for staff scheduling someone else's ("Alice vs Bob"). Only
the player mode gets a Suggest a time button — it needs the two user ids, which
the staff bracket view does not carry. Shares the button with the non-bracket
UserMatchDialog match-request dialog (``theme/dialog/match_dialog.py``).

``tenant_id`` is optional: pass it from a detached client event (the bracket
view's card click) so the service call is rebound with ``tenant_scope``; omit it
inside an ordinary page handler, where the client stash already resolves the
tenant.
"""

from contextlib import nullcontext
from typing import List, Optional

from nicegui import ui

from application.services import BracketService
from application.tenant_context import tenant_scope
from application.utils.timezone import now_local
from theme.dialog._helpers import (
    dialog_actions,
    dialog_header,
    mobile_sheet,
    native_date_input,
    native_time_input,
    render_suggest_time_button,
    submit_on_enter,
)
from theme.help import help_icon


class BracketScheduleDialog:
    def __init__(
        self,
        bracket_match_id: int,
        actor,
        *,
        opponent_name: Optional[str] = None,
        matchup_label: Optional[str] = None,
        game_number: int = 1,
        best_of: int = 1,
        tournament_name: str = '',
        tournament_id: Optional[int] = None,
        player_ids: Optional[List[int]] = None,
        tenant_id: Optional[int] = None,
        on_submit=None,
    ):
        self.bracket_match_id = bracket_match_id
        self.actor = actor
        self.opponent_name = opponent_name
        self.matchup_label = matchup_label
        self.game_number = game_number
        self.best_of = best_of
        self.tournament_name = tournament_name
        self.tournament_id = tournament_id
        self.player_ids = player_ids or []
        self.tenant_id = tenant_id
        self.on_submit = on_submit
        self.dialog = None
        self.bracket_service = BracketService()

    def _scope(self):
        return nullcontext() if self.tenant_id is None else tenant_scope(self.tenant_id)

    def _heading(self) -> str:
        game = (
            f'Schedule game {self.game_number} of {self.best_of}'
            if self.best_of > 1 else 'Schedule match'
        )
        return f'{game} vs {self.opponent_name}' if self.opponent_name else game

    def _defaults(self) -> tuple:
        now = now_local()
        return now.strftime('%Y-%m-%d'), now.strftime('%H:%M')

    async def open(self):
        default_date, default_time = self._defaults()
        can_suggest = bool(self.opponent_name and self.tournament_id and len(self.player_ids) == 2)

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(self._heading(), dialog)
            with ui.column().classes('q-pa-md gap-2'):
                if self.tournament_name:
                    ui.label(self.tournament_name).classes('text-bold')
                if self.opponent_name:
                    ui.label(f'Opponent: {self.opponent_name}').classes('text-muted')
                    ui.label('Pick a time you both can play.').classes('text-caption text-grey-7')
                elif self.matchup_label:
                    ui.label(self.matchup_label).classes('text-muted')

                with ui.row().classes('items-center gap-2'):
                    date = native_date_input('Date', default_date, required=True)
                    time = native_time_input('Time', default_time, required=True)

                if can_suggest:
                    # opponent_name is only set from the player dashboard's own
                    # page handler, never the staff bracket view's detached
                    # click — so tenant_id is never set here and the ordinary
                    # request-scoped tenant context already applies.
                    with ui.row().classes('items-center gap-1 no-wrap'):
                        render_suggest_time_button(
                            dialog,
                            get_tournament_id=lambda: self.tournament_id,
                            get_player_ids=lambda: self.player_ids,
                            get_bracket_match_id=lambda: self.bracket_match_id,
                            date=date,
                            time=time,
                            missing_message='Unable to suggest a time for this match.',
                        )
                        await help_icon('suggest-time')

            async def submit():
                if not (date.value and time.value):
                    with self.dialog:
                        ui.notify('Please choose a date and time.', color='warning')
                    return
                try:
                    with self._scope():
                        await self.bracket_service.schedule_bracket_match(
                            self.actor, self.bracket_match_id,
                            scheduled_date=date.value,
                            scheduled_time=time.value,
                        )
                    with self.dialog:
                        ui.notify(
                            'Match scheduled — your opponent will be asked to confirm.'
                            if self.opponent_name else 'Match scheduled.',
                            color='positive',
                        )
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit()
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(str(e), color='warning')

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Schedule', icon='event', on_click=submit).props('color=primary')

            submit_on_enter(dialog, submit)
            dialog.open()
