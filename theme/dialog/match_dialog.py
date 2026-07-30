from nicegui import app, background_tasks, ui

from application.services import (
    AuthService,
    FeatureFlagService,
    RaceRoomService,
    RacetimeRoomService,
    get_user_from_discord_id,
)
from application.utils.timezone import format_local_display
from application.tenant_context import require_tenant_id, tenant_scope
from models import FeatureFlag
from theme.dialog._helpers import (
    dialog_actions,
    dialog_header,
    mobile_sheet,
)
from theme.dialog import _match_bracket_link as bracket_link
from theme.dialog.match_dialog_base import BaseMatchDialog, enrolment_preview

# The empty-Tournament hints differ by audience: an admin can go and make one, a
# player requesting a match cannot.
_ADMIN_NO_TOURNAMENTS_HINT = 'No tournaments yet — create one on the Tournaments tab.'
_PLAYER_NO_TOURNAMENTS_HINT = 'No tournaments are open for requests right now.'


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
        # include_inactive: a SpeedGaming placeholder entrant is inactive by
        # construction, and a synced match's roster already contains it — leaving
        # it out of the options would blank an existing player's chip.
        users = await self.user_service.get_community_people(include_inactive=True)
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

        brackets_live = await FeatureFlagService().is_enabled(FeatureFlag.BRACKETS)
        linked_bracket_match_id = await bracket_link.linked_matchup_id(
            self.bracket_service, self.match, brackets_live=brackets_live,
        )

        is_create = self.match is None
        title = 'Create Match' if is_create else 'Edit Match'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(title, dialog)
            with ui.column().classes('q-pa-md gap-2'):
                ui.label('* required').classes('required-legend')

                # SpeedGaming read-only contract (PR 7): a match materialized from
                # an SG episode has read-only ETL-owned fields (schedule / players
                # / tournament). Surface a badge and disable those inputs; the
                # service-layer guard is the actual enforcement.
                is_sg_sourced = self.match is not None and getattr(
                    self.match, 'speedgaming_episode_id', None
                ) is not None
                if is_sg_sourced:
                    with ui.row().classes('items-center gap-2'):
                        ui.badge('Synced from SpeedGaming').props('color=primary')
                        ui.label(
                            'Schedule, players, and tournament are read-only — '
                            'updated by the next SpeedGaming sync.'
                        ).classes('text-caption text-grey')

                selected_tournament = self._render_tournament_select(
                    tournaments, defaults['tournament'], _ADMIN_NO_TOURNAMENTS_HINT)

                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(
                    label='Stage',
                    options=stream_room_options,
                    value=defaults['stream_room'],
                    with_input=True,
                ).classes('input-full-width')

                # Rebound: update_selection_options re-runs as a background task on
                # every tournament change, where the contextvar is unset — the
                # scoped read raised "No tenant in context" and left Players empty.
                tenant_id = require_tenant_id()

                async def get_opted_in_users(tournament_id):
                    with tenant_scope(tenant_id):
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
                    # "Choose any players" meant "any account on the platform"
                    # and now means "any member of this community", which is not
                    # what it did either way: the list it opens is the community,
                    # and what the box changes is the *enrolment* filter.
                    choose_any_players = ui.checkbox(
                        'Include players not enrolled in this tournament', value=False,
                    )

                # Scheduling someone into a tournament they are not in does enrol
                # them, which is right — it was just invisible. Name it before the
                # save, and again in the success notification. No confirmation
                # dialog: enrolment is reversible from the tournament's own
                # entrants dialog.
                enrolment_note = ui.label('').classes('text-caption text-grey')

                async def update_enrolment_note():
                    tournament_id = selected_tournament.value
                    chosen = selected_players.value or []
                    if not tournament_id or not chosen:
                        enrolment_note.text = ''
                        return
                    enrolled = {u.id for u in await get_opted_in_users(tournament_id)}
                    by_id = {u.id: u for u in users}
                    names = [
                        by_id[uid].preferred_name
                        for uid in chosen if uid in by_id and uid not in enrolled
                    ]
                    with tenant_scope(tenant_id):
                        tournament = await self.tournament_service.get_tournament_by_id(tournament_id)
                    enrolment_note.text = enrolment_preview(
                        names, tournament.name if tournament else 'this tournament',
                    )

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

                async def refresh_selection_and_note():
                    await update_selection_options()
                    await update_enrolment_note()

                await refresh_selection_and_note()
                selected_tournament.on('update:model-value', lambda: background_tasks.create(refresh_selection_and_note()))
                choose_any_players.on('update:model-value', lambda: background_tasks.create(refresh_selection_and_note()))
                selected_players.on('update:model-value', lambda: background_tasks.create(update_enrolment_note()))

                date, time = self._render_date_time_inputs(defaults['date'], defaults['time'])

                # Lock the ETL-owned inputs on a sourced match (after the initial
                # option population, which re-enables the players select).
                if is_sg_sourced:
                    selected_tournament.disable()
                    selected_players.disable()
                    choose_any_players.disable()
                    date.disable()
                    time.disable()

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

                selected_bracket_match = await bracket_link.render_select(
                    self.bracket_service, selected_tournament,
                    brackets_live=brackets_live,
                    linked_id=linked_bracket_match_id,
                    match_id=self.match.id if self.match else None,
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
                                            f'{format_local_display(ack.acknowledged_at)}'
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
                    await bracket_link.apply_link(
                        self.bracket_service, selected_bracket_match,
                        self.match.id, linked_bracket_match_id,
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
                    await bracket_link.apply_link(
                        self.bracket_service, selected_bracket_match, new_match.id, None,
                    )

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
        # include_inactive: a SpeedGaming placeholder entrant is inactive by
        # construction, and a synced match's roster already contains it — leaving
        # it out of the options would blank an existing player's chip.
        users = await self.user_service.get_community_people(include_inactive=True)

        user = await self.user_service.get_user_by_discord_id(self.discord_id)
        if not user:
            ui.notify('User not found. Please log in again.', color='negative')
            return

        # Bracket-run tournaments are excluded: their matches come from the
        # bracket, not from a request. The service rejects them either way — this
        # keeps the dropdown from offering a choice that can only fail.
        tournaments = await self.tournament_service.list_player_requestable(user)
        enrolled_any = bool(await self.tournament_service.get_enrolled_players_by_user(user))

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
                        'Your tournaments are scheduled from their bracket — '
                        'schedule your matchup from Your Schedule instead.'
                        if enrolled_any else
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

                selected_tournament = self._render_tournament_select(
                    tournaments, defaults['tournament'], _PLAYER_NO_TOURNAMENTS_HINT)
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

                    tournaments_list = (
                        await self.tournament_service.list_player_requestable()
                        if show_all_tournaments.value else tournaments
                    )
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
