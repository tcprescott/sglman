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

class MatchEditDialog:
    def __init__(self, match: Match, on_submit=None):
        self.match = match
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        users = await User.all().order_by('username')
        tournaments = await Tournament.all().order_by('name')
        # Pre-fill values from match
        default_tournament = self.match.tournament_id if self.match.tournament_id else None
        default_date = self.match.scheduled_at.strftime('%Y-%m-%d') if self.match.scheduled_at else ''
        default_time = self.match.scheduled_at.strftime('%H:%M') if self.match.scheduled_at else ''
        player_ids = [p.user_id for p in await MatchPlayers.filter(match=self.match)]

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            selected_tournament = ui.select(label='Tournament', options={t.id: t.name for t in tournaments}, value=default_tournament, with_input=True)
            selected_players = ui.select(label='Players', options={u.id: u.username for u in users}, value=player_ids, multiple=True, with_input=True)

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

            comment_input = ui.textarea(label='Comment (optional)', value=self.match.comment or '', placeholder='Add any notes or comments about this match...').style('width: 100%')

            async def submit():
                tournament_id = selected_tournament.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                new_player_ids = selected_players.value if isinstance(selected_players.value, list) else [selected_players.value]
                if not (new_player_ids and tournament_id and date_value and time_value):
                    ui.notify('All fields are required.', color='warning')
                    return
                match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
                self.match.tournament_id = tournament_id
                self.match.scheduled_at = match_time
                self.match.comment = comment_value
                await self.match.save()
                # Update players
                await MatchPlayers.filter(match=self.match).delete()
                for pid in new_player_ids:
                    user = await User.get(id=pid)
                    await MatchPlayers.create(match=self.match, user=user)
                ui.notify(f'Match updated: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                dialog.close()
                if self.on_submit:
                    await self.on_submit(self.match)


            async def confirm_delete():
                async def on_confirm():
                    await delete()
                ConfirmationDialog(
                    message="Are you sure you want to delete this match?",
                    on_confirm=on_confirm,
                    confirm_text="Delete",
                    cancel_text="Cancel"
                ).open()

            async def delete():
                await MatchPlayers.filter(match=self.match).delete()
                await self.match.delete()
                ui.notify('Match deleted', color='negative')
                dialog.close()
                if self.on_submit:
                    await self.on_submit(None)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Save', color='green', on_click=submit)
                ui.button('Delete', color='negative', on_click=confirm_delete)
                ui.button('Cancel', color='gray', on_click=dialog.close)
        dialog.open()
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
                if self.on_confirm:
                    ui.button(self.confirm_text, color='negative', on_click=self.on_confirm)
                else:
                    ui.button(self.confirm_text, color='negative', on_click=dialog.close)
                ui.button(self.cancel_text, color='gray', on_click=dialog.close)
        dialog.open()

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
                selected_players = ui.select(label='Players', options={u.id: u.username for u in users}, multiple=True, with_input=True)
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
                    player_ids = selected_players.value if isinstance(selected_players.value, list) else [selected_players.value]
                    if not (player_ids and len(player_ids) >= 2 and tournament_id and date_value and time_value):
                        ui.notify('Please select at least two players and fill all fields.', color='warning')
                        return
                    match = await create_match(
                        tournament_id,
                        date_value,
                        time_value,
                        comment_value,
                        player_ids=player_ids
                    )
                    ui.notify(f'Match submitted: Players={player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
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
