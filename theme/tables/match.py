import asyncio

from nicegui import app, ui

from models import Commentator, StreamRoom, Tracker, Tournament, User
from theme.dialog import ConfirmationDialog, UserDialog

# Pagination, sorting, and filtering can be implemented server-side if needed for large datasets.


class MatchTableView:
    def _build_row(self, m):
        """
        Build a row dict for a match object.
        """
        player_names = [p.user.preferred_name for p in m.players]
        commentator_names = [(c.user.preferred_name, c.approved, c.user.discord_id) for c in m.commentators]
        tracker_names = [(t.user.preferred_name, t.approved, t.user.discord_id) for t in m.trackers]
        row = {
            'id': m.id,
            'tournament': m.tournament.name if m.tournament else '',
            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
            'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else '',
            'finished': m.finished_at.strftime('%Y-%m-%d %H:%M') if m.finished_at else '',
            'players': player_names,
            'stream_room': m.stream_room.name if m.stream_room else '',
            'seed': m.generated_seed.seed_url if m.generated_seed else '',
            'generated_seed': m.generated_seed.seed_url if m.generated_seed else '',
            'tournament_seed_generator': m.tournament.seed_generator if m.tournament else None,
            'commentators': commentator_names,
            'trackers': tracker_names,
        }
        if self.admin_controls:
            row['actions'] = ''
        return row
    # Encapsulates the match table UI and logic for admin/player dashboards.

    def __init__(self, columns, get_query, admin_controls=False, extra_slots=None, submit_match_callback=None,
                 on_edit=None, on_generate_seed=None, on_seat=None, on_finish=None, on_edit_stream_room=None):
        self.columns = columns
        self.get_query = get_query
        self.admin_controls = admin_controls
        self.extra_slots = extra_slots
        self.submit_match_callback = submit_match_callback
        # Optional callbacks for admin actions
        self.on_edit = on_edit
        self.on_generate_seed = on_generate_seed
        self.on_seat = on_seat
        self.on_finish = on_finish
        self.on_edit_stream_room = on_edit_stream_room
        self.table = None
        self.show_upcoming_checkbox = None
        self.tournament_filter = None
        self.tournaments_list = []  # Will be populated in _setup_ui
        self.stream_room_filter = None
        self.stream_rooms_list = []  # Will be populated in _setup_ui
        self.auto_refresh_checkbox = None
        self._auto_refresh_task = None
        self._setup_ui()

    def _on_upcoming_change(self, *_args, **_kwargs):
        app.storage.user['show_only_upcoming_matches'] = self.show_upcoming_checkbox.value
        asyncio.create_task(self.refresh())
        
    def _on_tournament_filter_change(self, *_args, **_kwargs):
        # Store the tournament ID value in app.storage
        app.storage.user['tournament_filter'] = self.tournament_filter.value
        asyncio.create_task(self.refresh())
        
    def _on_stream_room_filter_change(self, *_args, **_kwargs):
        # Store the stream room ID value in app.storage
        app.storage.user['stream_room_filter'] = self.stream_room_filter.value
        asyncio.create_task(self.refresh())

    def _on_auto_refresh_change(self, *_args, **_kwargs):
        if self.auto_refresh_checkbox.value:
            if not self._auto_refresh_task:
                self._auto_refresh_task = asyncio.create_task(self._auto_refresh_loop())
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
        """Load all tournament names for the filter"""
        tournaments = await Tournament.all()
        self.tournaments_list = {t.id: t.name for t in tournaments}
        # Set initial value from storage or default to None (All Tournaments)
        default_tournament_id = app.storage.user.get('tournament_filter', None)
        if self.tournament_filter:
            self.tournament_filter.options = self.tournaments_list
            self.tournament_filter.value = default_tournament_id
            self.tournament_filter.update()
            
    async def _load_stream_rooms(self):
        """Load all stream room names for the filter"""
        stream_rooms = await StreamRoom.all()
        self.stream_rooms_list = {sr.id: sr.name for sr in stream_rooms}
        # Set initial value from storage or default to None (All Stages)
        default_stream_room_id = app.storage.user.get('stream_room_filter', None)
        if self.stream_room_filter:
            self.stream_room_filter.options = self.stream_rooms_list
            self.stream_room_filter.value = default_stream_room_id
            self.stream_room_filter.update()

    def _setup_ui(self):
        # Action button row
        if self.submit_match_callback:
            with ui.row().style('width: 100%; margin-bottom: 1em;'):
                ui.button(
                    'Create Match' if self.admin_controls else 'Request Match',
                    icon='add',
                    on_click=self.submit_match_callback
                ).props('color=primary')
        
        # Filters section - professional card-based layout
        with ui.card().style('width: 100%; padding: 1em; margin-bottom: 1em; background-color: #f5f5f5;'):
            with ui.row().style('width: 100%; align-items: center; gap: 1em; flex-wrap: wrap;'):
                # Tournament filter
                with ui.column().style('min-width: 200px;'):
                    ui.label('Tournament').style('font-size: 0.85em; font-weight: 500; color: #666; margin-bottom: 0.3em;')
                    self.tournament_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_tournament_filter_change
                    ).style('width: 100%;').props('outlined dense use-chips')
                
                # Stream room filter
                with ui.column().style('min-width: 180px;'):
                    ui.label('Stage').style('font-size: 0.85em; font-weight: 500; color: #666; margin-bottom: 0.3em;')
                    self.stream_room_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_stream_room_filter_change
                    ).style('width: 100%;').props('outlined dense use-chips')
                
                # Checkbox filters
                with ui.column().style('justify-content: center;'):
                    default_value = app.storage.user.get('show_only_upcoming_matches', True)
                    self.show_upcoming_checkbox = ui.checkbox(
                        'Hide Finished Matches',
                        value=default_value,
                        on_change=self._on_upcoming_change
                    )
                    
                    if self.admin_controls:
                        self.auto_refresh_checkbox = ui.checkbox('Auto-refresh', value=False)
                
                ui.space()
                
                # Refresh button
                with ui.column().style('justify-content: center;'):
                    ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary').tooltip('Refresh table')
        
        # Load filters data after UI is set up
        asyncio.create_task(self._load_tournaments())
        asyncio.create_task(self._load_stream_rooms())
            
        if self.auto_refresh_checkbox:
            self.auto_refresh_checkbox.on('update:model-value', self._on_auto_refresh_change)

        ui.add_head_html("""
        <style>
        .match-table th, .match-table td {
            border-right: 1px solid #ccc;
        }
        .match-table td {
            text-align: left;
        }
        /* Allow wrapping for long lists of names in table view for specific columns */
        /* Target the inner wrapper element placed inside the q-td, not the td itself */
        .match-table td .wrap {
            display: block;
            white-space: normal !important;
            word-break: normal;
            overflow-wrap: break-word;
            max-width: 120px; /* reasonable default, table can expand as needed */
        }
        /* Ensure links inside the wrapper also wrap */
        .match-table td .wrap a {
            white-space: normal !important;
            word-break: normal;
            overflow-wrap: break-word;
        }
        .match-table th {
            text-align: center;
        }
        .match-table th:last-child, .match-table td:last-child {
            border-right: none;
        }
        .match-table {
            border-collapse: collapse;
        }
        .match-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .match-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        </style>
        """)
        with ui.column().style('width: 100%;') as table_container:
            self.table_container = table_container
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('match-table').style('margin-top: 1em; width: 100%;').props(':grid="Quasar.Screen.lt.md"')
            self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable match id (or other key field)
        self.table.add_slot('body-cell-id', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_match', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        
        # Add the item slot for grid view
        self.render_grid_slot()
        
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Add slot for clickable player names
        if self.admin_controls:
            self.table.add_slot('body-cell-players', '''<q-td :props="props">
                <div>
                    <template v-for="(name, idx) in props.value">
                        <a href="#" @click="$parent.$emit('edit_player', { row: props.row, idx })" style="color: #1976d2; text-decoration: underline; margin-right: 4px;">{{ name }}</a><br/>
                    </template>
                </div>
            </q-td>''')
        else:
            self.table.add_slot('body-cell-players', '''<q-td :props="props">
                <div>
                    <template v-for="(name, idx) in props.value">
                        <span style="margin-right: 4px; text-decoration: underline;">{{ name }}</span><br/>
                    </template>
                </div>
            </q-td>''')
        # Crew columns (commentators/trackers):
        # - Always show signup/undo for the logged-in user
        # - Names are clickable for approval ONLY when admin_controls=True
        discord_id = app.storage.user.get('discord_id', None)
        discord_id_js = f"'{discord_id}'" if discord_id else 'null'
        if self.admin_controls:
            for role in ['commentators', 'trackers']:
                singular = role[:-1]
                self.table.add_slot(f'body-cell-{role}', f'''<q-td :props="props">
                    <div class="wrap">
                        <div style="margin-bottom: 6px;">
                            <q-btn v-if="props.value && props.value.some(item => item[2] == {discord_id_js})"
                                   icon="undo" color="negative" size="sm"
                                   @click="$parent.$emit('undo_{singular}', props.row)" style="margin-right: 6px;" />
                            <q-btn v-if="props.value && !props.value.some(item => item[2] == {discord_id_js})"
                                   icon="assignment" color="primary" size="sm"
                                   @click="$parent.$emit('signup_{singular}', props.row)" style="margin-right: 6px;" />
                        </div>
                        <template v-for="(item, idx) in props.value">
                            <a href="#" @click="$parent.$emit('edit_{singular}', {{ row: props.row, idx }})"
                               :style="'color: ' + (item[1] ? '#4CAF50' : '#FF9800') + '; margin-right: 4px; font-weight:' + (item[1] ? 'bold' : 'normal') + '; text-decoration: underline;'">
                                {{{{ item[0] }}}}
                            </a><br/>
                        </template>
                    </div>
                </q-td>''')
        else:
            for role in ['commentators', 'trackers']:
                singular = role[:-1]
                self.table.add_slot(f'body-cell-{role}', f'''<q-td :props="props">
                    <div class="wrap">
                        <div style="margin-bottom: 6px;">
                            <q-btn v-if="props.value && props.value.some(item => item[2] == {discord_id_js})"
                                   icon="undo" color="negative" size="sm"
                                   @click="$parent.$emit('undo_{singular}', props.row)" style="margin-right: 6px;" />
                            <q-btn v-if="props.value && !props.value.some(item => item[2] == {discord_id_js})"
                                   icon="assignment" color="primary" size="sm"
                                   @click="$parent.$emit('signup_{singular}', props.row)" style="margin-right: 6px;" />
                        </div>
                        <template v-for="(item, idx) in props.value">
                            <span :style="'color: ' + (item[1] ? '#4CAF50' : '#FF9800') + '; margin-right: 4px; font-weight:' + (item[1] ? 'bold' : 'normal')">
                                {{{{ item[0] }}}}
                            </span><br/>
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



        async def handle_signup_or_undo_role(action, role, row):
            # action: 'signup' or 'undo', role: 'commentator' or 'tracker'

            discord_id = app.storage.user.get('discord_id', None)
            if not discord_id:
                ui.notify(f'You must be logged in to {action}.', color='warning')
                return
            user = await User.get(discord_id=discord_id)
            match_query = self.get_query()
            match = await match_query.filter(id=row['id']).first().prefetch_related('tournament', role + 's', role + 's__user')
            if not match:
                ui.notify('Match not found.', color='warning')
                return
            attr_map = {
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in attr_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            crew_list = getattr(match, attr_map[role], [])
            if action == 'undo':
                crew_member = next((c for c in crew_list if c.user_id == user.id), None)
                if not crew_member:
                    ui.notify(f'You are not signed up as a {role} for this match.', color='info')
                    return
                    
                async def perform_undo():
                    await crew_member.delete()
                    ui.notify(f'You have been removed as a {role} for match ID {match.id}.', color='positive')
                    await self.update_row_by_id(match.id)
                    dialog.dialog.close()
                
                dialog = ConfirmationDialog(f'Are you sure you want to remove yourself as a {role} for match ID {match.id}?', confirm_text='Yes', cancel_text='No', on_confirm=perform_undo)
                dialog.open()
            elif action == 'signup':
                async def update_role_signup():
                    if any(c.user_id == user.id for c in crew_list):
                        ui.notify(f'You are already signed up as a {role} for this match.', color='info')
                        return
                    model_map = {
                        'commentator': Commentator,
                        'tracker': Tracker,
                    }
                    new_crew = model_map.get(role)(match=match, user=user, approved=False)
                    await new_crew.save()
                    ui.notify(f'Successfully signed up as a {role} for match ID {match.id}. Awaiting approval.', color='positive')
                    await self.update_row_by_id(match.id)
                    dialog.dialog.close()
                dialog = ConfirmationDialog(f'Do you want to sign up as a {role} for match ID {match.id}?', confirm_text='Yes', cancel_text='No', on_confirm=update_role_signup)
                dialog.open()
        self.table.on('signup_commentator', lambda event: handle_signup_or_undo_role('signup', 'commentator', event.args))
        self.table.on('signup_tracker', lambda event: handle_signup_or_undo_role('signup', 'tracker', event.args))
        self.table.on('undo_commentator', lambda event: handle_signup_or_undo_role('undo', 'commentator', event.args))
        self.table.on('undo_tracker', lambda event: handle_signup_or_undo_role('undo', 'tracker', event.args))

        # Admin-specific slots and handlers
        if self.admin_controls:
            if self.on_generate_seed is not None:
                self.table.add_slot('body-cell-generated_seed', '''<q-td :props="props">
                    <q-btn v-if="props.row.tournament_seed_generator && !props.value"
                           :loading="props.row._generating_seed"
                           :disabled="props.row._generating_seed"
                           @click="(props.row._generating_seed = true, $parent.$emit('roll', props))"
                           icon="casino" flat />
                    <span v-if="props.value">
                        <template v-if="/^https?:\\/\\//.test(props.value)">
                            <a :href="props.value" target="_blank" style="color: #1976d2; text-decoration: underline;" :title="props.value">
                                {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
                            </a>
                        </template>
                        <template v-else>{{ props.value }}</template>
                    </span>
                </q-td>''')
                self.table.on('roll', lambda event: asyncio.create_task(self._handle_roll(event)))

            if self.on_seat is not None:
                self.table.add_slot('body-cell-seated', '''<q-td :props="props">
                    <q-btn v-if="!props.value" @click="$parent.$emit('seat', props)" icon="chair" flat />
                    <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%;">
                        <q-icon name="check" color="green" size="md" />
                    </div>
                </q-td>''')
                self.table.on('seat', lambda event: asyncio.create_task(self._handle_seat(event)))

            if self.on_finish is not None:
                self.table.add_slot('body-cell-finished', '''<q-td :props="props">
                    <q-btn v-if="!props.value && props.row.seated" @click="$parent.$emit('finish', props)" icon="sports_score" flat />
                    <div v-else-if="!props.value && !props.row.seated" style="display: flex; justify-content: center; align-items: center; height: 100%;" />
                    <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%;">
                        <q-icon name="flag" color="green" size="md" />
                    </div>
                </q-td>''')
                self.table.on('finish', lambda event: asyncio.create_task(self._handle_finish(event)))

            if self.on_edit_stream_room is not None:
                self.table.add_slot('body-cell-stream_room', '''<q-td :props="props">
                    <q-btn v-if="!props.value" @click="$parent.$emit('edit-stream-room', props)" icon="movie" flat />
                    <template v-else>{{ props.value }}</template>
                </q-td>''')
                self.table.on('edit-stream-room', lambda event: asyncio.create_task(self._handle_edit_stream_room(event)))

            if self.on_edit is not None:
                self.table.on('edit_match', lambda event: asyncio.create_task(self._handle_edit(event)))

    async def refresh(self, *_args):
        match_query = self.get_query()
        
        # Apply upcoming matches filter if checked
        if self.show_upcoming_checkbox.value:
            match_query = match_query.filter(finished_at__isnull=True)
            
        # Apply tournament filter if a specific tournament is selected
        if self.tournament_filter and self.tournament_filter.value:
            # Extract the actual tournament ID from the selected object
            tournament_ids = self.tournament_filter.value
            match_query = match_query.filter(tournament_id__in=tournament_ids)

        if self.stream_room_filter and self.stream_room_filter.value:
            stream_room_ids = self.stream_room_filter.value
            match_query = match_query.filter(stream_room_id__in=stream_room_ids)

        all_matches = await match_query.prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed', 'commentators', 'commentators__user', 'trackers', 'trackers__user'
        ).order_by('scheduled_at')
        
        rows = [self._build_row(m) for m in all_matches]
        self.table.rows = rows
        self.table.update()

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
                field['separator'] = ', '  # Add space after comma
            elif field['key'] in ['seated', 'finished']:
                field['bool_or_text'] = True
                
            grid_fields.append(field)
            
        # Build JS array for Vue template
        js_field_array = ',\n    '.join([
            f"{{ label: '{f['label']}', key: '{f['key']}'" +
            (f", event: '{f['event']}'" if 'event' in f else '') +
            (", array: true" if f.get('array') else '') +
            (", arrayObjects: true" if f.get('array_objects') else '') +
            (", nameIndex: " + str(f['name_index']) if 'name_index' in f else '') +
            (", approvedIndex: " + str(f['approved_index']) if 'approved_index' in f else '') +
            (", boolOrText: true" if f.get('bool_or_text') else '') +
            (f", separator: '{f['separator']}'" if 'separator' in f else '') +
            (f", discord_id: {f['discord_id']}" if 'discord_id' in f else '') +
            " }" for f in grid_fields
        ])
        
        self.table.add_slot('item', f'''
        <div class="q-pa-md q-mb-sm" style="width: 100%; box-sizing: border-box; border: 1px solid #eee; border-radius: 8px; background: #fff;">
        <div v-for="field in [
            {js_field_array}
        ]" :key="field.key" class="row items-center q-mb-xs">
            <div class="col-4 text-grey-7">{{{{ field.label }}}}:</div>
            <div class="col-8">
                <!-- For fields with click events like match ID -->
                <template v-if="field.event">
                    <a href="#" @click="$parent.$emit(field.event, {{ row: props.row }})" style="color: #1976d2; text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
                </template>
                
                <!-- For array fields like players -->
                <template v-else-if="field.array">
                    <span>{{{{ Array.isArray(props.row[field.key]) ? props.row[field.key].join(field.separator || ', ') : props.row[field.key] }}}}</span>
                </template>
                
                <!-- For array of objects like commentators/trackers with approval status -->
                <template v-else-if="field.arrayObjects">
                    <span>
                        <!-- Add signup/undo buttons for commentator/tracker fields -->
                        <template v-if="field.key === 'commentators' || field.key === 'trackers'">
                            <div style="margin-bottom: 8px;">
                                <q-btn v-if="props.row[field.key] && props.row[field.key].some(item => item[2] == field.discord_id)"
                                       icon="undo" color="negative" size="sm" 
                                       @click="$parent.$emit('undo_' + field.key.slice(0, -1), props.row)" 
                                       style="margin-right: 8px;">
                                    Undo
                                </q-btn>
                                <q-btn v-if="props.row[field.key] && !props.row[field.key].some(item => item[2] == field.discord_id)" 
                                       icon="assignment" color="primary" size="sm" 
                                       @click="$parent.$emit('signup_' + field.key.slice(0, -1), props.row)" 
                                       style="margin-right: 8px;">
                                    Sign Up
                                </q-btn>
                            </div>
                        </template>
                        
                        <template v-if="Array.isArray(props.row[field.key])">
                            <template v-for="(item, idx) in props.row[field.key]">
                                <template v-if="(field.key === 'commentators' || field.key === 'trackers') && {'true' if self.admin_controls else 'false'}">
                                    <a href="#" @click="$parent.$emit('edit_' + field.key.slice(0, -1), {{ row: props.row, idx }})"
                                       :style="'color: ' + (item[field.approvedIndex] ? '#4CAF50' : '#FF9800') + '; font-weight: ' + (item[field.approvedIndex] ? 'bold' : 'normal') + '; text-decoration: underline;'">
                                        {{{{ item[field.nameIndex] }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                    </a>
                                </template>
                                <template v-else>
                                    <span :style="'color: ' + (item[field.approvedIndex] ? '#4CAF50' : '#FF9800') + '; font-weight: ' + (item[field.approvedIndex] ? 'bold' : 'normal')">
                                        {{{{ item[field.nameIndex] }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                    </span>
                                </template>
                            </template>
                        </template>
                        <template v-else>{{{{ props.row[field.key] }}}}</template>
                    </span>
                </template>
                
                <!-- For boolean or text fields like seated/finished -->
                <template v-else-if="field.boolOrText">
                    <template v-if="props.row[field.key] === true">Yes</template>
                    <template v-else-if="props.row[field.key] === false">No</template>
                    <template v-else>{{{{ props.row[field.key] || '' }}}}</template>
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
                           :href="props.row[field.key]" target="_blank" style="color: #1976d2; text-decoration: underline;">
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </a>
                        <span v-else>
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </span>
                    </template>
                    <template v-else-if="!{'true' if self.admin_controls else 'false'} || !props.row.tournament_seed_generator">-</template>
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
        asyncio.create_task(self.refresh())

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

    async def _handle_finish(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_finish:
            await self.on_finish(match_id)

    async def _handle_edit_stream_room(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit_stream_room:
            await self.on_edit_stream_room(match_id)

    async def update_row_by_id(self, match_id):
        """
        Update a single row in the table by its match ID, only if the row is currently visible.
        Does not respect the upcoming filter, but only updates if the row is present in self.table.rows.
        """
        # Find the index of the row with the given match_id
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is None:
            return  # Row not visible, do nothing
        # Query for the match object - ignoring tournament filter to properly handle row updates
        match_query = self.get_query()
        
        # We don't apply tournament filter here because this is updating a specific row that's already visible
        m = await match_query.filter(id=match_id).prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed', 'commentators', 'commentators__user', 'trackers', 'trackers__user'
        ).first()
        if not m:
            # Match not found, delete the row from the table
            del self.table.rows[idx]
            self.table.update()
            return
        row = self._build_row(m)
        self.table.rows[idx] = row
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
