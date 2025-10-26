"""Admin Settings/Tournaments Management Page"""

import asyncio

from nicegui import ui

from models import Tournament, StreamRoom
from theme.dialog import TournamentDialog
from theme.dialog.stream_room_edit_dialog import StreamRoomEditDialog
from theme.tables.tournament import TournamentTableView


def admin_settings_page() -> None:
    with ui.tabs().classes('w-full') as tabs:
        ui.tab('Tournaments', icon='emoji_events')
        ui.tab('Stream Rooms', icon='tv')
    
    with ui.tab_panels(tabs, value='Tournaments').classes('w-full'):
        with ui.tab_panel('Tournaments'):
            admin_tournaments_page()
        with ui.tab_panel('Stream Rooms'):
            admin_stream_rooms_page()


def admin_tournaments_page() -> None:
    with ui.column().style('width: 100%; max-width: 1400px; margin: 0 auto;'):
        # Header section
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Tournament Management').style('font-size: 2em; font-weight: bold;')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
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
    with ui.column().style('width: 100%; max-width: 1200px; margin: 0 auto;'):
        # Header section
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Stream Room Management').style('font-size: 2em; font-weight: bold;')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'stream_url', 'label': 'Stream URL', 'field': 'stream_url'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
        ]

        table_container = ui.column().classes('w-full')

        async def load_stream_rooms():
            rooms = await StreamRoom.all()
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
            room = await StreamRoom.get(id=row['id'])
            async def after_submit(_):
                await refresh_table()
            with table_container:
                dialog = StreamRoomEditDialog(stream_room=room, on_submit=after_submit)
                await dialog.open()

        with table_container:
            with ui.row().classes('w-full justify-end').style('margin-bottom: 1em;'):
                ui.button('Add Stream Room', icon='add', on_click=add_stream_room).props('color=primary')
            
            table = ui.table(
                columns=columns,
                rows=[],
                row_key='id',
            ).classes('w-full')
            
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
                        <template v-if="col.name === 'stream_url'">
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
                    <q-td auto-width>
                        <q-btn size="sm" color="primary" flat dense icon="edit" 
                               @click="$parent.$emit('edit', props.row)" />
                    </q-td>
                </q-tr>
            ''')
            
            table.on('edit', lambda e: asyncio.create_task(edit_stream_room(e.args)))

        asyncio.create_task(refresh_table())
