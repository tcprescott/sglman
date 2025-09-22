import asyncio
from datetime import datetime
from nicegui import ui
from models import Match, MatchPlayers, StreamRoom, Tournament, User
from theme.dialog.confirmation_dialog import ConfirmationDialog

from app_logic.match import create_match

class MatchDialog:
    def __init__(self, match: Match = None, discord_id: int=None, on_submit=None):
        self.match = match
        self.discord_id = discord_id
        self.on_submit = on_submit
        self.dialog = None
        self._clear_seated = False
        self._clear_finished = False
        self._clear_seed = False
        self._initial_updated_at = match.updated_at if match else None

    async def open(self):
        from models import TournamentPlayers, Tournament
        users = await User.all().order_by('username')
        stream_rooms = await StreamRoom.all().order_by('name')
        if self.discord_id is not None:
            user = await User.get(discord_id=self.discord_id)
            user_tournament_links = await TournamentPlayers.filter(user=user)
            tournament_ids = [tp.tournament_id for tp in user_tournament_links]
            tournaments = await Tournament.filter(id__in=tournament_ids).order_by('name')
        else:
            tournaments = await Tournament.all().order_by('name')
        now = datetime.now()
        # Pre-fill values for edit mode
        if self.match:
            default_tournament = self.match.tournament_id if self.match.tournament_id else None
            default_date = self.match.scheduled_at.strftime('%Y-%m-%d') if self.match.scheduled_at else now.strftime('%Y-%m-%d')
            default_time = self.match.scheduled_at.strftime('%H:%M') if self.match.scheduled_at else now.strftime('%H:%M')
            player_ids = [p.user_id for p in await MatchPlayers.filter(match=self.match)]
            comment_value = self.match.comment or ''
            default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        else:
            default_tournament = None
            default_date = now.strftime('%Y-%m-%d')
            default_time = now.strftime('%H:%M')
            player_ids = []
            comment_value = ''
            default_stream_room = None

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            if self.discord_id is not None and not tournaments:
                ui.label('You have not opted into any tournaments. Please opt in before submitting a match.').style('color: red; font-weight: bold; margin-bottom: 1em;')
                ui.button('Close', color='gray', on_click=dialog.close)
                dialog.open()
                return
            selected_tournament = ui.select(label='Tournament', options={t.id: t.name for t in tournaments}, value=default_tournament, with_input=True)
            if self.discord_id is None:
                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(label='Stream Room', options=stream_room_options, value=default_stream_room, with_input=True)

            from models import TournamentPlayers
            async def get_opted_in_users(tournament_id):
                links = await TournamentPlayers.filter(tournament_id=tournament_id)
                user_ids = [tp.user_id for tp in links]
                # Exclude self if discord_id is set
                return [u for u in users if u.id in user_ids and (self.discord_id is None or u.discord_id != self.discord_id)]

            with ui.row().classes('items-center').style('margin-top: 1em;'):
                if self.discord_id is None:
                    selected_players = ui.select(label='Players', options={}, value=player_ids, multiple=True, with_input=True)
                    selected_players.disable()
                    choose_any_players = ui.checkbox('Choose any players', value=False)
                else:
                    opponent_options = {}
                    selected_opponent = ui.select(label='Opponent', options=opponent_options, with_input=True)
                    selected_opponent.disable()

            async def update_selection_options(e):
                tournament_id = selected_tournament.value
                if self.discord_id is None:
                    if choose_any_players.value and tournament_id:
                        selected_players.disable()
                        selected_players.options = {u.id: u.preferred_name for u in users}
                        selected_players.enable()
                    elif tournament_id:
                        selected_players.disable()
                        opted_in_users = await get_opted_in_users(tournament_id)
                        selected_players.options = {u.id: u.preferred_name for u in opted_in_users}
                        selected_players.enable()
                    else:
                        selected_players.options = {}
                        selected_players.disable()
                else:
                    if tournament_id:
                        selected_opponent.disable()
                        opted_in_users = await get_opted_in_users(tournament_id)
                        selected_opponent.options = {u.id: u.preferred_name for u in opted_in_users}
                        selected_opponent.enable()
                    else:
                        selected_opponent.options = {}
                        selected_opponent.disable()
            selected_tournament.on('update:model-value', lambda e: asyncio.create_task(update_selection_options(e)))
            if self.discord_id is None:
                choose_any_players.on('update:model-value', lambda e: asyncio.create_task(update_selection_options(e)))

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

            comment_input = ui.textarea(label='Comment (optional)', value=comment_value, placeholder='Add any notes or comments about this match...').style('width: 100%')

            if self.match:
                def make_clear_button(label, attr_flag, match_attr):
                    def clear():
                        setattr(self, attr_flag, True)
                        btn.disable()
                        btn.props('outline color=gray')
                    btn_disabled = getattr(self.match, match_attr) is None
                    btn_color = 'gray' if btn_disabled else 'negative'
                    btn = ui.button(label, on_click=clear).props(f'outline color={btn_color}').style('margin-left: 1em;')
                    if btn_disabled:
                        btn.disable()
                    return btn

                with ui.row().classes('items-center'):
                    make_clear_button('Clear Seated', '_clear_seated', 'seated_at')
                    make_clear_button('Clear Finish', '_clear_finished', 'finished_at')
                    make_clear_button('Clear Seed', '_clear_seed', 'generated_seed')

            async def submit():
                tournament_id = selected_tournament.value
                if self.discord_id is None:
                    stream_room_id = selected_stream_room.value
                else:
                    stream_room_id = None
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                # Determine player IDs
                if self.discord_id is None:
                    new_player_ids = selected_players.value if isinstance(selected_players.value, list) else [selected_players.value]
                else:
                    opponent_id = selected_opponent.value
                    user = await User.get(discord_id=self.discord_id)
                    new_player_ids = [user.id, opponent_id] if opponent_id else []

                # Validation
                if self.match:
                    if not (new_player_ids and tournament_id and date_value and time_value):
                        with self.dialog:
                            ui.notify('All fields are required.', color='warning')
                        return
                else:
                    if not (new_player_ids and len(new_player_ids) >= 2 and tournament_id and date_value and time_value):
                        with self.dialog:
                            ui.notify('Please select at least two players and fill all fields.', color='warning')
                        return

                # Create or update match
                from models import TournamentPlayers, Tournament
                # Ensure all submitted players are enrolled in TournamentPlayers for this tournament
                existing_links = await TournamentPlayers.filter(tournament_id=tournament_id)
                existing_player_ids = {tp.user_id for tp in existing_links}
                for pid in new_player_ids:
                    if pid not in existing_player_ids:
                        tournament = await Tournament.get(id=tournament_id)
                        user = await User.get(id=pid)
                        await TournamentPlayers.create(user=user, tournament=tournament)

                if self.match:
                    # Fetch latest match from DB to check updated_at
                    latest_match = await Match.get(id=self.match.id)
                    if latest_match.updated_at != self._initial_updated_at:
                        with self.dialog:
                            ui.notify('This match has been modified by another admin. Please reload and try again.', color='warning')
                        return
                    match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
                    self.match.tournament_id = tournament_id
                    self.match.stream_room_id = stream_room_id if stream_room_id else None
                    self.match.scheduled_at = match_time
                    self.match.comment = comment_value
                    if hasattr(self, '_clear_seated') and self._clear_seated:
                        self.match.seated_at = None
                    if hasattr(self, '_clear_finished') and self._clear_finished:
                        self.match.finished_at = None
                    if hasattr(self, '_clear_seed') and self._clear_seed:
                        self.match.generated_seed = None
                    await self.match.save()
                    # Update players
                    await MatchPlayers.filter(match=self.match).delete()
                    for pid in new_player_ids:
                        user = await User.get(id=pid)
                        await MatchPlayers.create(match=self.match, user=user)
                    with self.dialog:
                        ui.notify(f'Match updated: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}, StreamRoom={stream_room_id}', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                else:
                    match = await create_match(
                        tournament_id,
                        date_value,
                        time_value,
                        comment_value,
                        player_ids=new_player_ids
                    )
                    with self.dialog:
                        if self.discord_id is None:
                            ui.notify(f'Match submitted: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                        else:
                            ui.notify(f'Match submitted: Opponent={new_player_ids[1]}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(match)

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
                with self.dialog:
                    with self.dialog:
                        ui.notify('Match deleted', color='negative')
                        dialog.close()
                if self.on_submit:
                    await self.on_submit(None)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.match:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Delete', color='negative', on_click=confirm_delete)
                else:
                    ui.button('Submit', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            # Allow Enter to submit

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
