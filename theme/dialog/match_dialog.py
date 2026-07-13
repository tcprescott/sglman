from typing import Awaitable, Callable

from nicegui import app, background_tasks, context, ui

from application.services import (
    AuthService,
    CrewService,
    MatchService,
    MatchSuggestionService,
    MatchWatcherService,
    RaceRoomService,
    RacetimeRoomService,
    StreamRoomService,
    TournamentService,
    UserService,
    get_user_from_discord_id,
)
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_display,
    format_eastern_time,
    now_eastern,
)
from models import Match
from theme.dialog._helpers import (
    dialog_actions,
    dialog_header,
    mobile_sheet,
    native_date_input,
    native_time_input,
    submit_on_enter,
)
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
        self.match_service = MatchService()
        self.user_service = UserService()
        self.crew_service = CrewService()
        self.tournament_service = TournamentService()
        self.stream_room_service = StreamRoomService()

    def _get_default_values(self):
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

    def _render_tournament_select(self, tournaments, default_value):
        return ui.select(
            label='Tournament *',
            options={t.id: t.name for t in tournaments},
            value=default_value,
            with_input=True,
        ).props('required').classes('input-full-width')

    def _render_date_time_inputs(self, default_date, default_time):
        with ui.row().classes('items-center gap-2'):
            date = native_date_input('Date', default_date, required=True)
            time = native_time_input('Time', default_time, required=True)

        return date, time

    def _render_suggest_time_button(
        self,
        *,
        get_tournament_id: Callable[[], object],
        get_player_ids: Callable[[], list],
        date,
        time,
        missing_message: str,
    ) -> None:
        """Render the 'Suggest a time' button shared by both dialogs.

        The two dialogs source player ids differently (admin from the players
        multi-select, user from the single opponent select plus their own id), so
        the ids are supplied by ``get_player_ids``, evaluated at click time.
        """
        async def suggest_time():
            tournament_id = get_tournament_id()
            player_ids = get_player_ids()
            if not tournament_id or not player_ids:
                with self.dialog:
                    ui.notify(missing_message, color='warning')
                return
            try:
                suggested = await MatchSuggestionService().suggest_match_time(
                    tournament_id=tournament_id,
                    player_ids=player_ids,
                )
                date.value = format_eastern_date(suggested)
                time.value = format_eastern_time(suggested)
                with self.dialog:
                    ui.notify('Suggested time filled in — review and save.', color='info')
            except ValueError as e:
                with self.dialog:
                    ui.notify(str(e), color='warning')

        ui.button('Suggest a time', icon='lightbulb', on_click=suggest_time).props('flat color=secondary').classes('mt-1')

    def _render_clear_buttons(self):
        def make_clear_button(label, icon, attr_flag, match_attr, is_relation=False):
            def clear():
                setattr(self, attr_flag, True)
                btn.disable()
                btn.props('outline')

            if is_relation:
                btn_disabled = getattr(self.match, f'{match_attr}_id', None) is None
            else:
                btn_disabled = getattr(self.match, match_attr) is None

            btn_color = 'gray' if btn_disabled else 'negative'
            btn = ui.button(label, icon=icon, on_click=clear).props(f'outline color={btn_color}').classes('ml-1')
            if btn_disabled:
                btn.disable()
            return btn

        with ui.row().classes('items-center flex-wrap gap-1'):
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

        async def on_change(event, client):
            new_value = bool(event.value)
            try:
                if new_value:
                    await watcher_service.watch(match_id, user)
                    with client:
                        ui.notify(
                            f'Now watching match ID {match_id}. You will receive Discord DMs on updates.',
                            color='positive',
                        )
                else:
                    await watcher_service.unwatch(match_id, user)
                    with client:
                        ui.notify(f'No longer watching match ID {match_id}.', color='positive')
            except ValueError as e:
                switch_ref['widget'].value = not new_value
                switch_ref['widget'].update()
                with client:
                    ui.notify(str(e), color='warning')

        switch_ref['widget'] = ui.switch(
            'Watch this match (Discord DM updates)',
            value=initial_watching,
            on_change=lambda e: background_tasks.create(on_change(e, context.client)),
        )

    def _confirm_delete(self, dialog):
        async def on_confirm():
            await self._delete_match(dialog)
        ConfirmationDialog(
            message="Are you sure you want to delete this match?",
            on_confirm=on_confirm,
            confirm_text="Delete",
            cancel_text="Cancel",
        ).open()

    async def _delete_match(self, dialog):
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
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

    async def _run_submit(
        self,
        dialog,
        *,
        required_fields: dict,
        tournament_id,
        player_ids: list,
        stale_message: str,
        do_update: Callable[[], Awaitable[None]],
        do_create: Callable[[], Awaitable[None]],
        create_success_message: str,
    ) -> None:
        """Shared submit pipeline for both match dialogs.

        Covers the mechanics both ``open()`` submit handlers share: required-field
        validation, ``ensure_players_enrolled``, the optimistic-lock ``updated_at``
        check on edit, and the ``PermissionError``/``ValueError`` handling ladder.
        The dialog-specific service calls are supplied by ``do_update``/``do_create``.

        ``required_fields`` is an ordered ``{label: value}`` mapping; any falsy value
        marks its label as missing.
        """
        missing = [label for label, value in required_fields.items() if not value]
        if missing:
            with self.dialog:
                ui.notify(f'Please fill required field(s): {", ".join(missing)}.', color='warning')
            return

        try:
            await self.match_service.ensure_players_enrolled(tournament_id, player_ids)
        except ValueError as e:
            with self.dialog:
                ui.notify(f'Error enrolling players: {str(e)}', color='negative')
            return

        if self.match:
            latest_match = await self.match_service.get_match_by_id(self.match.id)
            if latest_match and latest_match.updated_at != self._initial_updated_at:
                with self.dialog:
                    ui.notify(stale_message, color='warning')
                return

            try:
                await do_update()
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
                await do_create()
                with self.dialog:
                    ui.notify(create_success_message, color='positive')
                    dialog.close()
                if self.on_submit:
                    await self.on_submit()
            except PermissionError as e:
                with self.dialog:
                    ui.notify(str(e), color='negative')
            except ValueError as e:
                with self.dialog:
                    ui.notify(f'Error creating match: {str(e)}', color='negative')

    def _render_submit_footer(self, dialog, submit, *, create_label: str) -> None:
        """Render the shared footer (Delete/Cancel/primary) and wire Enter-to-submit.

        ``create_label`` is the primary-button text used when creating a new match
        ('Create' for admin, 'Submit' for user); editing always shows 'Save'.
        """
        with dialog_actions():
            if self.match:
                ui.button('Delete', on_click=lambda: self._confirm_delete(dialog)).props('color=negative flat')
            ui.space()
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save' if self.match else create_label, on_click=submit).props('color=primary')

        submit_on_enter(dialog, submit)
        dialog.open()

    async def open(self):
        raise NotImplementedError("Subclasses must implement open()")


