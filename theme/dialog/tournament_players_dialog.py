from nicegui import ui

from application.repositories import TournamentRepository
from theme.dialog._helpers import dialog_header


class TournamentPlayersDialog:
    def __init__(self, tournament):
        self.tournament = tournament
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header(f'Players — {self.tournament.name}', dialog)
            with ui.column().classes('q-pa-md'):
                players = await TournamentRepository.get_enrolled_players(self.tournament)
                if not players:
                    ui.label('No players enrolled.').classes('text-grey-7')
                else:
                    for tp in players:
                        user = tp.user
                        ui.label(f'{user.display_name or user.username} (Discord: {user.discord_id})')
            ui.separator()
            with ui.row().classes('justify-end q-pa-sm'):
                ui.button('Close', on_click=dialog.close).props('flat')
            dialog.open()
