from datetime import timedelta

from nicegui import app, background_tasks, context, ui

from application.services import (
    MatchDisplayService,
    MatchService,
    MatchStreamVolunteerService,
    MatchWatcherService,
    UserService,
)
from application.tenant_context import get_current_tenant_id
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from application.utils.timezone import local_day_bounds, today_local
from theme.empty_state import no_data_slot
from theme.realtime import register_view
from theme.tables.admin_crud import capture_render_context, scoped_background
from theme.tables.export import csv_export_button
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_grid import render_grid_slot
from theme.tables.match_handlers import MatchTableHandlersMixin
from theme.tables.match_slots import CANDIDATE_STAGE, register_body_slots
from theme.tables.preferences import (
    customize_table,
    preferences_button,
    row_count_label,
    search_input,
    sticky_header,
)

# Pagination, sorting, and filtering can be implemented server-side if needed for large datasets.

# Match lifecycle states, and the subset shown by default. Kept as module constants
# so the storage default, the select options, and the "is this filter changed?"
# check in _active_filter_count cannot drift out of sync.
ALL_MATCH_STATES = ['Scheduled', 'Checked In', 'Started', 'Finished', 'Confirmed']
DEFAULT_STATE_FILTER = ['Scheduled', 'Checked In', 'Started']

# Day scopes for the Day filter. The board had no day or now anchor at all, so
# an operator standing at a venue scrolled ~8 screenfuls of phone to find a
# match by eye — the cards carry every detail and nothing narrowed them to the
# day being run. ``ALL_DAYS`` is the default, so nothing is hidden until asked.
ALL_DAYS = 'All dates'
DAY_SCOPES = [ALL_DAYS, 'Today', 'Tomorrow', 'Next 7 days']

#: A tournament-id list no row can match. ``tournament_ids=None`` means "every
#: tournament", so an *empty* narrowing has to be spelled some other way or a
#: scoped board would fall open to the whole community.
_MATCHES_NOTHING = [0]
#: ``scope -> (days from today for the first day, for the last day)``, inclusive.
_DAY_OFFSETS = {'Today': (0, 0), 'Tomorrow': (1, 1), 'Next 7 days': (0, 6)}


def day_scope_window(scope: str):
    """UTC ``(start, end)`` epoch seconds for a day scope, or ``None`` for all.

    Resolved on the *display* clock — "today" at 21:00 in New York is not today
    in London — and through ``local_day_bounds`` so the window is half-open and
    does not lose its final second.
    """
    offsets = _DAY_OFFSETS.get(scope)
    if offsets is None:
        return None
    first, last = offsets
    today = today_local()
    start, end = local_day_bounds(today + timedelta(days=first), today + timedelta(days=last))
    return start.timestamp(), end.timestamp()


