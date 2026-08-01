"""Dialog for scheduling a Challonge bracket matchup.

The tournament and both players come from the bracket, so this dialog only
collects a date/time and delegates to ChallongeService.schedule_challonge_match,
which reuses the existing match-request + acknowledgment flow. Shares its
Suggest a time button with the non-bracket UserMatchDialog match-request
dialog (``theme/dialog/match_dialog.py``), rather than silently pre-filling an
availability/occupancy-aware suggestion on open.
"""

from nicegui import ui

from application.services import ChallongeService
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


class ChallongeScheduleDialog:
    def __init__(self, challonge_match, actor, opponent_name: str, on_submit=None):
        self.challonge_match = challonge_match
        self.actor = actor
        self.opponent_name = opponent_name
        self.on_submit = on_submit
        self.dialog = None
        self.challonge_service = ChallongeService()

    async def open(self):
        cm = self.challonge_match
        now = now_local()
        default_date = now.strftime('%Y-%m-%d')
        default_time = now.strftime('%H:%M')
        player_ids = [cm.participant1.user_id, cm.participant2.user_id]

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(f'Schedule vs {self.opponent_name}', dialog)
            with ui.column().classes('q-pa-md gap-2'):
                ui.label(cm.tournament.name).classes('text-bold')
                ui.label(f'Opponent: {self.opponent_name}').classes('text-muted')
                ui.label('Pick a time you both can play.').classes('text-caption text-grey-7')

                with ui.row().classes('items-center gap-2'):
                    date = native_date_input('Date', default_date, required=True)
                    time = native_time_input('Time', default_time, required=True)

                with ui.row().classes('items-center gap-1 no-wrap'):
                    render_suggest_time_button(
                        dialog,
                        get_tournament_id=lambda: cm.tournament_id,
                        get_player_ids=lambda: player_ids,
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
                    await self.challonge_service.schedule_challonge_match(
                        challonge_match_pk=cm.id,
                        scheduled_date=date.value,
                        scheduled_time=time.value,
                        actor=self.actor,
                    )
                    with self.dialog:
                        ui.notify('Match scheduled — your opponent will be asked to confirm.', color='positive')
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
