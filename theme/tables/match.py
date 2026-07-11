from nicegui import app, background_tasks, context, ui

from application.services import MatchDisplayService, MatchService, MatchWatcherService, UserService
from theme.realtime import register_view
from theme.tables.match_grid import render_grid_slot
from theme.tables.match_handlers import MatchTableHandlersMixin
from theme.tables.match_slots import register_body_slots

# Pagination, sorting, and filtering can be implemented server-side if needed for large datasets.

# Match lifecycle states, and the subset shown by default. Kept as module constants
# so the storage default, the select options, and the "is this filter changed?"
# check in _active_filter_count cannot drift out of sync.
ALL_MATCH_STATES = ['Scheduled', 'Checked In', 'Started', 'Finished', 'Confirmed']
DEFAULT_STATE_FILTER = ['Scheduled', 'Checked In', 'Started']


class MatchTableView(MatchTableHandlersMixin):
    """
    Encapsulates the match table UI and logic for admin/player dashboards.

    Owns the filters, data refresh, single-row updates, and event wiring. The
    Vue slot templates live in ``match_slots`` (columns) and ``match_grid``
    (mobile grid); the event-handler coroutines live in ``MatchTableHandlersMixin``
    (``match_handlers``). Uses MatchService for all data operations.
    """

    def __init__(self, columns, get_query, admin_controls=False, can_crud=True, extra_slots=None, submit_match_callback=None,
                 on_edit=None, on_generate_seed=None, on_seat=None, on_start=None, on_finish=None, on_confirm=None,
                 on_edit_stream_room=None, on_assign_stations=None, player_discord_id=None, grid_breakpoint='lt.md'):
        self.columns = columns
        self.get_query = get_query
        self.grid_breakpoint = grid_breakpoint
        self.admin_controls = admin_controls
        self.can_crud = can_crud
        self.player_discord_id = player_discord_id
        self.extra_slots = extra_slots
        self.submit_match_callback = submit_match_callback
        # Optional callbacks for admin actions
        self.on_edit = on_edit
        self.on_generate_seed = on_generate_seed
        self.on_seat = on_seat
        self.on_start = on_start
        self.on_finish = on_finish
        self.on_confirm = on_confirm
        self.on_edit_stream_room = on_edit_stream_room
        self.on_assign_stations = on_assign_stations
        self.table = None
        self.tournament_filter = None
        self.tournaments_list = []  # Will be populated in _setup_ui
        self.stream_room_filter = None
        self.stream_rooms_list = []  # Will be populated in _setup_ui
        self.state_filter = None
        # Mobile collapsible-filter state (CSS gates the toggle/card to <1024px)
        self.filters_card = None
        self.filter_badge = None
        self._filters_open = False
        # Initialize services
        self.service = MatchService()
        self.display_service = MatchDisplayService()
        self.user_service = UserService()
        self.watcher_service = MatchWatcherService()
        self._setup_ui()

    def _on_state_filter_change(self, *_args, **_kwargs):
        # Store the state filter value in app.storage
        app.storage.user['state_filter'] = self.state_filter.value
        self._update_filter_badge()
        background_tasks.create(self.refresh())

    def _on_tournament_filter_change(self, *_args, **_kwargs):
        # Store the tournament ID value in app.storage
        app.storage.user['tournament_filter'] = self.tournament_filter.value
        self._update_filter_badge()
        background_tasks.create(self.refresh())

    def _on_stream_room_filter_change(self, *_args, **_kwargs):
        # Store the stream room ID value in app.storage
        app.storage.user['stream_room_filter'] = self.stream_room_filter.value
        self._update_filter_badge()
        background_tasks.create(self.refresh())

    def _toggle_filters(self):
        """Show/hide the filter card on mobile; CSS gates ``sgl-filters-open`` to <1024px."""
        self._filters_open = not self._filters_open
        if self._filters_open:
            self.filters_card.classes(add='sgl-filters-open')
        else:
            self.filters_card.classes(remove='sgl-filters-open')

    def _active_filter_count(self) -> int:
        """Number of the three filters set away from their default (state's default is Scheduled/Checked In/Started)."""
        count = 0
        if self.tournament_filter and self.tournament_filter.value:
            count += 1
        if self.stream_room_filter and self.stream_room_filter.value:
            count += 1
        if self.state_filter and set(self.state_filter.value or []) != set(DEFAULT_STATE_FILTER):
            count += 1
        return count

    def _update_filter_badge(self):
        """Sync the mobile filter-count badge with the current selections."""
        if self.filter_badge is None:
            return
        count = self._active_filter_count()
        self.filter_badge.text = str(count)
        self.filter_badge.set_visibility(count > 0)

    async def _load_tournaments(self):
        """Load all tournament names for the filter using service layer."""
        self.tournaments_list = await self.display_service.get_tournaments_for_filter()
        # Set initial value from storage or default to None (All Tournaments)
        default_tournament_id = app.storage.user.get('tournament_filter', None)
        if self.tournament_filter:
            self.tournament_filter.options = self.tournaments_list
            self.tournament_filter.value = default_tournament_id
            self.tournament_filter.update()
        self._update_filter_badge()

    async def _load_stream_rooms(self):
        """Load all stream room names for the filter using service layer."""
        self.stream_rooms_list = await self.display_service.get_stream_rooms_for_filter()
        # Set initial value from storage or default to None (All Stages)
        default_stream_room_id = app.storage.user.get('stream_room_filter', None)
        if self.stream_room_filter:
            self.stream_room_filter.options = self.stream_rooms_list
            self.stream_room_filter.value = default_stream_room_id
            self.stream_room_filter.update()
        self._update_filter_badge()

    def _setup_ui(self):
        # Action button row
        if self.submit_match_callback:
            with ui.row().classes('full-width row-spacing'):
                ui.button(
                    'Create Match' if self.admin_controls else 'Request Match',
                    icon='add',
                    on_click=self.submit_match_callback
                ).props('color=primary')

        # Mobile-only filter toggle (CSS hides this row >=1024px, where the card is
        # shown inline; below 1024px the card is collapsed until toggled open).
        with ui.row().classes('sgl-filter-toggle full-width items-center'):
            ui.button('Filters', icon='filter_list', on_click=self._toggle_filters).props('flat color=primary')
            self.filter_badge = ui.badge('0').props('color=primary')
            self.filter_badge.set_visibility(False)
            ui.space()
            ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary round dense').tooltip('Refresh table')

        # Filters section - professional card-based layout
        self.filters_card = ui.card().classes('match-filters-card')
        with self.filters_card:
            with ui.row().classes('match-filter-row'):
                # Tournament filter
                with ui.column().classes('match-filter-column'):
                    ui.label('Tournament').classes('match-filter-label')
                    self.tournament_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_tournament_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                # Stream room filter
                with ui.column().classes('match-filter-column'):
                    ui.label('Stage').classes('match-filter-label')
                    self.stream_room_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_stream_room_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                # State filter
                with ui.column().classes('match-filter-column'):
                    ui.label('State').classes('match-filter-label')
                    # Default to showing Scheduled, Checked In, and Started
                    default_states = app.storage.user.get('state_filter', list(DEFAULT_STATE_FILTER))
                    self.state_filter = ui.select(
                        options=list(ALL_MATCH_STATES),
                        value=default_states,
                        multiple=True,
                        on_change=self._on_state_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                ui.space()

                # Refresh button
                with ui.column().classes('flex-center'):
                    ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary').tooltip('Refresh table')

        # Load filters data after UI is set up
        background_tasks.create(self._load_tournaments())
        background_tasks.create(self._load_stream_rooms())

        with ui.column().classes('full-width') as table_container:
            self.table_container = table_container
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('match-table match-table-container').props(f':grid="Quasar.Screen.{self.grid_breakpoint}"')
            self.table.on('update:pagination', self._on_page_change)

        # Resolve current user's discord_id once for slot templates and event wiring.
        discord_id = app.storage.user.get('discord_id', None)

        # Register the column slot templates (see match_slots). The want_* flags
        # mirror the callback availability so the seed/state/stream-room slots
        # register exactly as before.
        register_body_slots(
            self.table,
            admin_controls=self.admin_controls,
            can_crud=self.can_crud,
            discord_id=discord_id,
            extra_slots=self.extra_slots,
            has_edit=self.on_edit is not None,
            want_seed_slot=self.admin_controls and self.on_generate_seed is not None,
            want_state_slot=self.admin_controls and (
                self.on_seat is not None or self.on_start is not None
                or self.on_finish is not None or self.on_confirm is not None
            ),
            want_stream_room_admin=self.admin_controls and self.on_edit_stream_room is not None,
            want_stream_room_readonly=self.on_edit_stream_room is None,
        )

        # Register the mobile grid slot (see match_grid).
        render_grid_slot(
            self.table, self.columns,
            admin_controls=self.admin_controls, can_crud=self.can_crud, discord_id=discord_id,
            has_edit=self.on_edit is not None,
        )

        # --- Event wiring (handler bodies live in MatchTableHandlersMixin) ---
        self.table.on('acknowledge_match', lambda event: background_tasks.create(
            self._handle_acknowledge_match(event.args, context.client)))

        for role in ['player']:
            self.table.on(f'edit_{role}', lambda event, r=role: self._handle_edit_role(r, event))
        for role in ['commentator', 'tracker']:
            self.table.on(f"edit_{role}", lambda event, r=role: self._handle_approve_role(r, event))

        if self.on_assign_stations is not None:
            self.table.on('assign_stations', lambda event: background_tasks.create(self._handle_assign_stations(event)))

        self.table.on('signup_commentator', lambda event: self._handle_signup_or_undo_role('signup', 'commentator', event.args))
        self.table.on('signup_tracker', lambda event: self._handle_signup_or_undo_role('signup', 'tracker', event.args))
        self.table.on('undo_commentator', lambda event: self._handle_signup_or_undo_role('undo', 'commentator', event.args))
        self.table.on('undo_tracker', lambda event: self._handle_signup_or_undo_role('undo', 'tracker', event.args))

        self.table.on('acknowledge_commentator', lambda event: background_tasks.create(
            self._handle_acknowledge_crew('commentator', event, context.client)))
        self.table.on('acknowledge_tracker', lambda event: background_tasks.create(
            self._handle_acknowledge_crew('tracker', event, context.client)))

        if discord_id:
            self.table.on('toggle_watch', self._handle_toggle_watch)

        # Admin-specific event wiring (slots registered above under the same conditions)
        if self.admin_controls:
            if self.on_generate_seed is not None:
                self.table.on('roll', lambda event: background_tasks.create(self._handle_roll(event)))
            if (self.on_seat is not None or self.on_start is not None
                    or self.on_finish is not None or self.on_confirm is not None):
                if self.on_seat is not None:
                    self.table.on('seat', lambda event: background_tasks.create(self._handle_seat(event)))
                if self.on_start is not None:
                    self.table.on('start', lambda event: background_tasks.create(self._handle_start(event)))
                if self.on_finish is not None:
                    self.table.on('finish', lambda event: background_tasks.create(self._handle_finish(event)))
                if self.on_confirm is not None:
                    self.table.on('confirm', lambda event: background_tasks.create(self._handle_confirm(event)))
            if self.on_edit_stream_room is not None:
                self.table.on('edit-stream-room', lambda event: background_tasks.create(self._handle_edit_stream_room(event)))

        if self.on_edit is not None:
            self.table.on('edit_match', lambda event: background_tasks.create(self._handle_edit(event)))

        # Live updates: react to match changes made by other users.
        register_view(self._on_remote_change)

    async def _on_remote_change(self, match_id, change_type):
        """Apply a match change broadcast from another user's action."""
        from application import match_events
        if change_type == match_events.CREATED:
            await self.refresh()  # a new match may not have a row yet
        else:
            # 'changed' updates in place; 'deleted' removes the row.
            await self.update_row_by_id(match_id, flash=True)

    async def refresh(self, *_args):
        """Refresh table data using service layer."""
        # Build filter parameters
        tournament_ids = None
        if self.tournament_filter and self.tournament_filter.value:
            tournament_ids = self.tournament_filter.value

        stream_room_ids = None
        if self.stream_room_filter and self.stream_room_filter.value:
            stream_room_ids = self.stream_room_filter.value

        # When the active state filter shows only pre-finish states, exclude
        # finished/confirmed matches at the DB layer instead of hydrating the
        # entire (monotonically growing) match history and dropping them in
        # Python below. Confirming requires a finish, so both hidden states
        # share ``finished_at IS NOT NULL`` — exactly what ``only_upcoming``
        # filters — making this a behavior-preserving fast path for the default
        # Scheduled/Checked In/Started view (the highest-traffic schedule tab).
        state_filter = self.state_filter.value if self.state_filter else []
        only_upcoming = bool(state_filter) and not ({'Finished', 'Confirmed'} & set(state_filter))

        rows = await self.display_service.get_matches_for_display(
            tournament_ids=tournament_ids,
            stream_room_ids=stream_room_ids,
            only_upcoming=only_upcoming,
            user_discord_id=self.player_discord_id
        )

        # Client-side filter by state (narrows within the fetched set)
        if state_filter:
            rows = [row for row in rows if row.get('state') in state_filter]

        watched_ids = await self._fetch_watched_ids()
        for row in rows:
            row['_watching'] = row.get('id') in watched_ids

        self.table.rows = rows
        self.table.update()

    async def _fetch_watched_ids(self) -> set:
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            return set()
        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            return set()
        return set(await self.watcher_service.list_watched_match_ids(user))

    def _on_page_change(self, *_):
        background_tasks.create(self.refresh())

    async def update_row_by_id(self, match_id, flash=False):
        """
        Update a single row in the table by its match ID, only if the row is currently visible.
        Uses service layer to fetch match data. When ``flash`` is set, the refreshed row
        briefly highlights so viewers notice a change made elsewhere.
        """
        # Find the index of the row with the given match_id
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is None:
            return  # Row not visible, do nothing

        # Use service to get match data
        match_data = await self.display_service.get_match_for_display(match_id)

        if not match_data:
            # Match not found, delete the row from the table
            del self.table.rows[idx]
            self.table.update()
            return

        match_data['_watching'] = self.table.rows[idx].get('_watching', False)
        if flash:
            match_data['_flash'] = True
        self.table.rows[idx] = match_data
        self.table.update()
        if flash:
            self._schedule_flash_clear(match_id)

    def _schedule_flash_clear(self, match_id):
        """Clear the transient highlight on a row a moment after it was set."""
        def clear():
            i = next((j for j, r in enumerate(self.table.rows) if r.get('id') == match_id), None)
            if i is not None and self.table.rows[i].get('_flash'):
                self.table.rows[i]['_flash'] = False
                self.table.update()
        ui.timer(1.6, clear, once=True)

    async def delete_row_by_id(self, match_id):
        """
        Delete a single row in the table by its match ID, only if the row is currently visible.
        Does not delete from the database, only removes from the table UI.
        """
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is not None:
            del self.table.rows[idx]
            self.table.update()
