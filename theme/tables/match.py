import asyncio

from nicegui import app, background_tasks, context, ui

from application.services import MatchService, MatchWatcherService, UserService
from theme.dialog import ConfirmationDialog, UserDialog
from theme.realtime import register_view

# Pagination, sorting, and filtering can be implemented server-side if needed for large datasets.


class MatchTableView:
    """
    Encapsulates the match table UI and logic for admin/player dashboards.
    Uses MatchService for all data operations.
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
        self.show_upcoming_checkbox = None
        self.tournament_filter = None
        self.tournaments_list = []  # Will be populated in _setup_ui
        self.stream_room_filter = None
        self.stream_rooms_list = []  # Will be populated in _setup_ui
        self.state_filter = None
        self.auto_refresh_checkbox = None
        self._auto_refresh_task = None
        # Initialize services
        self.service = MatchService()
        self.user_service = UserService()
        self.watcher_service = MatchWatcherService()
        self._setup_ui()
        
    def _on_state_filter_change(self, *_args, **_kwargs):
        # Store the state filter value in app.storage
        app.storage.user['state_filter'] = self.state_filter.value
        background_tasks.create(self.refresh())
        
    def _on_tournament_filter_change(self, *_args, **_kwargs):
        # Store the tournament ID value in app.storage
        app.storage.user['tournament_filter'] = self.tournament_filter.value
        background_tasks.create(self.refresh())
        
    def _on_stream_room_filter_change(self, *_args, **_kwargs):
        # Store the stream room ID value in app.storage
        app.storage.user['stream_room_filter'] = self.stream_room_filter.value
        background_tasks.create(self.refresh())

    def _on_auto_refresh_change(self, *_args, **_kwargs):
        if self.auto_refresh_checkbox.value:
            if not self._auto_refresh_task:
                self._auto_refresh_task = background_tasks.create(self._auto_refresh_loop())
        else:
            if self._auto_refresh_task:
                self._auto_refresh_task.cancel()
                self._auto_refresh_task = None

    async def _auto_refresh_loop(self):
        try:
            while self.auto_refresh_checkbox.value:
                await self.refresh()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    async def _load_tournaments(self):
        """Load all tournament names for the filter using service layer."""
        self.tournaments_list = await self.service.get_tournaments_for_filter()
        # Set initial value from storage or default to None (All Tournaments)
        default_tournament_id = app.storage.user.get('tournament_filter', None)
        if self.tournament_filter:
            self.tournament_filter.options = self.tournaments_list
            self.tournament_filter.value = default_tournament_id
            self.tournament_filter.update()
            
    async def _load_stream_rooms(self):
        """Load all stream room names for the filter using service layer."""
        self.stream_rooms_list = await self.service.get_stream_rooms_for_filter()
        # Set initial value from storage or default to None (All Stages)
        default_stream_room_id = app.storage.user.get('stream_room_filter', None)
        if self.stream_room_filter:
            self.stream_room_filter.options = self.stream_rooms_list
            self.stream_room_filter.value = default_stream_room_id
            self.stream_room_filter.update()

    def _setup_ui(self):
        # Action button row
        if self.submit_match_callback:
            with ui.row().classes('full-width row-spacing'):
                ui.button(
                    'Create Match' if self.admin_controls else 'Request Match',
                    icon='add',
                    on_click=self.submit_match_callback
                ).props('color=primary')
        
        # Filters section - professional card-based layout
        with ui.card().classes('match-filters-card'):
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
                    default_states = app.storage.user.get('state_filter', ['Scheduled', 'Checked In', 'Started'])
                    self.state_filter = ui.select(
                        options=['Scheduled', 'Checked In', 'Started', 'Finished', 'Confirmed'],
                        value=default_states,
                        multiple=True,
                        on_change=self._on_state_filter_change
                    ).classes('full-width').props('outlined dense use-chips')
                
                # Auto-refresh checkbox (admin only)
                with ui.column().classes('flex-center'):
                    if self.admin_controls:
                        self.auto_refresh_checkbox = ui.checkbox('Auto-refresh', value=False)
                
                ui.space()
                
                # Refresh button
                with ui.column().classes('flex-center'):
                    ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary').tooltip('Refresh table')
        
        # Load filters data after UI is set up
        background_tasks.create(self._load_tournaments())
        background_tasks.create(self._load_stream_rooms())
            
        if self.auto_refresh_checkbox:
            self.auto_refresh_checkbox.on('update:model-value', self._on_auto_refresh_change)

        with ui.column().classes('full-width') as table_container:
            self.table_container = table_container
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('match-table match-table-container').props(f':grid="Quasar.Screen.{self.grid_breakpoint}"')
            self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable match id (or other key field)
        self.table.add_slot('body-cell-id', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
            <a href="#" @click="$parent.$emit('edit_match', props)" class="table-link cell-id">{{ props.value }}</a>
        </q-td>''')

        # Pass-through slots so plain columns also flash on a live update.
        self.table.add_slot('body-cell-tournament', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
            {{ props.value }}
        </q-td>''')
        self.table.add_slot('body-cell-scheduled_at', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
            <span class="cell-time">{{ props.value }}</span>
        </q-td>''')
        
        # Add the item slot for grid view
        self.render_grid_slot()
        
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Resolve current user's discord_id once for slot templates that need it.
        discord_id = app.storage.user.get('discord_id', None)
        discord_id_js = f"'{discord_id}'" if discord_id else 'null'

        async def handle_acknowledge_match(row, client):
            with client:
                discord_id = app.storage.user.get('discord_id', None)
                if not discord_id:
                    ui.notify('You must be logged in to acknowledge.', color='warning')
                    return
                user = await self.user_service.get_current_user_from_storage(discord_id)
                if not user:
                    ui.notify('User not found. Please log in again.', color='warning')
                    return
                match_id = row['id']
                try:
                    await self.service.acknowledge_match(match_id, user)
                    ui.notify(f'You acknowledged match ID {match_id}.', color='positive')
                    await self.update_row_by_id(match_id)
                except ValueError as e:
                    ui.notify(str(e), color='warning')

        self.table.on('acknowledge_match', lambda event: background_tasks.create(handle_acknowledge_match(event.args, context.client)))
        # Add slot for player names with winner indicator
        if self.admin_controls and self.can_crud:
            self.table.add_slot('body-cell-players', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div>
                        <template v-for="(player, idx) in props.value">
                            <div style="display: flex; align-items: center; gap: 4px;">
                                <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1]"
                                        name="check_circle" class="st-ok" size="xs">
                                    <q-tooltip v-if="props.row.acknowledgments[idx][3]">Acknowledged {{ props.row.acknowledgments[idx][3] }}</q-tooltip>
                                </q-icon>
                                <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                                        name="schedule" class="st-pending" size="xs">
                                    <q-tooltip>Awaiting acknowledgment</q-tooltip>
                                </q-icon>
                                <span :class="player[1] === 1 ? 'st-ok-strong' : ''">
                                    {{ player[0] }}
                                    <span v-if="player[2]" class="st-neutral italic-note"> ({{ player[2] }})</span>
                                </span>
                                <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][2]"
                                      class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                            </div>
                        </template>
                    </div>
                    <q-btn @click="$parent.$emit('assign_stations', props)"
                           icon="switch_access_shortcut" color="primary" size="xs" flat round>
                        <q-tooltip>Assign Stations</q-tooltip>
                    </q-btn>
                </div>
            </q-td>''')
        elif self.admin_controls:
            self.table.add_slot('body-cell-players', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <div>
                    <template v-for="(player, idx) in props.value">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1]"
                                    name="check_circle" class="st-ok" size="xs">
                                <q-tooltip v-if="props.row.acknowledgments[idx][3]">Acknowledged {{ props.row.acknowledgments[idx][3] }}</q-tooltip>
                            </q-icon>
                            <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                                    name="schedule" class="st-pending" size="xs">
                                <q-tooltip>Awaiting acknowledgment</q-tooltip>
                            </q-icon>
                            <span :class="player[1] === 1 ? 'st-ok-strong' : ''">
                                {{ player[0] }}
                                <span v-if="player[2]" class="st-neutral italic-note"> ({{ player[2] }})</span>
                            </span>
                            <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][2]"
                                  class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                        </div>
                    </template>
                </div>
            </q-td>''')
        else:
            self.table.add_slot('body-cell-players', f'''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <div>
                    <template v-for="(player, idx) in props.value">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1]"
                                    name="check_circle" class="st-ok" size="xs">
                                <q-tooltip v-if="props.row.acknowledgments[idx][3]">Acknowledged {{{{ props.row.acknowledgments[idx][3] }}}}</q-tooltip>
                            </q-icon>
                            <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                                    name="schedule" class="st-pending" size="xs">
                                <q-tooltip>Awaiting acknowledgment</q-tooltip>
                            </q-icon>
                            <span :class="player[1] === 1 ? 'st-ok-strong' : ''">{{{{ player[0] }}}}</span>
                            <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][2]"
                                  class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                            <q-btn v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && !props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][4] && props.row.acknowledgments[idx][4] == {discord_id_js}"
                                   icon="check" color="primary" size="xs" dense flat
                                   @click="$parent.$emit('acknowledge_match', props.row)">
                                <q-tooltip>Acknowledge</q-tooltip>
                            </q-btn>
                        </div>
                    </template>
                </div>
            </q-td>''')
        # Crew columns (commentators/trackers):
        # - Always show signup/undo for the logged-in user
        # - Names are clickable for approval ONLY when admin_controls=True
        if self.admin_controls and self.can_crud:
            for role in ['commentators', 'trackers']:
                singular = role[:-1]
                self.table.add_slot(f'body-cell-{role}', f'''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <div class="wrap">
                        <template v-for="(item, idx) in props.value">
                            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                                <q-icon v-if="item[1] && item[3]" name="check_circle" class="st-ok" size="xs">
                                    <q-tooltip v-if="item[4]">Acknowledged {{{{ item[4] }}}}</q-tooltip>
                                </q-icon>
                                <q-icon v-else-if="item[1] && !item[3]" name="schedule" class="st-pending" size="xs">
                                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                                </q-icon>
                                <a href="#" @click="$parent.$emit('edit_{singular}', {{ row: props.row, idx }})"
                                   :class="item[1] ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px; text-decoration: underline;">
                                    {{{{ item[0] }}}}
                                </a>
                            </div>
                        </template>
                    </div>
                </q-td>''')
        elif self.admin_controls:
            for role in ['commentators', 'trackers']:
                self.table.add_slot(f'body-cell-{role}', f'''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <div class="wrap">
                        <template v-for="(item, idx) in props.value">
                            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                                <q-icon v-if="item[1] && item[3]" name="check_circle" class="st-ok" size="xs">
                                    <q-tooltip v-if="item[4]">Acknowledged {{{{ item[4] }}}}</q-tooltip>
                                </q-icon>
                                <q-icon v-else-if="item[1] && !item[3]" name="schedule" class="st-pending" size="xs">
                                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                                </q-icon>
                                <span :class="item[1] ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px;">
                                    {{{{ item[0] }}}}
                                </span>
                            </div>
                        </template>
                    </div>
                </q-td>''')
        else:
            for role in ['commentators', 'trackers']:
                singular = role[:-1]
                self.table.add_slot(f'body-cell-{role}', f'''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <div class="wrap">
                        <div style="margin-bottom: 6px;">
                            <q-btn v-if="props.value && props.value.some(item => item[2] == {discord_id_js})"
                                   icon="undo" color="negative" size="sm"
                                   @click="$parent.$emit('undo_{singular}', props.row)" style="margin-right: 6px;" />
                            <q-btn v-if="props.value && !props.value.some(item => item[2] == {discord_id_js}) && !props.row.players.some(p => p[3] == {discord_id_js})"
                                   icon="assignment" color="primary" size="sm"
                                   @click="$parent.$emit('signup_{singular}', props.row)" style="margin-right: 6px;" />
                        </div>
                        <template v-for="(item, idx) in props.value">
                            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                                <q-icon v-if="item[1] && item[3]" name="check_circle" class="st-ok" size="xs">
                                    <q-tooltip v-if="item[4]">Acknowledged {{{{ item[4] }}}}</q-tooltip>
                                </q-icon>
                                <q-icon v-else-if="item[1] && !item[3]" name="schedule" class="st-pending" size="xs">
                                    <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                                </q-icon>
                                <span :class="item[1] ? 'st-ok-strong' : 'st-pending'" style="margin-right: 4px;">
                                    {{{{ item[0] }}}}
                                </span>
                                <q-btn v-if="item[1] && !item[3] && item[2] == {discord_id_js}"
                                       icon="check" color="primary" size="xs" dense flat
                                       @click="$parent.$emit('acknowledge_{singular}', {{ row: props.row, idx }})">
                                    <q-tooltip>Acknowledge</q-tooltip>
                                </q-btn>
                            </div>
                        </template>
                    </div>
                </q-td>''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Handler for editing a player

        async def handle_edit_role(role, event):
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            match_query = self.get_query()
            prefetch_map = {
                'player': ('players', 'players__user'),
                'commentator': ('commentators', 'commentators__user'),
                'tracker': ('trackers', 'trackers__user'),
            }
            attr_map = {
                'player': 'players',
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in prefetch_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
            items = getattr(m, attr_map[role], []) if m else []
            if not m or idx >= len(items):
                ui.notify(f'{role.capitalize()} not found.', color='warning')
                return

            user = items[idx].user
            with self.table_container:
                dialog = UserDialog(user)
                await dialog.open()

        async def handle_approve_role(role, event):
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            match_query = self.get_query()
            prefetch_map = {
                'player': ('players', 'players__user'),
                'commentator': ('commentators', 'commentators__user'),
                'tracker': ('trackers', 'trackers__user'),
            }
            attr_map = {
                'player': 'players',
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in prefetch_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
            items = getattr(m, attr_map[role], []) if m else []
            if not m or idx >= len(items):
                ui.notify(f'{role.capitalize()} not found.', color='warning')
                return
            from theme.dialog import ApproveCrewDialog
            crew_member = items[idx]
            with self.table_container:
                dialog = ApproveCrewDialog(crew_member, role, on_approve=lambda: self.update_row_by_id(match_id))
                await dialog.open()

        for role in ['player']:
            self.table.on(f'edit_{role}', lambda event, r=role: handle_edit_role(r, event))
        for role in ['commentator', 'tracker']:
            self.table.on(f"edit_{role}", lambda event, r=role: handle_approve_role(r, event))
        
        if self.on_assign_stations is not None:
            self.table.on('assign_stations', lambda event: background_tasks.create(self._handle_assign_stations(event)))



        async def handle_signup_or_undo_role(action, role, row):
            """Handle crew signup/undo using service layer."""
            discord_id = app.storage.user.get('discord_id', None)
            if not discord_id:
                ui.notify(f'You must be logged in to {action}.', color='warning')
                return
            
            # Get user via service layer
            user = await self.user_service.get_current_user_from_storage(discord_id)
            if not user:
                ui.notify('User not found. Please log in again.', color='warning')
                return
            
            match_id = row['id']
            
            if action == 'undo':
                async def perform_undo():
                    try:
                        await self.service.undo_crew_signup(match_id, user, role)
                        ui.notify(f'You have been removed as a {role} for match ID {match_id}.', color='positive')
                        await self.update_row_by_id(match_id)
                        dialog.dialog.close()
                    except ValueError as e:
                        ui.notify(str(e), color='warning')
                        dialog.dialog.close()
                
                dialog = ConfirmationDialog(
                    f'Are you sure you want to remove yourself as a {role} for match ID {match_id}?',
                    confirm_text='Yes',
                    cancel_text='No',
                    on_confirm=perform_undo
                )
                dialog.open()
                
            elif action == 'signup':
                async def update_role_signup():
                    try:
                        await self.service.signup_crew(match_id, user, role)
                        ui.notify(f'Successfully signed up as a {role} for match ID {match_id}. Awaiting approval.', color='positive')
                        await self.update_row_by_id(match_id)
                        dialog.dialog.close()
                    except ValueError as e:
                        ui.notify(str(e), color='warning')
                        dialog.dialog.close()
                
                dialog = ConfirmationDialog(
                    f'Do you want to sign up as a {role} for match ID {match_id}?',
                    confirm_text='Yes',
                    cancel_text='No',
                    on_confirm=update_role_signup
                )
                dialog.open()
                
        self.table.on('signup_commentator', lambda event: handle_signup_or_undo_role('signup', 'commentator', event.args))
        self.table.on('signup_tracker', lambda event: handle_signup_or_undo_role('signup', 'tracker', event.args))
        self.table.on('undo_commentator', lambda event: handle_signup_or_undo_role('undo', 'commentator', event.args))
        self.table.on('undo_tracker', lambda event: handle_signup_or_undo_role('undo', 'tracker', event.args))

        async def handle_acknowledge_crew(role, event, client):
            from application.services import CrewService
            with client:
                row = event.args['row']
                idx = event.args['idx']
                match_id = row['id']
                items = row.get(f'{role}s') or []
                if idx >= len(items) or len(items[idx]) <= 5:
                    ui.notify('Page is out of date — please refresh and try again.', color='warning')
                    return
                crew_id = items[idx][5]
                discord_id = app.storage.user.get('discord_id', None)
                if not discord_id:
                    ui.notify('You must be logged in to acknowledge.', color='warning')
                    return
                user = await self.user_service.get_current_user_from_storage(discord_id)
                if not user:
                    ui.notify('User not found. Please log in again.', color='warning')
                    return
                try:
                    await CrewService().acknowledge_crew_assignment(crew_id, role, user)
                    ui.notify(f'You acknowledged your {role} assignment for match ID {match_id}.', color='positive')
                    await self.update_row_by_id(match_id)
                except ValueError as e:
                    ui.notify(str(e), color='warning')

        self.table.on('acknowledge_commentator', lambda event: background_tasks.create(handle_acknowledge_crew('commentator', event, context.client)))
        self.table.on('acknowledge_tracker', lambda event: background_tasks.create(handle_acknowledge_crew('tracker', event, context.client)))

        if discord_id:
            self.table.add_slot('body-cell-watch', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <q-btn :icon="props.row._watching ? 'visibility' : 'visibility_off'"
                       :color="props.row._watching ? 'primary' : 'grey'"
                       size="sm" flat round
                       @click="$parent.$emit('toggle_watch', props.row)">
                    <q-tooltip>{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}</q-tooltip>
                </q-btn>
            </q-td>''')
            self.table.on('toggle_watch', self._handle_toggle_watch)

        # Admin-specific slots and handlers
        if self.admin_controls:
            if self.on_generate_seed is not None:
                self.table.add_slot('body-cell-generated_seed', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <q-btn v-if="props.row.tournament_seed_generator && !props.value"
                           :loading="props.row._generating_seed"
                           :disabled="props.row._generating_seed"
                           @click="(props.row._generating_seed = true, $parent.$emit('roll', props))"
                           icon="casino" color="primary" size="sm">
                        Generate
                    </q-btn>
                    <span v-if="props.value">
                        <template v-if="/^https?:\\/\\//.test(props.value)">
                            <a :href="props.value" target="_blank" style="color: var(--sgl-link); text-decoration: underline;" :title="props.value">
                                {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
                            </a>
                        </template>
                        <template v-else>{{ props.value }}</template>
                    </span>
                </q-td>''')
                self.table.on('roll', lambda event: background_tasks.create(self._handle_roll(event)))

            # State column with context-aware actions
            if self.on_seat is not None or self.on_start is not None or self.on_finish is not None or self.on_confirm is not None:
                self.table.add_slot('body-cell-state', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <!-- Scheduled state: show Check In button -->
                    <q-btn v-if="props.value === 'Scheduled'" @click="$parent.$emit('seat', props)"
                           icon="chair" color="primary" size="sm">
                        Check In
                    </q-btn>
                    
                    <!-- Checked In: show Start button and timestamp -->
                    <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                        <q-btn @click="$parent.$emit('start', props)"
                               icon="play_arrow" color="primary" size="sm">
                            Start
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="check" class="st-neutral" size="xs" />
                            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                        </div>
                    </div>
                    
                    <!-- Started: show Finish button and timestamp -->
                    <div v-else-if="props.value === 'Started'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                        <q-btn @click="$parent.$emit('finish', props)"
                               icon="sports_score" color="primary" size="sm">
                            Finish
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="play_arrow" class="st-live" size="xs" />
                            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                        </div>
                    </div>
                    
                    <!-- Finished: show Confirm button and timestamp -->
                    <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                        <q-btn @click="$parent.$emit('confirm', props)"
                               icon="check_circle" color="primary" size="sm">
                            Confirm
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="flag" class="st-pending" size="xs" />
                            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                        </div>
                    </div>
                    
                    <!-- Confirmed: show state with icon and timestamp -->
                    <div v-else-if="props.value === 'Confirmed'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="verified" class="st-ok" size="sm" />
                            <span style="font-weight: 500;">{{ props.value }}</span>
                        </div>
                        <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                    </div>
                    
                    <!-- Fallback -->
                    <span v-else>{{ props.value }}</span>
                </q-td>''')
                
                if self.on_seat is not None:
                    self.table.on('seat', lambda event: background_tasks.create(self._handle_seat(event)))
                if self.on_start is not None:
                    self.table.on('start', lambda event: background_tasks.create(self._handle_start(event)))
                if self.on_finish is not None:
                    self.table.on('finish', lambda event: background_tasks.create(self._handle_finish(event)))
                if self.on_confirm is not None:
                    self.table.on('confirm', lambda event: background_tasks.create(self._handle_confirm(event)))

            if self.on_edit_stream_room is not None:
                self.table.add_slot('body-cell-stream_room', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                    <q-btn v-if="!props.value && !props.row.is_stream_candidate" @click="$parent.$emit('edit-stream-room', props)"
                           icon="movie" color="primary" size="sm">
                        Assign
                    </q-btn>
                    <template v-else>
                        <a v-if="props.value && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{ props.value }}</a>
                        <span v-else-if="props.value">{{ props.value }}</span>
                        <span v-if="props.row.is_stream_candidate && !props.value" class="sgl-chip sgl-chip--candidate q-ml-xs">candidate</span>
                        <q-btn v-if="!props.value && props.row.is_stream_candidate" @click="$parent.$emit('edit-stream-room', props)"
                               icon="movie" color="primary" size="sm" class="q-ml-xs">
                            Assign
                        </q-btn>
                    </template>
                </q-td>''')
                self.table.on('edit-stream-room', lambda event: background_tasks.create(self._handle_edit_stream_room(event)))

        if self.on_edit is not None:
            self.table.on('edit_match', lambda event: background_tasks.create(self._handle_edit(event)))

        if self.on_edit_stream_room is None:
            self.table.add_slot('body-cell-stream_room', '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <a v-if="props.value && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{ props.value }}</a>
                <span v-else-if="props.value">{{ props.value }}</span>
                <span v-else>-</span>
            </q-td>''')

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

        # Use service to get formatted match data (all states)
        rows = await self.service.get_matches_for_display(
            tournament_ids=tournament_ids,
            stream_room_ids=stream_room_ids,
            only_upcoming=False,  # Get all matches
            user_discord_id=self.player_discord_id
        )

        # Client-side filter by state
        state_filter = self.state_filter.value if self.state_filter else []
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

    def render_grid_slot(self):
        # Get the discord_id from app.storage if available
        discord_id = app.storage.user.get('discord_id', None)
        
        # Dynamically generate grid slot fields from self.columns
        grid_fields = []
        for col in self.columns:
            if col.get('hidden'):  # Skip hidden columns
                continue
                
            field = {
                'label': col.get('label', col.get('name', '')),
                'key': col.get('name', ''),
                'discord_id': f"'{discord_id}'" if discord_id else 'null'  # Format for JS template
            }
            
            # Special handling for different field types
            if field['key'] == 'id':
                field['event'] = 'edit_match'
            elif field['key'] == 'players':
                field['array'] = True
                field['separator'] = ', '  # Add space after comma
            elif field['key'] in ['commentators', 'trackers']:
                field['array_objects'] = True
                field['name_index'] = 0
                field['approved_index'] = 1
                field['ack_index'] = 3
                field['ack_ts_index'] = 4
                field['discord_index'] = 2
                field['separator'] = ', '  # Add space after comma
            elif field['key'] == 'acknowledgments':
                field['ack_field'] = True
            elif field['key'] == 'state':
                field['state_field'] = True
            elif field['key'] == 'watch':
                field['watch_field'] = True

            grid_fields.append(field)

        # Build JS array for Vue template
        js_field_array = ',\n    '.join([
            f"{{ label: '{f['label']}', key: '{f['key']}'" +
            (f", event: '{f['event']}'" if 'event' in f else '') +
            (", array: true" if f.get('array') else '') +
            (", arrayObjects: true" if f.get('array_objects') else '') +
            (", nameIndex: " + str(f['name_index']) if 'name_index' in f else '') +
            (", approvedIndex: " + str(f['approved_index']) if 'approved_index' in f else '') +
            (", ackIndex: " + str(f['ack_index']) if 'ack_index' in f else '') +
            (", ackTsIndex: " + str(f['ack_ts_index']) if 'ack_ts_index' in f else '') +
            (", discordIndex: " + str(f['discord_index']) if 'discord_index' in f else '') +
            (", ackField: true" if f.get('ack_field') else '') +
            (", stateField: true" if f.get('state_field') else '') +
            (", watchField: true" if f.get('watch_field') else '') +
            (f", separator: '{f['separator']}'" if 'separator' in f else '') +
            (f", discord_id: {f['discord_id']}" if 'discord_id' in f else '') +
            " }" for f in grid_fields
        ])
        
        self.table.add_slot('item', f'''
    <div class="q-pa-md q-mb-sm match-grid-card" :class="props.row._flash ? 'sgl-row-flash' : ''" style="width: 100%; box-sizing: border-box; border: 1px solid #eee; border-radius: 8px; background: #fff;">
        <div v-for="field in [
            {js_field_array}
        ]" :key="field.key" class="row items-center q-mb-xs">
            <div class="col-4 text-grey-7">{{{{ field.label }}}}:</div>
            <div class="col-8">
                <!-- For fields with click events like match ID -->
                <template v-if="field.event">
                    <a href="#" @click="$parent.$emit(field.event, {{ row: props.row }})" style="color: var(--sgl-link); text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
                </template>

                <!-- For array fields like players -->
                <template v-else-if="field.array">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div v-if="field.key === 'players'">
                            <template v-for="(player, idx) in props.row[field.key]">
                                <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1]"
                                            name="check_circle" class="st-ok" size="xs">
                                        <q-tooltip v-if="props.row.acknowledgments[idx][3]">Acknowledged {{{{ props.row.acknowledgments[idx][3] }}}}</q-tooltip>
                                    </q-icon>
                                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                                            name="schedule" class="st-pending" size="xs">
                                        <q-tooltip>Awaiting acknowledgment</q-tooltip>
                                    </q-icon>
                                    <span :class="player[1] === 1 ? 'st-ok-strong' : ''">
                                        {{{{ player[0] }}}}
                                        <span v-if="{'true' if self.admin_controls else 'false'} && player[2]" class="st-neutral italic-note"> ({{{{ player[2] }}}})</span>
                                    </span>
                                    <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][2]"
                                          class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                                    <q-btn v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && !props.row.acknowledgments[idx][1] && props.row.acknowledgments[idx][4] && props.row.acknowledgments[idx][4] == field.discord_id"
                                           icon="check" color="primary" size="xs" dense flat
                                           @click="$parent.$emit('acknowledge_match', props.row)">
                                        <q-tooltip>Acknowledge</q-tooltip>
                                    </q-btn>
                                </div>
                            </template>
                        </div>
                        <span v-else>{{{{ Array.isArray(props.row[field.key]) ? props.row[field.key].join(field.separator || ', ') : props.row[field.key] }}}}</span>
                        <q-btn v-if="{'true' if (self.admin_controls and self.can_crud) else 'false'} && field.key === 'players'"
                               @click="$parent.$emit('assign_stations', {{ row: props.row }})"
                               icon="switch_access_shortcut" color="primary" size="xs" flat round>
                            <q-tooltip>Assign Stations</q-tooltip>
                        </q-btn>
                    </div>
                </template>

                <!-- For array of objects like commentators/trackers with approval status -->
                <template v-else-if="field.arrayObjects">
                    <span>
                        <!-- Add signup/undo buttons for commentator/tracker fields (non-admin only) -->
                        <template v-if="(field.key === 'commentators' || field.key === 'trackers') && !{'true' if self.admin_controls else 'false'}">
                            <div style="margin-bottom: 8px;">
                                <q-btn v-if="props.row[field.key] && props.row[field.key].some(item => item[2] == field.discord_id)"
                                       icon="undo" color="negative" size="sm"
                                       @click="$parent.$emit('undo_' + field.key.slice(0, -1), props.row)"
                                       style="margin-right: 8px;">
                                    Undo
                                </q-btn>
                                <q-btn v-if="props.row[field.key] && !props.row[field.key].some(item => item[2] == field.discord_id) && !props.row.players.some(p => p[3] == field.discord_id)"
                                       icon="assignment" color="primary" size="sm"
                                       @click="$parent.$emit('signup_' + field.key.slice(0, -1), props.row)"
                                       style="margin-right: 8px;">
                                    Sign Up
                                </q-btn>
                            </div>
                        </template>

                        <template v-if="Array.isArray(props.row[field.key])">
                            <template v-for="(item, idx) in props.row[field.key]">
                                <span style="display: inline-flex; align-items: center; gap: 2px;">
                                    <q-icon v-if="(field.key === 'commentators' || field.key === 'trackers') && item[field.approvedIndex] && item[field.ackIndex]"
                                            name="check_circle" class="st-ok" size="xs">
                                        <q-tooltip v-if="item[field.ackTsIndex]">Acknowledged {{{{ item[field.ackTsIndex] }}}}</q-tooltip>
                                    </q-icon>
                                    <q-icon v-else-if="(field.key === 'commentators' || field.key === 'trackers') && item[field.approvedIndex] && !item[field.ackIndex]"
                                            name="schedule" class="st-pending" size="xs">
                                        <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                                    </q-icon>
                                    <template v-if="(field.key === 'commentators' || field.key === 'trackers') && {'true' if (self.admin_controls and self.can_crud) else 'false'}">
                                        <a href="#" @click="$parent.$emit('edit_' + field.key.slice(0, -1), {{ row: props.row, idx }})"
                                           :class="item[field.approvedIndex] ? 'st-ok-strong' : 'st-pending'" style="text-decoration: underline;">
                                            {{{{ item[field.nameIndex] }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                        </a>
                                    </template>
                                    <template v-else>
                                        <span :class="item[field.approvedIndex] ? 'st-ok-strong' : 'st-pending'">
                                            {{{{ item[field.nameIndex] }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                        </span>
                                    </template>
                                    <q-btn v-if="(field.key === 'commentators' || field.key === 'trackers') && !{'true' if self.admin_controls else 'false'} && item[field.approvedIndex] && !item[field.ackIndex] && item[field.discordIndex] == field.discord_id"
                                           icon="check" color="primary" size="xs" dense flat
                                           @click="$parent.$emit('acknowledge_' + field.key.slice(0, -1), {{ row: props.row, idx }})">
                                        <q-tooltip>Acknowledge</q-tooltip>
                                    </q-btn>
                                </span>
                            </template>
                        </template>
                        <template v-else>{{{{ props.row[field.key] }}}}</template>
                    </span>
                </template>

                <!-- For state field with admin buttons -->
                <template v-else-if="field.stateField">
                    <!-- Scheduled state: show Check In button -->
                    <q-btn v-if="{'true' if self.admin_controls else 'false'} && props.row[field.key] === 'Scheduled'"
                           @click="$parent.$emit('seat', {{ key: props.row.id }})"
                           icon="chair" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Check In
                    </q-btn>
                    
                    <!-- Checked In: show Start button and timestamp -->
                    <div v-else-if="{'true' if self.admin_controls else 'false'} && props.row[field.key] === 'Checked In'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('start', {{ key: props.row.id }})"
                               icon="play_arrow" color="primary" size="sm">
                            Start
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="check" class="st-neutral" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>
                    
                    <!-- Started: show Finish button and timestamp -->
                    <div v-else-if="{'true' if self.admin_controls else 'false'} && props.row[field.key] === 'Started'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('finish', {{ key: props.row.id }})"
                               icon="sports_score" color="primary" size="sm">
                            Finish
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="play_arrow" class="st-live" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>
                    
                    <!-- Finished: show Confirm button and timestamp -->
                    <div v-else-if="{'true' if self.admin_controls else 'false'} && props.row[field.key] === 'Finished'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('confirm', {{ key: props.row.id }})"
                               icon="check_circle" color="primary" size="sm">
                            Confirm
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="flag" class="st-pending" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>
                    
                    <!-- Confirmed: show state with icon and timestamp -->
                    <div v-else-if="props.row[field.key] === 'Confirmed'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="verified" class="st-ok" size="sm" />
                            <span style="font-weight: 500;">{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    
                    <!-- Non-admin views: show state with icon and timestamp -->
                    <div v-else-if="props.row[field.key] === 'Finished'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="flag" class="st-pending" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    <div v-else-if="props.row[field.key] === 'Started'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="play_arrow" class="st-live" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    <div v-else-if="props.row[field.key] === 'Checked In'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="check" class="st-neutral" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    
                    <!-- Fallback for Scheduled or other states -->
                    <div v-else style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="schedule" class="st-neutral" size="sm" />
                            <span>{{{{ props.row[field.key] || 'Scheduled' }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                </template>

                <!-- For generated_seed field, truncate long URLs -->
                <template v-else-if="field.key === 'generated_seed'">
                    <!-- Show generate button if admin, has seed generator, and no seed yet -->
                    <q-btn v-if="{'true' if self.admin_controls else 'false'} && props.row.tournament_seed_generator && !props.row[field.key]"
                           :loading="props.row._generating_seed"
                           :disabled="props.row._generating_seed"
                           @click="(props.row._generating_seed = true, $parent.$emit('roll', {{ key: props.row.id }}))"
                           icon="casino" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Generate Seed
                    </q-btn>
                    <template v-if="props.row[field.key]">
                        <a v-if="props.row[field.key].startsWith('https://') || props.row[field.key].startsWith('http://')"
                           :href="props.row[field.key]" target="_blank" style="color: var(--sgl-link); text-decoration: underline;">
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </a>
                        <span v-else>
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </span>
                    </template>
                    <template v-else-if="!{'true' if self.admin_controls else 'false'} || !props.row.tournament_seed_generator">-</template>
                </template>

                <!-- Acknowledgments field: icon + name per player -->
                <template v-else-if="field.ackField">
                    <template v-if="Array.isArray(props.row[field.key])">
                        <div v-for="(item, idx) in props.row[field.key]" :key="idx"
                             style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                            <q-icon :name="item[1] ? 'check_circle' : 'schedule'"
                                    :class="item[1] ? 'st-ok' : 'st-pending'" size="xs" />
                            <span :class="item[1] ? 'st-ok-strong' : 'st-pending'">
                                {{{{ item[0] }}}}<span v-if="item[1] && item[2]" style="font-style: italic; font-weight: normal;"> (auto)</span>
                            </span>
                        </div>
                    </template>
                    <template v-else>—</template>
                </template>

                <!-- Watch toggle (logged-in users only) -->
                <template v-else-if="field.watchField">
                    <q-btn :icon="props.row._watching ? 'visibility' : 'visibility_off'"
                           :color="props.row._watching ? 'primary' : 'grey'"
                           size="sm" flat round
                           @click="$parent.$emit('toggle_watch', props.row)">
                        <q-tooltip>{{{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}}}</q-tooltip>
                    </q-btn>
                </template>

                <!-- For stream_room field with admin button -->
                <template v-else-if="field.key === 'stream_room'">
                    <a v-if="props.row[field.key] && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
                    <span v-else-if="props.row[field.key]">{{{{ props.row[field.key] }}}}</span>
                    <span v-if="props.row.is_stream_candidate && !props.row[field.key]" class="sgl-chip sgl-chip--candidate q-ml-xs">candidate</span>
                    <q-btn v-if="{'true' if (self.admin_controls and self.can_crud) else 'false'} && !props.row[field.key]"
                           @click="$parent.$emit('edit-stream-room', {{ key: props.row.id }})"
                           icon="movie" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Assign Stage
                    </q-btn>
                    <template v-if="!props.row[field.key] && !props.row.is_stream_candidate && !{'true' if (self.admin_controls and self.can_crud) else 'false'}">-</template>
                </template>

                <!-- Default rendering for other fields -->
                <template v-else>
                    {{{{ props.row[field.key] || '' }}}}
                </template>
            </div>
        </div>
        </div>
        ''')

    def _on_page_change(self, *_):
        background_tasks.create(self.refresh())

    # Helper to extract match id from emitted events
    def _event_match_id(self, event):
        if hasattr(event, 'args'):
            args = event.args
            if isinstance(args, dict):
                if 'key' in args:
                    return args['key']
                if 'row' in args and isinstance(args['row'], dict) and 'id' in args['row']:
                    return args['row']['id']
        return None

    async def _handle_edit(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit:
            await self.on_edit(match_id)

    async def _handle_roll(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_generate_seed:
            await self.on_generate_seed(match_id)

    async def _handle_seat(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_seat:
            await self.on_seat(match_id)

    async def _handle_start(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_start:
            await self.on_start(match_id)

    async def _handle_finish(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_finish:
            await self.on_finish(match_id)

    async def _handle_confirm(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_confirm:
            await self.on_confirm(match_id)

    async def _handle_assign_stations(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_assign_stations:
            await self.on_assign_stations(match_id)

    async def _handle_edit_stream_room(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit_stream_room:
            await self.on_edit_stream_room(match_id)

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
        match_data = await self.service.get_match_for_display(match_id)

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

    async def _handle_toggle_watch(self, event):
        row = event.args if isinstance(event.args, dict) else {}
        match_id = row.get('id')
        if match_id is None:
            return

        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.notify('You must be logged in to watch a match.', color='warning')
            return

        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            ui.notify('User not found. Please log in again.', color='warning')
            return

        currently_watching = bool(row.get('_watching'))
        try:
            if currently_watching:
                await self.watcher_service.unwatch(match_id, user)
                ui.notify(f'No longer watching match ID {match_id}.', color='positive')
            else:
                await self.watcher_service.watch(match_id, user)
                ui.notify(f'Now watching match ID {match_id}. You will receive Discord DMs on updates.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
            return

        idx = next((i for i, r in enumerate(self.table.rows) if r.get('id') == match_id), None)
        if idx is not None:
            self.table.rows[idx]['_watching'] = not currently_watching
            self.table.update()

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
