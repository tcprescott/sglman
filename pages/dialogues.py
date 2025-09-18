from nicegui import ui
from models import Match, User, Tournament, MatchPlayers
from datetime import datetime

async def create_match(tournament_id, date_value, time_value, comment_value, player_ids=None):
    match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    match = await Match.create(
        tournament_id=tournament_id,
        scheduled_at=match_time
    )
    if player_ids:
        for pid in player_ids:
            user = await User.get(id=pid)
            await MatchPlayers.create(match=match, user=user)
    if comment_value:
        match.comment = comment_value
        await match.save()
    return match

class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm", cancel_text="Cancel"):
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.dialog = None

    def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            ui.label(self.message).style('font-size: 1.1em; margin-bottom: 1em;')
            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button(self.confirm_text, on_click=self._confirm)
                ui.button(self.cancel_text, on_click=dialog.close)
        dialog.open()

    def _confirm(self):
        if self.on_confirm:
            self.on_confirm()
        if self.dialog:
            self.dialog.close()

class MatchSubmissionDialog:
    def __init__(self, discord_id=None, on_submit=None, select_both_players=False):
        self.discord_id = discord_id
        self.on_submit = on_submit
        self.dialog = None
        self.select_both_players = select_both_players

    async def open(self):
        users = await User.all().order_by('username')
        tournaments = await Tournament.all().order_by('name')
        now = datetime.now()
        default_date = now.strftime('%Y-%m-%d')
        default_time = now.strftime('%H:%M')

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            selected_tournament = ui.select(label='Tournament', options={t.id: t.name for t in tournaments}, with_input=True)
            if self.select_both_players:
                selected_player1 = ui.select(label='Player 1', options={u.id: u.username for u in users}, with_input=True)
                selected_player2 = ui.select(label='Player 2', options={u.id: u.username for u in users}, with_input=True)
            else:
                selected_opponent = ui.select(label='Opponent', options={u.id: u.username for u in users}, with_input=True)

            with ui.row().classes('justify-between items-center').style('margin-bottom: 1em;'):
                with ui.input('Date (YYYY-MM-DD)', value=default_date) as date:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.date(value=default_date).bind_value(date):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props('flat')
                    with date.add_slot('append'):
                        ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

                with ui.input('Time (24-hour format)', value=default_time) as time:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.time(value=default_time).bind_value(time):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props('flat')
                    with time.add_slot('append'):
                        ui.icon('access_time').on('click', menu.open).classes('cursor-pointer')

            comment_input = ui.textarea(label='Comment (optional)', placeholder='Add any notes or comments about this match...').style('width: 100%')

            async def submit():
                tournament_id = selected_tournament.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                if self.select_both_players:
                    player1_id = selected_player1.value
                    player2_id = selected_player2.value
                    if not (player1_id and player2_id and tournament_id and date_value and time_value):
                        ui.notify('All fields are required.', color='warning')
                        return
                    match = await create_match(
                        tournament_id,
                        date_value,
                        time_value,
                        comment_value,
                        player_ids=[player1_id, player2_id]
                    )
                    ui.notify(f'Match submitted: Player1={player1_id}, Player2={player2_id}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                else:
                    opponent_id = selected_opponent.value
                    if not (opponent_id and tournament_id and date_value and time_value):
                        ui.notify('All fields are required.', color='warning')
                        return
                    # Get current user by discord_id
                    user = await User.get(discord_id=self.discord_id)
                    match = await create_match(
                        tournament_id,
                        date_value,
                        time_value,
                        comment_value,
                        player_ids=[user.id, opponent_id]
                    )
                    ui.notify(f'Match submitted: Opponent={opponent_id}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                dialog.close()
                if self.on_submit:
                    await self.on_submit(match)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Submit', on_click=submit)
                ui.button('Cancel', on_click=dialog.close)
        dialog.open()
