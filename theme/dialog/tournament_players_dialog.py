from nicegui import ui

from models import TournamentPlayers, User


class TournamentPlayersDialog:
    def __init__(self, tournament):
        self.tournament = tournament
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            ui.label(f'Players enrolled in "{self.tournament.name}"').classes('text-h6')
            players = await TournamentPlayers.filter(tournament=self.tournament).prefetch_related('user')
            if not players:
                ui.label('No players enrolled.').style('color: gray;')
            else:
                with ui.column():
                    for tp in players:
                        user = tp.user
                        ui.label(f'{user.display_name or user.username} (Discord: {user.discord_id})')
            ui.button('Close', color='gray', on_click=dialog.close)
            dialog.open()
