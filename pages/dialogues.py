from nicegui import ui
from models import Match, User, Tournament, MatchPlayers
from datetime import datetime

class MatchSubmissionDialog:
    def __init__(self, discord_id, on_submit=None):
        self.discord_id = discord_id
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        users = await User.all().order_by('username')
        tournaments = await Tournament.all().order_by('name')
        now = datetime.now()
        default_date = now.strftime('%Y-%m-%d')
        default_time = now.strftime('%H:%M')

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            selected_tournament = ui.select(label='Tournament', options={t.id: t.name for t in tournaments}, with_input=True)
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

            # Add comment input field, full width
            comment_input = ui.textarea(label='Comment (optional)', placeholder='Add any notes or comments about this match...').style('width: 100%')

            async def submit():
                opponent_id = selected_opponent.value
                tournament_id = selected_tournament.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                if not (opponent_id and tournament_id and date_value and time_value):
                    ui.notify('All fields are required.', color='warning')
                    return
                match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
                match = await Match.create(
                    tournament_id=tournament_id,
                    scheduled_at=match_time
                )
                await MatchPlayers.create(match=match, user=await User.get(discord_id=self.discord_id))
                await MatchPlayers.create(match=match, user=await User.get(id=opponent_id))
                # Optionally store or process the comment
                if comment_value:
                    match.comment = comment_value
                    await match.save()
                ui.notify(f'Match submitted: Opponent={opponent_id}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                dialog.close()
                if self.on_submit:
                    await self.on_submit(match)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Submit', on_click=submit)
                ui.button('Cancel', on_click=dialog.close)
        dialog.open()
