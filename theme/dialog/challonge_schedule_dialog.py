"""Dialog for scheduling a Challonge bracket matchup.

The tournament and both players come from the bracket, so this dialog only
collects a date/time — pre-filled with an availability/occupancy-aware
suggestion — and delegates to ChallongeService.schedule_challonge_match, which
reuses the existing match-request + acknowledgment flow.
"""

from nicegui import ui

from application.services import ChallongeService, MatchSuggestionService
from application.utils.timezone import format_eastern_date, format_eastern_time, now_eastern
from theme.dialog._helpers import dialog_header, submit_on_enter


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
        now = now_eastern()
        default_date = now.strftime('%Y-%m-%d')
        default_time = now.strftime('%H:%M')

        # Pre-fill with a suggested slot (availability/occupancy aware).
        try:
            player_ids = [cm.participant1.user_id, cm.participant2.user_id]
            suggested = await MatchSuggestionService().suggest_match_time(
                tournament_id=cm.tournament_id, player_ids=player_ids,
            )
            default_date = format_eastern_date(suggested)
            default_time = format_eastern_time(suggested)
        except ValueError:
            pass

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header(f'Schedule vs {self.opponent_name}', dialog)
            with ui.column().classes('q-pa-md gap-2'):
                ui.label(cm.tournament.name).classes('text-bold')
                ui.label(f'Opponent: {self.opponent_name}').classes('text-muted')
                ui.label('Pick a time you both can play — we suggested one for you.').classes(
                    'text-caption text-grey-7'
                )

                with ui.row().classes('items-center gap-2'):
                    with ui.input('Date (YYYY-MM-DD)', value=default_date).props('required') as date:
                        with ui.menu().props('no-parent-event') as date_menu:
                            with ui.date(value=default_date).bind_value(date):
                                with ui.row().classes('justify-end'):
                                    ui.button('Close', on_click=date_menu.close).props('flat')
                        with date.add_slot('append'):
                            ui.icon('edit_calendar').on('click', date_menu.open).classes('cursor-pointer')

                    with ui.input('Time (24-hour format)', value=default_time).props('required') as time:
                        with ui.menu().props('no-parent-event') as time_menu:
                            with ui.time(value=default_time).bind_value(time):
                                with ui.row().classes('justify-end'):
                                    ui.button('Close', on_click=time_menu.close).props('flat')
                        with time.add_slot('append'):
                            ui.icon('access_time').on('click', time_menu.open).classes('cursor-pointer')

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

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Schedule', icon='event', on_click=submit).props('color=primary')

            submit_on_enter(dialog, submit)
            dialog.open()