class AdminMatchDialog(BaseMatchDialog):
    """Admin view for creating/editing matches with full control."""

    def __init__(self, match=None, on_submit=None):
        super().__init__(match, on_submit)

    async def _render_racetime_room_section(self):
        """Show the match's racetime room, or a manual-create button for it.

        Manual creation is gated on ``can_manage_sync`` (STAFF / SYNC_ADMIN) and
        works regardless of the tournament's auto-open toggle. The section is
        omitted entirely when the tournament has no racetime bot configured.
        """
        tournament = await self.tournament_service.get_tournament_by_id(self.match.tournament_id)
        if tournament is None or tournament.racetime_bot_id is None:
            return
        existing = await RacetimeRoomService().get_for_match(self.match)
        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        can_sync = await AuthService.can_manage_sync(actor)
        with ui.column().classes('gap-1'):
            ui.label('Racetime Room').classes('text-bold')
            if existing is not None:
                ui.label(f'{existing.slug} — {existing.status.value}').classes('text-grey-7')
                return
            if not can_sync:
                ui.label('No room yet.').classes('text-grey-6')
                return
            match_id = self.match.id

            async def create_room():
                try:
                    await RaceRoomService().manual_create_room(actor, match_id)
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify('Racetime room created', color='positive')
                self.dialog.close()
                if self.on_submit:
                    await self.on_submit(self.match)

            ui.button(
                'Create racetime room', icon='sports_esports', on_click=create_room,
            ).props('outline color=secondary')

    async def open(self):
        users = await self.user_service.get_all_users()
        stream_rooms = await self.stream_room_service.get_all_stream_rooms()
        tournaments = await self.tournament_service.get_all_tournaments()

        defaults = self._get_default_values()

        if self.match:
            players = await self.match_service.get_match_players(self.match)
            player_ids = [p.user_id for p in players]
            commentator_ids = [c.user_id for c in await self.match.commentators]
            tracker_ids = [t.user_id for t in await self.match.trackers]
        else:
            player_ids = []
            commentator_ids = []
            tracker_ids = []

        is_create = self.match is None
        title = 'Create Match' if is_create else 'Edit Match'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(title, dialog)
            with ui.column().classes('q-pa-md gap-2'):
                ui.label('* required').classes('required-legend')

                selected_tournament = self._render_tournament_select(tournaments, defaults['tournament'])

                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(
                    label='Stage',
                    options=stream_room_options,
                    value=defaults['stream_room'],
                    with_input=True,
                ).classes('input-full-width')

                async def get_opted_in_users(tournament_id):
                    enrolled = await self.tournament_service.get_enrolled_players_by_tournament_id(tournament_id)
                    user_ids = [tp.user_id for tp in enrolled]
                    return [u for u in users if u.id in user_ids]

                with ui.row().classes('items-start gap-2 flex-wrap'):
                    selected_players = ui.select(
                        label='Players',
                        options={},
                        value=player_ids,
                        multiple=True,
                        with_input=True,
                    ).props('use-chips')
                    selected_players.disable()
                    choose_any_players = ui.checkbox('Choose any players', value=False)

                with ui.row().classes('items-start gap-2 flex-wrap'):
                    selected_commentators = ui.select(
                        label='Commentators',
                        options={u.id: u.preferred_name for u in users},
                        value=commentator_ids,
                        multiple=True,
                        with_input=True,
                    ).props('use-chips')

                    selected_trackers = ui.select(
                        label='Trackers',
                        options={u.id: u.preferred_name for u in users},
                        value=tracker_ids,
                        multiple=True,
                        with_input=True,
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

                date, time = self._render_date_time_inputs(defaults['date'], defaults['time'])

                def get_player_ids():
                    pids = selected_players.value
                    if isinstance(pids, list):
                        return [p for p in pids if p is not None]
                    return [pids] if pids else []

                self._render_suggest_time_button(
                    get_tournament_id=lambda: selected_tournament.value,
                    get_player_ids=get_player_ids,
                    date=date,
                    time=time,
                    missing_message='Select a tournament and at least one player first.',
                )

                comment_input = ui.textarea(
                    label='Comment (optional)',
                    value=defaults['comment'],
                    placeholder='Add any notes or comments about this match...',
                ).classes('full-width')

                stream_candidate_checkbox = ui.checkbox(
                    'Stream candidate (flag as potential stream match)',
                    value=self.match.is_stream_candidate if self.match else False,
                )

                if self.match:
                    self._render_clear_buttons()

                if self.match:
                    acks = await self.match_service.list_acknowledgments(self.match)
                    with ui.column():
                        ui.label('Player Acknowledgments').classes('text-bold')
                        if not acks:
                            ui.label('No players assigned.').classes('text-grey-6')
                        else:
                            for ack in acks:
                                with ui.row().classes('items-center'):
                                    if ack.acknowledged_at:
                                        ui.icon('check_circle').classes('st-ok')
                                        suffix = ' (auto)' if ack.auto_acknowledged else ''
                                        ui.label(
                                            f'{ack.user.preferred_name}{suffix} — '
                                            f'{format_eastern_display(ack.acknowledged_at)}'
                                        )
                                    else:
                                        ui.icon('schedule').classes('st-pending')
                                        ui.label(f'{ack.user.preferred_name} — pending').classes('text-grey-6')

                if self.match:
                    await self._render_racetime_room_section()

            async def submit():
                tournament_id = selected_tournament.value
                stream_room_id = selected_stream_room.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                new_player_ids = selected_players.value if isinstance(selected_players.value, list) else [selected_players.value]
                new_commentator_ids = selected_commentators.value if isinstance(selected_commentators.value, list) else [selected_commentators.value]
                new_tracker_ids = selected_trackers.value if isinstance(selected_trackers.value, list) else [selected_trackers.value]

                async def do_update():
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
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
                    if (stream_room_id or None) != self.match.stream_room_id:
                        await self.match_service.assign_stage(
                            self.match.id, stream_room_id or None, actor=actor,
                        )
                    if stream_candidate_checkbox.value != self.match.is_stream_candidate:
                        await self.match_service.set_stream_candidate(
                            self.match.id, stream_candidate_checkbox.value, actor=actor,
                        )

                async def do_create():
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
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

                await self._run_submit(
                    dialog,
                    required_fields={'Tournament': tournament_id, 'Date': date_value, 'Time': time_value},
                    tournament_id=tournament_id,
                    player_ids=new_player_ids,
                    stale_message='This match has been modified by another admin. Please reload and try again.',
                    do_update=do_update,
                    do_create=do_create,
                    create_success_message='Match created successfully',
                )

            self._render_submit_footer(dialog, submit, create_label='Create')


class UserMatchDialog(BaseMatchDialog):
    """User view for submitting match requests."""

    def __init__(self, discord_id, match=None, on_submit=None):
        super().__init__(match, on_submit)
        self.discord_id = discord_id

    async def open(self):
        users = await self.user_service.get_all_users()

        user = await self.user_service.get_user_by_discord_id(self.discord_id)
        if not user:
            ui.notify('User not found. Please log in again.', color='negative')
            return

        enrolled_players = await self.tournament_service.get_enrolled_players_by_user(user)
        tournament_ids = [tp.tournament_id for tp in enrolled_players]
        tournaments = await self.tournament_service.get_tournaments_by_ids(tournament_ids) if tournament_ids else []

        defaults = self._get_default_values()

        if self.match:
            players = await self.match_service.get_match_players(self.match)
            opponent_id = next((p.user_id for p in players if p.user_id != user.id), None)
        else:
            opponent_id = None

        is_create = self.match is None
        title = 'Submit Match' if is_create else 'Edit Match'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(title, dialog)
            with ui.column().classes('q-pa-md gap-2'):
                if not tournaments:
                    ui.label(
                        'You have not opted into any tournaments. '
                        'Please opt in before submitting a match.'
                    ).classes('text-negative')
                    with dialog_actions().classes('justify-end'):
                        ui.button('Close', on_click=dialog.close).props('flat')
                    dialog.open()
                    return

                if self.match:
                    await self._render_watch_switch(user)

                ui.label('* required').classes('required-legend')

                selected_tournament = self._render_tournament_select(tournaments, defaults['tournament'])
                show_all_tournaments = ui.checkbox('Show all tournaments', value=False)

                async def get_opted_in_users(tournament_id):
                    enrolled = await self.tournament_service.get_enrolled_players_by_tournament_id(tournament_id)
                    user_ids = [tp.user_id for tp in enrolled]
                    return [u for u in users if u.id in user_ids and u.discord_id != self.discord_id]

                selected_opponent = ui.select(
                    label='Opponent *',
                    options={},
                    value=opponent_id,
                    with_input=True,
                ).props('required').classes('input-full-width')
                selected_opponent.disable()

                async def update_selection_options():
                    tournament_id = selected_tournament.value

                    tournaments_list = await self.tournament_service.get_all_tournaments() if show_all_tournaments.value else tournaments
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

                await update_selection_options()
                selected_tournament.on('update:model-value', lambda: background_tasks.create(update_selection_options()))
                show_all_tournaments.on('update:model-value', lambda: background_tasks.create(update_selection_options()))

                date, time = self._render_date_time_inputs(defaults['date'], defaults['time'])

                self._render_suggest_time_button(
                    get_tournament_id=lambda: selected_tournament.value,
                    get_player_ids=lambda: [user.id, selected_opponent.value] if selected_opponent.value else [],
                    date=date,
                    time=time,
                    missing_message='Select a tournament and opponent first.',
                )

                comment_input = ui.textarea(
                    label='Comment (optional)',
                    value=defaults['comment'],
                    placeholder='Add any notes or comments about this match...',
                ).classes('full-width')

                if self.match:
                    self._render_clear_buttons()

            async def submit():
                tournament_id = selected_tournament.value
                opp_id = selected_opponent.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value

                new_player_ids = [user.id, opp_id]

                async def do_update():
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

                async def do_create():
                    await self.match_service.submit_match_request(
                        tournament_id=tournament_id,
                        scheduled_date=date_value,
                        scheduled_time=time_value,
                        comment=comment_value,
                        player_ids=new_player_ids,
                        actor=user,
                    )

                await self._run_submit(
                    dialog,
                    required_fields={
                        'Tournament': tournament_id,
                        'Opponent': opp_id,
                        'Date': date_value,
                        'Time': time_value,
                    },
                    tournament_id=tournament_id,
                    player_ids=new_player_ids,
                    stale_message='This match has been modified. Please reload and try again.',
                    do_update=do_update,
                    do_create=do_create,
                    create_success_message='Match submitted successfully',
                )

            self._render_submit_footer(dialog, submit, create_label='Submit')
