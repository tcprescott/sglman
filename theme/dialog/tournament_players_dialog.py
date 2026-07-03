from nicegui import ui

from application.services import TournamentService
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet


class TournamentPlayersDialog:
    def __init__(self, tournament):
        self.tournament = tournament
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(f'Players — {self.tournament.name}', dialog)
            with ui.column().classes('q-pa-md'):
                players = await TournamentService().get_enrolled_players(self.tournament)
                if not players:
                    ui.label('No players enrolled.').classes('text-grey-7')
                else:
                    for tp in players:
                        user = tp.user
                        ui.label(f'{user.display_name or user.username} (Discord: {user.discord_id})')
            with dialog_actions().classes('justify-end'):
                ui.button('Close', on_click=dialog.close).props('flat')
            dialog.open()
