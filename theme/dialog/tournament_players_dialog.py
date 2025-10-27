from nicegui import ui

from application.repositories import TournamentRepository


class TournamentPlayersDialog:
    def __init__(self, tournament):
        self.tournament = tournament
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog
            ui.label(f'Players enrolled in "{self.tournament.name}"').classes('text-h6')
            players = await TournamentRepository.get_enrolled_players(self.tournament)
            if not players:
                ui.label('No players enrolled.').classes('text-gray')
            else:
                with ui.column():
                    for tp in players:
                        user = tp.user
                        ui.label(f'{user.display_name or user.username} (Discord: {user.discord_id})')
            ui.button('Close', color='gray', on_click=dialog.close)
            dialog.open()
