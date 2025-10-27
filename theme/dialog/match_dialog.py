import asyncio
from datetime import datetime

from nicegui import ui

from application.services import MatchService, UserService, CrewService
from application.repositories import (
    UserRepository,
    TournamentRepository,
    StreamRoomRepository,
    MatchRepository,
)
from models import Match
from theme.dialog.confirmation_dialog import ConfirmationDialog


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
        # Initialize services
        self.match_service = MatchService()
        self.user_service = UserService()
        self.crew_service = CrewService()
        # Initialize repositories
        self.user_repository = UserRepository()
        self.tournament_repository = TournamentRepository()
        self.stream_room_repository = StreamRoomRepository()
        self.match_repository = MatchRepository()

    async def open(self):
        users = await self.user_repository.get_all()
        stream_rooms = await self.stream_room_repository.get_all()
        show_all_tournaments = None
        if self.discord_id is not None:
            user = await self.user_repository.get_by_discord_id(self.discord_id)
            if not user:
                with ui.dialog() as dialog, ui.card():
                    ui.label('User not found. Please log in again.').style('color: red; font-weight: bold;')
                    ui.button('Close', color='gray', on_click=dialog.close)
                    dialog.open()
                return
            enrolled_players = await self.tournament_repository.get_enrolled_players_by_user(user)
            tournament_ids = [tp.tournament_id for tp in enrolled_players]
            tournaments = await self.tournament_repository.get_by_ids(tournament_ids) if tournament_ids else []
        else:
            tournaments = await self.tournament_repository.get_all()
        now = datetime.now()
        # Pre-fill values for edit mode
        if self.match:
            default_tournament = self.match.tournament_id if self.match.tournament_id else None
            default_date = self.match.scheduled_at.strftime('%Y-%m-%d') if self.match.scheduled_at else now.strftime('%Y-%m-%d')
            default_time = self.match.scheduled_at.strftime('%H:%M') if self.match.scheduled_at else now.strftime('%H:%M')
            players = await self.match_repository.get_players(self.match)
            player_ids = [p.user_id for p in players]
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
            if self.discord_id is not None:
                show_all_tournaments = ui.checkbox('Show all tournaments', value=False)
            if self.discord_id is None:
                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(label='Stage', options=stream_room_options, value=default_stream_room, with_input=True)

            async def get_opted_in_users(tournament_id):
                enrolled = await self.tournament_repository.get_enrolled_players_by_tournament_id(tournament_id)
                user_ids = [tp.user_id for tp in enrolled]
                # Exclude self if discord_id is set
                return [u for u in users if u.id in user_ids and (self.discord_id is None or u.discord_id != self.discord_id)]

            with ui.row().classes('items-center').style('margin-top: 1em;'):
                if self.discord_id is None:
                    selected_players = ui.select(label='Players', options={}, value=player_ids, multiple=True, with_input=True).props('use-chips')
                    selected_players.disable()
                    choose_any_players = ui.checkbox('Choose any players', value=False)
                    # Add dropdowns for commentators and trackers
                    # Pre-fill for edit mode
                    commentator_ids = [c.user_id for c in await self.match.commentators] if self.match else []
                    tracker_ids = [t.user_id for t in await self.match.trackers] if self.match else []
                    selected_commentators = ui.select(label='Commentators', options={u.id: u.preferred_name for u in users}, value=commentator_ids, multiple=True, with_input=True).props('use-chips')
                    selected_trackers = ui.select(label='Trackers', options={u.id: u.preferred_name for u in users}, value=tracker_ids, multiple=True, with_input=True).props('use-chips')
                else:
                    opponent_options = {}
                    selected_opponent = ui.select(label='Opponent', options=opponent_options, with_input=True)
                    selected_opponent.disable()
                    # For player edit, you may want to add single commentator/tracker selection if needed

            async def update_selection_options():
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
                    # If show_all_tournaments is checked, show all tournaments
                    tournaments_list = await self.tournament_repository.get_all() if show_all_tournaments and show_all_tournaments.value else tournaments
                    selected_tournament.disable()
                    selected_tournament.options = {t.id: t.name for t in tournaments_list}
                    selected_tournament.enable()
                    if tournament_id:
                        selected_opponent.disable()
                        opted_in_users = await get_opted_in_users(tournament_id)
                        selected_opponent.options = {u.id: u.preferred_name for u in opted_in_users}
                        selected_opponent.enable()
                    else:
                        selected_opponent.options = {}
                        selected_opponent.disable()

            await update_selection_options()  # Initialize options based on default tournament
            selected_tournament.on('update:model-value', lambda: asyncio.create_task(update_selection_options()))
            if self.discord_id is None:
                choose_any_players.on('update:model-value', lambda: asyncio.create_task(update_selection_options()))
            else:
                show_all_tournaments.on('update:model-value', lambda: asyncio.create_task(update_selection_options()))

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
                    new_commentator_ids = selected_commentators.value if isinstance(selected_commentators.value, list) else [selected_commentators.value]
                    new_tracker_ids = selected_trackers.value if isinstance(selected_trackers.value, list) else [selected_trackers.value]
                else:
                    opponent_id = selected_opponent.value
                    user = await self.user_repository.get_by_discord_id(self.discord_id)
                    if not user:
                        with self.dialog:
                            ui.notify('User not found. Please log in again.', color='warning')
                        return
                    new_player_ids = [user.id, opponent_id] if opponent_id else []
                    new_commentator_ids = []
                    new_tracker_ids = []
                    is_enrolled = await self.tournament_repository.is_player_enrolled_by_id(tournament_id, user)
                    if not is_enrolled:
                        await self.tournament_repository.enroll_player_by_id(tournament_id, user)

                # Validation
                if self.match:
                    # For edits, require players and core fields
                    if not (new_player_ids and tournament_id and date_value and time_value):
                        with self.dialog:
                            ui.notify('All fields are required.', color='warning')
                        return
                else:
                    # For new matches, enforce different rules for admin vs player submissions
                    if self.discord_id is None:
                        # Admin mode: do not enforce a minimum number of players; just require at least one
                        if not (tournament_id and date_value and time_value):
                            with self.dialog:
                                ui.notify('Please fill all fields.', color='warning')
                            return
                    else:
                        # Player mode: must include two players (self and opponent)
                        if not (new_player_ids and len(new_player_ids) >= 2 and tournament_id and date_value and time_value):
                            with self.dialog:
                                ui.notify('Please select at least two players and fill all fields.', color='warning')
                            return

                # Ensure all submitted players are enrolled in tournament (service handles this)
                try:
                    await self.match_service.ensure_players_enrolled(tournament_id, new_player_ids)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error enrolling players: {str(e)}', color='negative')
                    return

                if self.match:
                    # Fetch latest match from DB to check updated_at
                    latest_match = await self.match_repository.get_by_id(self.match.id)
                    if latest_match and latest_match.updated_at != self._initial_updated_at:
                        with self.dialog:
                            ui.notify('This match has been modified by another admin. Please reload and try again.', color='warning')
                        return
                    
                    try:
                        await self.match_service.update_match(
                            match_id=self.match.id,
                            tournament_id=tournament_id,
                            scheduled_date=date_value,
                            scheduled_time=time_value,
                            player_ids=new_player_ids,
                            commentator_ids=new_commentator_ids,
                            tracker_ids=new_tracker_ids,
                            comment=comment_value,
                            stream_room_id=stream_room_id if stream_room_id else None,
                            clear_seated=self._clear_seated,
                            clear_finished=self._clear_finished,
                            clear_seed=self._clear_seed
                        )
                        with self.dialog:
                            ui.notify(f'Match updated: Players={new_player_ids}, Commentators={new_commentator_ids}, Trackers={new_tracker_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}, StreamRoom={stream_room_id}', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.match)
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error updating match: {str(e)}', color='negative')
                else:
                    try:
                        await self.match_service.create_match(
                            tournament_id=tournament_id,
                            scheduled_date=date_value,
                            scheduled_time=time_value,
                            comment=comment_value,
                            player_ids=new_player_ids,
                            commentator_ids=new_commentator_ids if self.discord_id is None else None,
                            tracker_ids=new_tracker_ids if self.discord_id is None else None,
                            stream_room_id=stream_room_id if self.discord_id is None else None
                        )
                        with self.dialog:
                            if self.discord_id is None:
                                ui.notify(f'Match submitted: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                            else:
                                ui.notify(f'Match submitted: Opponent={new_player_ids[1]}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit()
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error creating match: {str(e)}', color='negative')

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
                try:
                    await self.match_repository.delete(self.match)
                    with self.dialog:
                        ui.notify('Match deleted', color='negative')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(None)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error deleting match: {str(e)}', color='negative')

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