class MatchTableView(MatchTableHandlersMixin):
    """
    Encapsulates the match table UI and logic for admin/player dashboards.

    Owns the filters, data refresh, single-row updates, and event wiring. The
    Vue slot templates live in ``match_slots`` (columns) and ``match_grid``
    (mobile grid); the event-handler coroutines live in ``MatchTableHandlersMixin``
    (``match_handlers``). Uses MatchService for all data operations.
    """

    def __init__(self, columns, get_query, admin_controls=False, access=None, extra_slots=None, submit_match_callback=None,
                 on_edit=None, on_generate_seed=None, on_seat=None, on_start=None, on_finish=None, on_confirm=None,
                 on_edit_result=None, on_set_stage=None, on_assign_stations=None,
                 player_discord_id=None, grid_breakpoint='lt.md',
                 row_sort=None, exclude_racetime=False, on_rows_changed=None, actions_first=False,
                 storage_key='match', default_state_filter=None, match_ids=None,
                 scope_tournament_ids=None, table_key=None, searchable=False):
        self.columns = columns
        # When set, this board's desktop columns follow the viewer's saved
        # layout. Each surface built on this class passes its **own** key: a
        # proctor's column choices must not follow them onto the admin board.
        self.table_key = table_key
        # A text box over the visible columns, for the boards where finding one
        # row is the actual task. Not persisted: it is working state.
        self.searchable = searchable
        self._plan = None
        self.get_query = get_query
        self.grid_breakpoint = grid_breakpoint
        self.admin_controls = admin_controls
        # What this viewer may do, one field per service gate (match_access).
        # Defaults to a spectator: the player-facing boards pass nothing, and
        # every capability-gated control is also behind ``admin_controls``.
        self.access = access or MatchBoardAccess()
        self.player_discord_id = player_discord_id
        # Every board gets its own filter namespace and its own default state
        # set — see _skey. Pass a distinct storage_key from each construction
        # site; the fallback exists only so a bare view still works.
        self.storage_key = storage_key
        self.default_state_filter = default_state_filter
        # Board-shaping hooks. ``row_sort`` reorders the fetched rows (the
        # proctor board sorts by what needs doing next rather than by clock),
        # ``exclude_racetime`` drops rows no on-site proctor can act on,
        # ``on_rows_changed`` lets a caller mirror the row set (a summary strip),
        # and ``actions_first`` hoists the mobile card's action row.
        self.row_sort = row_sort
        # A deep link focuses the board on specific matches. It narrows the query
        # and suspends the State filter — a link to a Confirmed match must not
        # land on an empty board because the board's default set hides it — but
        # it never writes to the stored filters, so leaving the focus restores
        # whatever the operator had chosen.
        self.match_ids = list(match_ids) if match_ids else None
        # A hard bound on which tournaments this board may show at all — set for
        # a viewer whose authority is per tournament. Distinct from the
        # Tournament *filter*, which is the operator's own choice **within** the
        # scope; ``refresh`` intersects the two, so choosing a tournament cannot
        # widen the board past what the viewer operates.
        self.scope_tournament_ids = list(scope_tournament_ids) if scope_tournament_ids is not None else None
        self.exclude_racetime = exclude_racetime
        self.on_rows_changed = on_rows_changed
        self.actions_first = actions_first
        self.extra_slots = extra_slots
        self.submit_match_callback = submit_match_callback
        # Optional callbacks for admin actions
        self.on_edit = on_edit
        self.on_generate_seed = on_generate_seed
        self.on_seat = on_seat
        self.on_start = on_start
        self.on_finish = on_finish
        self.on_confirm = on_confirm
        # Correcting an already-recorded result: the admin's half of "the proctor
        # records their best guess". Reaches the same service as on_finish's
        # dialog, but must never re-finish the match.
        self.on_edit_result = on_edit_result
        # Where this match is streamed, written from the row's Stage select —
        # a real stage, the ``Candidate`` pseudo-stage, or nothing.
        self.on_set_stage = on_set_stage
        self.on_assign_stations = on_assign_stations
        self.table = None
        self.tournament_filter = None
        self.tournaments_list = []  # Will be populated in _setup_ui
        self.stage_filter = None
        self.stages_list = []  # Will be populated in _setup_ui
        self.state_filter = None
        self.day_filter = None
        # Mobile collapsible-filter state (CSS gates the toggle/card to <1024px)
        self.filters_card = None
        self.filter_badge = None
        self._filters_open = False
        # Capture the tenant at build time (context is live here). Background
        # tasks — filter/page refreshes, filter-option loads — run outside the
        # slot/request context where neither the contextvar nor the per-client
        # stash is reachable, so scoped repository reads would raise
        # ``require_tenant_id()``; ``_bg`` rebinds this captured tenant.
        self._tenant_id = get_current_tenant_id()
        self._render_context = capture_render_context()
        # True until the stored filters have been restored, so restoring them
        # does not each trigger their own table load. See _refresh_unless_initializing.
        self._initializing = True
        # Initialize services
        self.service = MatchService()
        self.display_service = MatchDisplayService()
        self.user_service = UserService()
        self.watcher_service = MatchWatcherService()
        self.stream_volunteer_service = MatchStreamVolunteerService()
        self._setup_ui()

    def _bg(self, coro) -> None:
        """Schedule ``coro`` with this view's tenant *and* display zone rebound."""
        scoped_background(self._render_context, coro)

    def _skey(self, name: str) -> str:
        """Session key for one of this view's filters.

        Namespaced per view: four boards share one session, and before this a
        filter change on the admin Schedule tab silently retargeted the home
        schedule board and the proctor station too.
        """
        return f'{self.storage_key}:{name}'

    def _stored_or_default_states(self) -> list:
        """This board's opening State selection.

        A stored choice wins; otherwise the board's own default (the admin
        board needs ``Finished`` — that set is its work). Split out of
        ``_setup_ui`` so the precedence is testable without a slot context.
        """
        return tenant_session_get(
            self._skey('state_filter'),
            list(self.default_state_filter or DEFAULT_STATE_FILTER),
        )

    def _refresh_unless_initializing(self) -> None:
        """Reload the table for a *user's* filter change.

        Restoring a stored filter during the initial load also fires these
        handlers, and each one used to schedule its own full reload — three table
        loads per page render instead of one. During initialization the reload is
        left to :meth:`_initial_load`, which runs once after every filter is
        restored (and therefore reads the final filter state).
        """
        if self._initializing:
            return
        self._bg(self.refresh())

    def _on_state_filter_change(self, *_args, **_kwargs):
        # Tenant-scoped: a filter is meaningful only within its own community.
        tenant_session_set(self._skey('state_filter'), self.state_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_day_filter_change(self, *_args, **_kwargs):
        tenant_session_set(self._skey('day_filter'), self.day_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_tournament_filter_change(self, *_args, **_kwargs):
        # Store the tournament ID value (namespaced by tenant — ids are global).
        tenant_session_set(self._skey('tournament_filter'), self.tournament_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_stage_filter_change(self, *_args, **_kwargs):
        # Store the stage ID value (namespaced by tenant — ids are global).
        tenant_session_set(self._skey('stage_filter'), self.stage_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    async def _initial_load(self) -> None:
        """Populate the filters, then load the table exactly once.

        The view owns its own first load: callers used to kick a `refresh()` of
        their own after constructing it, which raced the filter restore (the
        table could load before the stored tournament filter was applied) and
        cost an extra query fan-out.
        """
        try:
            await self._load_tournaments()
            await self._load_stages()
        finally:
            self._initializing = False
        await self.refresh()

    def _toggle_filters(self):
        """Show/hide the filter card on mobile; CSS gates ``wiz-filters-open`` to <1024px."""
        self._filters_open = not self._filters_open
        if self._filters_open:
            self.filters_card.classes(add='wiz-filters-open')
        else:
            self.filters_card.classes(remove='wiz-filters-open')

    def _active_filter_count(self) -> int:
        """Number of the three filters set away from this board's own default.

        Compared against ``default_state_filter`` rather than the module
        constant, so a board that legitimately defaults to a different state
        set does not permanently claim its own default is a custom filter.
        """
        count = 0
        if self.tournament_filter and self.tournament_filter.value:
            count += 1
        if self.stage_filter and self.stage_filter.value:
            count += 1
        default_states = set(self.default_state_filter or DEFAULT_STATE_FILTER)
        if self.state_filter and set(self.state_filter.value or []) != default_states:
            count += 1
        if self.day_filter and self.day_filter.value not in (None, ALL_DAYS):
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
        # A scoped board offers only its own tournaments: the filter is a choice
        # within the scope, and listing the rest invites picking one that yields
        # an empty board for no visible reason.
        if self.scope_tournament_ids is not None:
            allowed = set(self.scope_tournament_ids)
            self.tournaments_list = {
                tid: name for tid, name in self.tournaments_list.items() if tid in allowed
            }
        # Set initial value from storage or default to None (All Tournaments)
        default_tournament_id = tenant_session_get(self._skey('tournament_filter'), None)
        if self.tournament_filter:
            self.tournament_filter.options = self.tournaments_list
            self.tournament_filter.value = default_tournament_id
            self.tournament_filter.update()
        self._update_filter_badge()

    async def _load_stages(self):
        """Load all stage names for the filter using service layer."""
        self.stages_list = await self.display_service.get_stages_for_filter()
        # Set initial value from storage or default to None (All Stages)
        default_stage_id = tenant_session_get(self._skey('stage_filter'), None)
        if self.stage_filter:
            self.stage_filter.options = self.stages_list
            self.stage_filter.value = default_stage_id
            self.stage_filter.update()
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
        with ui.row().classes('wiz-filter-toggle full-width items-center'):
            ui.button('Filters', icon='filter_list', on_click=self._toggle_filters).props('flat color=primary')
            self.filter_badge = ui.badge('0').props('color=primary')
            self.filter_badge.set_visibility(False)
            ui.space()
            ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary round dense').tooltip('Refresh table')

        # Filters section - professional card-based layout
        self.filters_card = ui.card().classes('match-filters-card')
        with self.filters_card:
            with ui.row().classes('match-filter-row'):
                # Day filter, first because it is the coarsest narrowing and
                # the one an operator working a venue reaches for.
                with ui.column().classes('match-filter-column'):
                    ui.label('Day').classes('match-filter-label')
                    self.day_filter = ui.select(
                        options=list(DAY_SCOPES),
                        value=tenant_session_get(self._skey('day_filter'), ALL_DAYS),
                        on_change=self._on_day_filter_change,
                    ).classes('full-width').props('outlined dense')

                # Tournament filter
                with ui.column().classes('match-filter-column'):
                    ui.label('Tournament').classes('match-filter-label')
                    self.tournament_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_tournament_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                # Stage filter
                with ui.column().classes('match-filter-column'):
                    ui.label('Stage').classes('match-filter-label')
                    self.stage_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_stage_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                # State filter
                with ui.column().classes('match-filter-column'):
                    ui.label('State').classes('match-filter-label')
                    default_states = self._stored_or_default_states()
                    self.state_filter = ui.select(
                        options=list(ALL_MATCH_STATES),
                        value=default_states,
                        multiple=True,
                        on_change=self._on_state_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                ui.space()

                # Refresh button, and a placeholder the preferences gear is
                # rendered into once the table exists (the filter strip is built
                # first, for visual order).
                with ui.column().classes('flex-center'):
                    with ui.row().classes('items-center'):
                        search_slot = ui.row().classes('items-center')
                        gear_slot = ui.row().classes('items-center')
                        ui.button(icon='refresh', on_click=self.refresh) \
                            .props('flat color=primary').tooltip('Refresh table')

        # Restore the filters, then load the table — one task, one load.
        self._bg(self._initial_load())

        with ui.column().classes('full-width') as table_container:
            self.table_container = table_container
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
            # Client-side paging over the rows already loaded. There is no
            # 'update:pagination' handler: Quasar pages over table.rows, so
            # re-querying the database on a page turn fetched data the browser
            # already held. Refresh stays an explicit button.
                pagination={'rowsPerPage': 25, 'page': 1},
            ).classes('match-table match-table-container').props(f':grid="Quasar.Screen.{self.grid_breakpoint}"')
            self.table.add_slot('no-data', no_data_slot('No matches to show yet.'))

        # Resolve current user's discord_id once for slot templates and event wiring.
        discord_id = app.storage.user.get('discord_id', None)

        # Register the column slot templates (see match_slots). The want_* flags
        # mirror the callback availability so the seed/state/stage slots
        # register exactly as before.
        register_body_slots(
            self.table,
            admin_controls=self.admin_controls,
            access=self.access,
            discord_id=discord_id,
            extra_slots=self.extra_slots,
            has_edit=self.on_edit is not None,
            want_seed_slot=self.admin_controls and self.on_generate_seed is not None,
            want_seed_readonly=self.admin_controls and self.on_generate_seed is None,
            # Every operator's board gets the state cell, including one whose
            # viewer can run nothing: it carries the chips and timestamps, and
            # the capability flags inside it decide which buttons appear.
            want_state_slot=self.admin_controls,
            want_stage_admin=self.admin_controls and self.on_set_stage is not None,
            want_stage_readonly=self.on_set_stage is None,
        )

        # Register the mobile grid slot (see match_grid).
        render_grid_slot(
            self.table, self.columns,
            admin_controls=self.admin_controls, access=self.access, discord_id=discord_id,
            has_edit=self.on_edit is not None,
            actions_first=self.actions_first,
        )

        if self.table_key:
            # **After** render_grid_slot(), never before: the card's item slot is
            # generated from these columns at build time, so applying a saved
            # layout here cannot reach it. Pinned by
            # tests/theme/test_table_preferences.py.
            self._plan = customize_table(self.table, self.columns, key=self.table_key)
            with gear_slot:
                csv_export_button(
                    'matches',
                    lambda: self._plan.columns if self._plan else self.columns,
                    lambda: self.table.rows,
                )
                preferences_button(self.table)
            if self.searchable:
                with search_slot:
                    search_input(self.table, placeholder='Search matches…')
            with self.table_container:
                row_count_label(self.table, 'matches')
            sticky_header(self.table)

        # --- Event wiring (handler bodies live in MatchTableHandlersMixin) ---
        self.table.on('acknowledge_match', lambda event: background_tasks.create(
            self._handle_acknowledge_match(event.args, context.client)))

        for role in ['player']:
            self.table.on(f'edit_{role}', lambda event, r=role: self._handle_edit_role(r, event))
        for role in ['commentator', 'tracker']:
            self.table.on(f"view_{role}", lambda event, r=role: self._handle_edit_role(r, event))
            self.table.on(f"toggle_{role}", lambda event, r=role: self._handle_toggle_approval(r, event))

        if self.on_assign_stations is not None:
            self.table.on('assign_stations', lambda event: self._bg(self._handle_assign_stations(event)))

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
            # Registered directly, exactly like toggle_watch beside it: both are
            # socket events handled inside the client's own context, where
            # ``ui.notify`` reaches the browser. ``_bg`` would rebind the tenant
            # but drop the client, so the confirmation would go nowhere.
            self.table.on('toggle_stream_volunteer', self._handle_toggle_stream_volunteer)

        # Bracket link: navigation only, so it needs no tenant rebind — and it
        # goes through ui.navigate.to precisely to pick up the tenant root_path.
        self.table.on('open_bracket', self._handle_open_bracket)

        # Admin-specific event wiring (slots registered above under the same
        # conditions). These handlers' callbacks reach scoped repository reads
        # (``require_tenant_id()``) before restoring any client context, so they
        # run through ``_bg`` to rebind the captured tenant — a socket event
        # carries neither the request contextvar nor a reachable client stash.
        if self.admin_controls:
            if self.on_generate_seed is not None:
                self.table.on('roll', lambda event: self._bg(self._handle_roll(event)))
            if (self.on_seat is not None or self.on_start is not None
                    or self.on_finish is not None or self.on_confirm is not None
                    or self.on_edit_result is not None):
                if self.on_seat is not None:
                    self.table.on('seat', lambda event: self._bg(self._handle_seat(event)))
                if self.on_start is not None:
                    self.table.on('start', lambda event: self._bg(self._handle_start(event)))
                if self.on_finish is not None:
                    self.table.on('finish', lambda event: self._bg(self._handle_finish(event)))
                if self.on_confirm is not None:
                    self.table.on('confirm', lambda event: self._bg(self._handle_confirm(event)))
                if self.on_edit_result is not None:
                    self.table.on('edit_result', lambda event: self._bg(self._handle_edit_result(event)))
            if self.on_set_stage is not None:
                self.table.on('set_stage', lambda event: self._bg(self._handle_set_stage(event)))

        if self.on_edit is not None:
            self.table.on('edit_match', lambda event: self._bg(self._handle_edit(event)))

        # Live updates: react to match changes made by other users.
        register_view(self._on_remote_change)

    async def _on_remote_change(self, match_id, change_type):
        """Apply a match change broadcast from another user's action."""
        from application.events import match_live
        if change_type == match_live.CREATED:
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
        if self.scope_tournament_ids is not None:
            # The scope wins: an empty intersection is an empty board, which is
            # the honest answer for "the tournament you picked is not yours".
            tournament_ids = (
                [t for t in tournament_ids if t in self.scope_tournament_ids]
                if tournament_ids else list(self.scope_tournament_ids)
            )
            if not tournament_ids:
                tournament_ids = _MATCHES_NOTHING

        stage_ids = None
        if self.stage_filter and self.stage_filter.value:
            stage_ids = self.stage_filter.value

        # When the active state filter shows only pre-finish states, exclude
        # finished/confirmed matches at the DB layer instead of hydrating the
        # entire (monotonically growing) match history and dropping them in
        # Python below. Confirming requires a finish, so both hidden states
        # share ``finished_at IS NOT NULL`` — exactly what ``only_upcoming``
        # filters — making this a behavior-preserving fast path for the default
        # Scheduled/Checked In/Started view (the highest-traffic schedule tab).
        state_filter = self.state_filter.value if self.state_filter else []
        if self.match_ids:
            state_filter = []
        only_upcoming = bool(state_filter) and not ({'Finished', 'Confirmed'} & set(state_filter))

        rows = await self.display_service.get_matches_for_display(
            tournament_ids=tournament_ids,
            stage_ids=stage_ids,
            only_upcoming=only_upcoming,
            user_discord_id=self.player_discord_id,
            exclude_racetime=self.exclude_racetime,
            match_ids=self.match_ids,
        )

        # Client-side filter by state (narrows within the fetched set)
        if state_filter:
            rows = [row for row in rows if row.get('state') in state_filter]

        # ...then by day. Suspended under a deep link for the reason the state
        # filter is: a link to one match must not land on an empty board.
        window = None if self.match_ids else day_scope_window(
            self.day_filter.value if self.day_filter else ALL_DAYS)
        if window:
            start, end = window
            rows = [
                row for row in rows
                if row.get('scheduled_ts') is not None
                and start <= row['scheduled_ts'] < end
            ]

        watched_ids = await self._fetch_watched_ids()
        volunteered_ids = await self._fetch_stream_volunteered_ids()
        stage_options = self._stage_options()
        for row in rows:
            row['_watching'] = row.get('id') in watched_ids
            row['_stream_volunteer'] = row.get('id') in volunteered_ids
            if stage_options is not None:
                row['stage_options'] = stage_options

        if self.row_sort is not None:
            rows = self.row_sort(rows)

        self.table.rows = rows
        self.table.update()
        self._notify_rows_changed()

    def _stage_options(self):
        """The Stage select's choices, or ``None`` for a board that cannot set one.

        Carried on every row rather than baked into the slot template: the stages
        load in a background task *after* the templates are registered, so a
        template built at registration time would offer an empty list forever.
        One shared list object per refresh, not a copy per row.

        ``No Stage`` leads, because "none" is one of the answers rather than the
        absence of one — it is what the cell shows when nothing is assigned, and
        it has to be selectable to be reversible. ``Candidate`` follows: the
        answer before a stage is decided, writing ``is_stream_candidate`` rather
        than a stage (see ``match_slots.CANDIDATE_STAGE``).
        """
        if self.on_set_stage is None:
            return None
        return [
            {'label': 'No Stage', 'value': None},
            {'label': 'Candidate', 'value': CANDIDATE_STAGE},
        ] + [
            {'label': name, 'value': stage_id}
            for stage_id, name in (self.stages_list or {}).items()
        ]

    async def focus_matches(self, match_ids) -> None:
        """Narrow the board to ``match_ids`` (or restore it with ``None``).

        The same mechanism a deep link uses, offered to a summary strip: a
        count of outstanding work is only half a queue if there is no way to
        get to it. Suspends the State filter for the same reason the deep link
        does — a pending signup on a Finished match must not vanish because the
        board's default set hides it.
        """
        self.match_ids = list(match_ids) if match_ids else None
        await self.refresh()

    def _notify_rows_changed(self) -> None:
        """Tell the caller the visible row set changed (drives a summary strip)."""
        if self.on_rows_changed is not None:
            self.on_rows_changed(self.table.rows)

    async def _fetch_watched_ids(self) -> set:
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            return set()
        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            return set()
        return set(await self.watcher_service.list_watched_match_ids(user))

    async def _fetch_stream_volunteered_ids(self) -> set:
        """Matches this viewer has offered for stream — the toggle's own state.

        Separate from the row's ``stream_volunteers`` names, which are everyone's
        and are what staff read.
        """
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            return set()
        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            return set()
        return set(await self.stream_volunteer_service.list_volunteered_match_ids(user))

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
            self._notify_rows_changed()
            return

        match_data['_watching'] = self.table.rows[idx].get('_watching', False)
        match_data['_stream_volunteer'] = self.table.rows[idx].get('_stream_volunteer', False)
        stage_options = self._stage_options()
        if stage_options is not None:
            match_data['stage_options'] = stage_options
        if flash:
            match_data['_flash'] = True
        self.table.rows[idx] = match_data
        self.table.update()
        self._notify_rows_changed()
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
