from nicegui import background_tasks, ui

from application.services import CrewService, MatchService, MatchWatcherService, UserService, current_user_from_storage
from application.repositories import (
    MatchAcknowledgmentRepository,
    UserRepository,
    TournamentRepository,
    StreamRoomRepository,
    MatchRepository,
)
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_display,
    format_eastern_time,
    now_eastern,
)
from models import Match
from theme.dialog.confirmation_dialog import ConfirmationDialog


class BaseMatchDialog:
    """Base class for match dialogs with common functionality."""
    
    def __init__(self, match: Match = None, on_submit=None):
        self.match = match
        self.on_submit = on_submit
        self.dialog = None
        self._clear_seated = False
        self._clear_started = False
        self._clear_finished = False
        self._clear_confirmed = False
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
        self.acknowledgment_repository = MatchAcknowledgmentRepository()

    def _get_default_values(self):
        """Get default form values based on match state."""
        now = now_eastern()
        if self.match:
            return {
                'tournament': self.match.tournament_id if self.match.tournament_id else None,
                'date': format_eastern_date(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%Y-%m-%d'),
                'time': format_eastern_time(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%H:%M'),
                'comment': self.match.comment or '',
                'stream_room': self.match.stream_room_id if self.match.stream_room_id else None,
            }
        else:
            return {
                'tournament': None,
                'date': now.strftime('%Y-%m-%d'),
                'time': now.strftime('%H:%M'),
                'comment': '',
                'stream_room': None,
            }

    def _render_date_time_inputs(self, default_date, default_time):
        """Render date and time input fields."""
        with ui.row().classes('justify-between items-center mb-1'):
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
        
        return date, time

    def _render_clear_buttons(self):
        """Render clear buttons for edit mode."""
        def make_clear_button(label, icon, attr_flag, match_attr, is_relation=False):
            def clear():
                setattr(self, attr_flag, True)
                btn.disable()
                btn.props('outline color=gray')
            
            # For foreign key relations, check if the ID field is None
            if is_relation:
                btn_disabled = getattr(self.match, f'{match_attr}_id', None) is None
            else:
                btn_disabled = getattr(self.match, match_attr) is None
            
            btn_color = 'gray' if btn_disabled else 'negative'
            btn = ui.button(label, icon=icon, on_click=clear).props(f'outline color={btn_color}').classes('ml-1')
            if btn_disabled:
                btn.disable()
            return btn

        with ui.row().classes('items-center'):
            make_clear_button('Clear Check In', 'chair', '_clear_seated', 'seated_at')
            make_clear_button('Clear Started', 'play_arrow', '_clear_started', 'started_at')
            make_clear_button('Clear Finish', 'sports_score', '_clear_finished', 'finished_at')
            make_clear_button('Clear Confirmed', 'verified', '_clear_confirmed', 'confirmed_at')
            make_clear_button('Clear Seed', 'casino', '_clear_seed', 'generated_seed', is_relation=True)

    async def _render_watch_switch(self, user):
        if not self.match:
            return
        watcher_service = MatchWatcherService()
        initial_watching = await watcher_service.is_watching(self.match.id, user)
        match_id = self.match.id

        switch_ref = {}

        async def on_change(event):
            new_value = bool(event.value)
            try:
                if new_value:
                    await watcher_service.watch(match_id, user)
                    with self.dialog:
                        ui.notify(
                            f'Now watching match ID {match_id}. You will receive Discord DMs on updates.',
                            color='positive',
                        )
                else:
                    await watcher_service.unwatch(match_id, user)
                    with self.dialog:
                        ui.notify(
                            f'No longer watching match ID {match_id}.',
                            color='positive',
                        )
            except ValueError as e:
                switch_ref['widget'].value = not new_value
                switch_ref['widget'].update()
                with self.dialog:
                    ui.notify(str(e), color='warning')

        switch_ref['widget'] = ui.switch(
            'Watch this match (Discord DM updates)',
            value=initial_watching,
            on_change=lambda e: background_tasks.create(on_change(e)),
        )

    async def _confirm_delete(self, dialog):
        """Show delete confirmation dialog."""
        async def on_confirm():
            await self._delete_match(dialog)
        ConfirmationDialog(
            message="Are you sure you want to delete this match?",
            on_confirm=on_confirm,
            confirm_text="Delete",
            cancel_text="Cancel"
        ).open()

    async def _delete_match(self, dialog):
        """Delete the match."""
        try:
            actor = await current_user_from_storage()
            await self.match_service.delete_match(self.match.id, actor=actor)
            with dialog:
                ui.notify('Match deleted', color='negative')
                dialog.close()
            if self.on_submit:
                await self.on_submit(None)
        except PermissionError as e:
            with dialog:
                ui.notify(str(e), color='negative')
        except ValueError as e:
            with dialog:
                ui.notify(f'Error deleting match: {str(e)}', color='negative')

    async def open(self):
        """Open the dialog - must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement open()")


class AdminMatchDialog(BaseMatchDialog):
    """Admin view for creating/editing matches with full control."""
    
    def __init__(self, match=None, on_submit=None):
        super().__init__(match, on_submit)

    async def open(self):
        users = await self.user_repository.get_all()
        stream_rooms = await self.stream_room_repository.get_all()
        tournaments = await self.tournament_repository.get_all()
        
        defaults = self._get_default_values()
        
        # Get player IDs for edit mode
        if self.match:
            players = await self.match_repository.get_players(self.match)
            player_ids = [p.user_id for p in players]
            commentator_ids = [c.user_id for c in await self.match.commentators]
            tracker_ids = [t.user_id for t in await self.match.trackers]
        else:
            player_ids = []
            commentator_ids = []
            tracker_ids = []

        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog
            
            # Tournament selector
            selected_tournament = ui.select(
                label='Tournament',
                options={t.id: t.name for t in tournaments},
                value=defaults['tournament'],
                with_input=True
            )
            
            # Stream room selector
            stream_room_options = {None: '(None)'}
            stream_room_options.update({s.id: s.name for s in stream_rooms})
            selected_stream_room = ui.select(
                label='Stage',
                options=stream_room_options,
                value=defaults['stream_room'],
                with_input=True
            )

            async def get_opted_in_users(tournament_id):
                enrolled = await self.tournament_repository.get_enrolled_players_by_tournament_id(tournament_id)
                user_ids = [tp.user_id for tp in enrolled]
                return [u for u in users if u.id in user_ids]

            # Player selection
            with ui.row().classes('items-center action-row'):
                selected_players = ui.select(
                    label='Players',
                    options={},
                    value=player_ids,
                    multiple=True,
                    with_input=True
                ).props('use-chips')
                selected_players.disable()
                choose_any_players = ui.checkbox('Choose any players', value=False)
                
                # Commentators and trackers
                selected_commentators = ui.select(
                    label='Commentators',
                    options={u.id: u.preferred_name for u in users},
                    value=commentator_ids,
                    multiple=True,
                    with_input=True
                ).props('use-chips')
                
                selected_trackers = ui.select(
                    label='Trackers',
                    options={u.id: u.preferred_name for u in users},
                    value=tracker_ids,
                    multiple=True,
                    with_input=True
                ).props('use-chips')

            async def update_selection_options():
                tournament_id = selected_tournament.value
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

            await update_selection_options()
            selected_tournament.on('update:model-value', lambda: background_tasks.create(update_selection_options()))
            choose_any_players.on('update:model-value', lambda: background_tasks.create(update_selection_options()))

            # Date and time inputs
            date, time = self._render_date_time_inputs(defaults['date'], defaults['time'])
            
            # Comment
            comment_input = ui.textarea(
                label='Comment (optional)',
                value=defaults['comment'],
                placeholder='Add any notes or comments about this match...'
            ).classes('full-width')

            # Stream candidate flag
            stream_candidate_checkbox = ui.checkbox(
                'Stream candidate (flag as potential stream match)',
                value=self.match.is_stream_candidate if self.match else False,
            )

            # Clear buttons for edit mode
            if self.match:
                self._render_clear_buttons()

            # Acknowledgment status block (edit mode only)
            if self.match:
                acks = await self.acknowledgment_repository.list_for_match(self.match)
                with ui.column().classes('action-row'):
                    ui.label('Player Acknowledgments').classes('text-bold')
                    if not acks:
                        ui.label('No players assigned.').classes('text-muted')
                    else:
                        for ack in acks:
                            with ui.row().classes('items-center'):
                                if ack.acknowledged_at:
                                    ui.icon('check_circle').props('color=green')
                                    suffix = ' (auto)' if ack.auto_acknowledged else ''
                                    ui.label(
                                        f'{ack.user.preferred_name}{suffix} — '
                                        f'{format_eastern_display(ack.acknowledged_at)}'
                                    )
                                else:
                                    ui.icon('schedule').props('color=orange')
                                    ui.label(f'{ack.user.preferred_name} — pending').classes('text-muted')

            async def submit():
                tournament_id = selected_tournament.value
                stream_room_id = selected_stream_room.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                new_player_ids = selected_players.value if isinstance(selected_players.value, list) else [selected_players.value]
                new_commentator_ids = selected_commentators.value if isinstance(selected_commentators.value, list) else [selected_commentators.value]
                new_tracker_ids = selected_trackers.value if isinstance(selected_trackers.value, list) else [selected_trackers.value]

                # Validation
                if not (tournament_id and date_value and time_value):
                    with self.dialog:
                        ui.notify('Please fill all required fields.', color='warning')
                    return

                # Ensure all submitted players are enrolled in tournament
                try:
                    await self.match_service.ensure_players_enrolled(tournament_id, new_player_ids)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error enrolling players: {str(e)}', color='negative')
                    return

                actor = await current_user_from_storage()
                if self.match:
                    # Check for concurrent modifications
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
                            clear_seated=self._clear_seated,
                            clear_started=self._clear_started,
                            clear_finished=self._clear_finished,
                            clear_confirmed=self._clear_confirmed,
                            clear_seed=self._clear_seed,
                            actor=actor,
                        )
                        # Stage assignment and stream-candidate flag are gated by
                        # can_manage_streams; route them through dedicated methods.
                        if (stream_room_id or None) != self.match.stream_room_id:
                            await self.match_service.assign_stage(
                                self.match.id, stream_room_id or None, actor=actor,
                            )
                        if stream_candidate_checkbox.value != self.match.is_stream_candidate:
                            await self.match_service.set_stream_candidate(
                                self.match.id, stream_candidate_checkbox.value, actor=actor,
                            )
                        with self.dialog:
                            ui.notify('Match updated successfully', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.match)
                    except PermissionError as e:
                        with self.dialog:
                            ui.notify(str(e), color='negative')
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error updating match: {str(e)}', color='negative')
                else:
                    try:
                        new_match = await self.match_service.create_match(
                            tournament_id=tournament_id,
                            scheduled_date=date_value,
                            scheduled_time=time_value,
                            comment=comment_value,
                            player_ids=new_player_ids,
                            commentator_ids=new_commentator_ids,
                            tracker_ids=new_tracker_ids,
                            is_stream_candidate=stream_candidate_checkbox.value,
                            actor=actor,
                        )
                        if stream_room_id:
                            await self.match_service.assign_stage(new_match.id, stream_room_id, actor=actor)
                        with self.dialog:
                            ui.notify('Match created successfully', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit()
                    except PermissionError as e:
                        with self.dialog:
                            ui.notify(str(e), color='negative')
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error creating match: {str(e)}', color='negative')

            with ui.row().classes('justify-between action-row'):
                if self.match:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Delete', color='negative', on_click=lambda: background_tasks.create(self._confirm_delete(dialog)))
                else:
                    ui.button('Submit', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class UserMatchDialog(BaseMatchDialog):
    """User view for submitting match requests."""
    
    def __init__(self, discord_id, match=None, on_submit=None):
        super().__init__(match, on_submit)
        self.discord_id = discord_id

    async def open(self):
        users = await self.user_repository.get_all()
        
        # Get current user
        user = await self.user_repository.get_by_discord_id(self.discord_id)
        if not user:
            with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
                ui.label('User not found. Please log in again.').classes('text-error')
                ui.button('Close', color='gray', on_click=dialog.close)
                dialog.open()
            return
        
        # Get tournaments user is enrolled in
        enrolled_players = await self.tournament_repository.get_enrolled_players_by_user(user)
        tournament_ids = [tp.tournament_id for tp in enrolled_players]
        tournaments = await self.tournament_repository.get_by_ids(tournament_ids) if tournament_ids else []
        
        defaults = self._get_default_values()
        
        # Get player IDs for edit mode
        if self.match:
            players = await self.match_repository.get_players(self.match)
            # Find opponent (not self)
            opponent_id = next((p.user_id for p in players if p.user_id != user.id), None)
        else:
            opponent_id = None

        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog

            if self.match:
                await self._render_watch_switch(user)

            # Check if user has tournaments
            if not tournaments:
                ui.label('You have not opted into any tournaments. Please opt in before submitting a match.').classes('text-error mb-1')
                ui.button('Close', color='gray', on_click=dialog.close)
                dialog.open()
                return
            
            # Tournament selector with "show all" option
            selected_tournament = ui.select(
                label='Tournament',
                options={t.id: t.name for t in tournaments},
                value=defaults['tournament'],
                with_input=True
            )
            show_all_tournaments = ui.checkbox('Show all tournaments', value=False)

            async def get_opted_in_users(tournament_id):
                enrolled = await self.tournament_repository.get_enrolled_players_by_tournament_id(tournament_id)
                user_ids = [tp.user_id for tp in enrolled]
                # Exclude self
                return [u for u in users if u.id in user_ids and u.discord_id != self.discord_id]

            # Opponent selection
            opponent_options = {}
            selected_opponent = ui.select(
                label='Opponent',
                options=opponent_options,
                value=opponent_id,
                with_input=True
            )
            selected_opponent.disable()

            async def update_selection_options():
                tournament_id = selected_tournament.value
                
                # Update tournament list if "show all" is toggled
                tournaments_list = await self.tournament_repository.get_all() if show_all_tournaments.value else tournaments
                selected_tournament.disable()
                selected_tournament.options = {t.id: t.name for t in tournaments_list}
                selected_tournament.enable()
                
                # Update opponent options
                if tournament_id:
                    selected_opponent.disable()
                    opted_in_users = await get_opted_in_users(tournament_id)
                    selected_opponent.options = {u.id: u.preferred_name for u in opted_in_users}
                    selected_opponent.enable()
                else:
                    selected_opponent.options = {}
                    selected_opponent.disable()

            await update_selection_options()
            selected_tournament.on('update:model-value', lambda: background_tasks.create(update_selection_options()))
            show_all_tournaments.on('update:model-value', lambda: background_tasks.create(update_selection_options()))

            # Date and time inputs
            date, time = self._render_date_time_inputs(defaults['date'], defaults['time'])
            
            # Comment
            comment_input = ui.textarea(
                label='Comment (optional)',
                value=defaults['comment'],
                placeholder='Add any notes or comments about this match...'
            ).classes('full-width')

            # Clear buttons for edit mode
            if self.match:
                self._render_clear_buttons()

            async def submit():
                tournament_id = selected_tournament.value
                opponent_id = selected_opponent.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value

                # Validation - must have opponent and all fields
                if not (opponent_id and tournament_id and date_value and time_value):
                    with self.dialog:
                        ui.notify('Please select an opponent and fill all fields.', color='warning')
                    return

                new_player_ids = [user.id, opponent_id]

                # Auto-enroll user if not already enrolled
                is_enrolled = await self.tournament_repository.is_player_enrolled_by_id(tournament_id, user)
                if not is_enrolled:
                    await self.tournament_repository.enroll_player_by_id(tournament_id, user)

                # Ensure opponent is enrolled
                try:
                    await self.match_service.ensure_players_enrolled(tournament_id, new_player_ids)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error enrolling players: {str(e)}', color='negative')
                    return

                if self.match:
                    # Check for concurrent modifications
                    latest_match = await self.match_repository.get_by_id(self.match.id)
                    if latest_match and latest_match.updated_at != self._initial_updated_at:
                        with self.dialog:
                            ui.notify('This match has been modified. Please reload and try again.', color='warning')
                        return

                    try:
                        await self.match_service.update_match(
                            match_id=self.match.id,
                            tournament_id=tournament_id,
                            scheduled_date=date_value,
                            scheduled_time=time_value,
                            player_ids=new_player_ids,
                            commentator_ids=[],
                            tracker_ids=[],
                            comment=comment_value,
                            clear_seated=self._clear_seated,
                            clear_started=self._clear_started,
                            clear_finished=self._clear_finished,
                            clear_confirmed=self._clear_confirmed,
                            clear_seed=self._clear_seed,
                            actor=user,
                        )
                        with self.dialog:
                            ui.notify('Match updated successfully', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.match)
                    except PermissionError as e:
                        with self.dialog:
                            ui.notify(str(e), color='negative')
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error updating match: {str(e)}', color='negative')
                else:
                    try:
                        await self.match_service.submit_match_request(
                            tournament_id=tournament_id,
                            scheduled_date=date_value,
                            scheduled_time=time_value,
                            comment=comment_value,
                            player_ids=new_player_ids,
                            actor=user,
                        )
                        with self.dialog:
                            ui.notify('Match submitted successfully', color='positive')
                            dialog.close()
                        if self.on_submit:
                            await self.on_submit()
                    except PermissionError as e:
                        with self.dialog:
                            ui.notify(str(e), color='negative')
                    except ValueError as e:
                        with self.dialog:
                            ui.notify(f'Error creating match: {str(e)}', color='negative')

            with ui.row().classes('justify-between action-row'):
                if self.match:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Delete', color='negative', on_click=lambda: background_tasks.create(self._confirm_delete(dialog)))
                else:
                    ui.button('Submit', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
