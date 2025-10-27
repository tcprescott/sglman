"""Admin Settings/Tournaments Management Page"""

import asyncio

from nicegui import ui

from application.repositories import StreamRoomRepository
from models import Tournament
from theme.dialog import TournamentDialog
from theme.dialog.stream_room_edit_dialog import StreamRoomEditDialog
from theme.tables.tournament import TournamentTableView


def admin_tournaments_page() -> None:
    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Tournament Management').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'name', 'label': 'Name', 'field': 'name'},
            {'name': 'description', 'label': 'Description', 'field': 'description'},
            {'name': 'seed_generator', 'label': 'Seed Generator', 'field': 'seed_generator'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
            {'name': 'players_per_match', 'label': 'Players/Match', 'field': 'players_per_match'},
            {'name': 'average_match_duration', 'label': 'Avg Match Duration (min)', 'field': 'average_match_duration'},
            {'name': 'max_match_duration', 'label': 'Max Match Duration (min)', 'field': 'max_match_duration'},
            {'name': 'staff_administered', 'label': 'Staff Administered', 'field': 'staff_administered'},
            {'name': 'player_count', 'label': 'Player Count', 'field': 'player_count'},
        ]

        async def add_tournament():
            async def after_submit(_):
                await table_view.refresh()
            dialog = TournamentDialog(on_submit=after_submit)
            await dialog.open()

        def get_query():
            return Tournament.all()
        
        table_view = TournamentTableView(
            columns=columns, get_query=get_query, submit_tournament_callback=add_tournament)
        
        def on_tab_selected():
            asyncio.create_task(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Tournaments' else None)


def admin_stream_rooms_page() -> None:
    with ui.column().classes('page-container-narrow'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Stream Room Management').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True, 'clickable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'stream_url', 'label': 'Stream URL', 'field': 'stream_url'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
        ]

        table_container = ui.column().classes('w-full')

        async def load_stream_rooms():
            rooms = await StreamRoomRepository.get_all()
            rows = [
                {
                    'id': room.id,
                    'name': room.name,
                    'stream_url': room.stream_url or '',
                    'is_active': room.is_active,
                }
                for room in rooms
            ]
            return rows

        async def refresh_table():
            rows = await load_stream_rooms()
            table.rows = rows
            table.update()

        async def add_stream_room():
            async def after_submit(_):
                await refresh_table()
            with table_container:
                dialog = StreamRoomEditDialog(on_submit=after_submit)
                await dialog.open()

        async def edit_stream_room(row):
            room = await StreamRoomRepository.get_by_id(row['id'])
            if not room:
                ui.notify('Stream room not found.', color='warning')
                return
            async def after_submit(_):
                await refresh_table()
            with table_container:
                dialog = StreamRoomEditDialog(stream_room=room, on_submit=after_submit)
                await dialog.open()

        with table_container:
            with ui.row().classes('w-full justify-end mb-1'):
                ui.button('Add Stream Room', icon='add', on_click=add_stream_room).props('color=primary')
            
            table = ui.table(
                columns=columns,
                rows=[],
                row_key='id',
            ).classes('w-full')
            
            # Enable grid mode for mobile using Quasar's screen detection
            table.props(':grid="Quasar.Screen.lt.md"')
            
            table.add_slot('body-cell-stream_url', '''
                <q-td :props="props">
                    <a :href="props.row.stream_url" target="_blank" v-if="props.row.stream_url">
                        {{ props.row.stream_url }}
                    </a>
                    <span v-else>-</span>
                </q-td>
            ''')
            
            table.add_slot('body-cell-is_active', '''
                <q-td :props="props">
                    <q-icon :name="props.row.is_active ? 'check_circle' : 'cancel'" 
                            :color="props.row.is_active ? 'positive' : 'negative'" size="sm" />
                </q-td>
            ''')
            
            table.add_slot('body', '''
                <q-tr :props="props">
                    <q-td v-for="col in props.cols" :key="col.name" :props="props">
                        <template v-if="col.name === 'id'">
                            <a href="javascript:void(0)" @click="$parent.$emit('edit', props.row)" 
                               style="color: #1976d2; text-decoration: underline; cursor: pointer;">
                                {{ col.value }}
                            </a>
                        </template>
                        <template v-else-if="col.name === 'stream_url'">
                            <a :href="props.row.stream_url" target="_blank" v-if="props.row.stream_url">
                                {{ props.row.stream_url }}
                            </a>
                            <span v-else>-</span>
                        </template>
                        <template v-else-if="col.name === 'is_active'">
                            <q-icon :name="props.row.is_active ? 'check_circle' : 'cancel'" 
                                    :color="props.row.is_active ? 'positive' : 'negative'" size="sm" />
                        </template>
                        <template v-else>
                            {{ col.value }}
                        </template>
                    </q-td>
                </q-tr>
            ''')
            
            # Add grid item slot for mobile/card view
            table.add_slot('item', '''
                <div class="q-pa-xs col-xs-12 col-sm-6 col-md-4">
                    <q-card class="q-pa-md" style="cursor: pointer;" @click="$parent.$emit('edit', props.row)">
                        <q-card-section>
                            <div class="text-h6">
                                {{ props.row.name }}
                                <q-badge :color="props.row.is_active ? 'positive' : 'negative'" class="q-ml-sm">
                                    {{ props.row.is_active ? 'Active' : 'Inactive' }}
                                </q-badge>
                            </div>
                            <div class="text-caption text-grey">ID: {{ props.row.id }}</div>
                        </q-card-section>
                        <q-card-section v-if="props.row.stream_url">
                            <div class="text-caption text-grey-7">Stream URL:</div>
                            <a :href="props.row.stream_url" target="_blank" 
                               @click.stop
                               style="color: #1976d2; text-decoration: underline; word-break: break-all;">
                                {{ props.row.stream_url }}
                            </a>
                        </q-card-section>
                        <q-card-section v-else>
                            <div class="text-caption text-grey-7">No stream URL set</div>
                        </q-card-section>
                    </q-card>
                </div>
            ''')
            
            table.on('edit', lambda e: asyncio.create_task(edit_stream_room(e.args)))

        asyncio.create_task(refresh_table())
