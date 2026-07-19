"""Admin Settings/Tournaments Management Page"""


from nicegui import app, background_tasks, context, ui

from application.services import AuthService, StreamRoomService, get_user_from_discord_id
from application.tenant_context import require_tenant_id
from models import Tournament
from theme.dialog import TournamentDialog
from theme.dialog.stream_room_edit_dialog import StreamRoomEditDialog
from theme.tables.tournament import TournamentTableView


async def admin_tournaments_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_create = await AuthService.is_staff(actor)

    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Tournament Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'The tournaments this community runs — players per match, durations, '
            'and seed generator. Click a name to edit, or a player count to manage '
            'entrants.'
        ).classes('text-caption text-grey')

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
            return Tournament.filter(tenant_id=require_tenant_id())
        
        table_view = TournamentTableView(
            columns=columns, get_query=get_query,
            submit_tournament_callback=add_tournament if can_create else None,
        )
        
        def on_tab_selected():
            background_tasks.create(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Tournaments' else None)


async def admin_stream_rooms_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_manage = await AuthService.can_manage_stream_rooms(actor)

    with ui.column().classes('page-container-narrow'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Stream Room Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'The stages matches can be assigned to. Each maps to a stream URL used '
            'across the schedule and On Air views.'
        ).classes('text-caption text-grey')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True, 'clickable': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'stream_url', 'label': 'Stream URL', 'field': 'stream_url'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
        ]

        table_container = ui.column().classes('w-full')

        async def load_stream_rooms():
            rooms = await StreamRoomService().get_all_stream_rooms()
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

        async def edit_stream_room(row, client):
            # Runs in a background task (table 'edit' event → background_tasks.create),
            # where the slot stack is empty; restore the captured client so ui.notify
            # and the dialog have a slot context.
            with client:
                room = await StreamRoomService().get_stream_room_by_id(row['id'])
                if not room:
                    ui.notify('Stream room not found.', color='warning')
                    return
                async def after_submit(_):
                    await refresh_table()
                dialog = StreamRoomEditDialog(stream_room=room, on_submit=after_submit)
                await dialog.open()

        with table_container:
            with ui.row().classes('full-width'):
                if can_manage:
                    ui.button('Add Stream Room', icon='add', on_click=add_stream_room).props('color=primary')
                ui.space()
                ui.button(icon='refresh', on_click=lambda: background_tasks.create(refresh_table())).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(
                columns=columns,
                rows=[],
                row_key='id',
            ).classes('w-full sgl-table')
            
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
                               style="color: var(--sgl-link); text-decoration: underline; cursor: pointer;">
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
                    <q-card class="q-pa-sm">
                        <q-card-section class="q-pa-sm">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <span class="text-h6">{{ props.row.name }}</span>
                                    <q-badge :color="props.row.is_active ? 'positive' : 'negative'" class="q-ml-sm">
                                        {{ props.row.is_active ? 'Active' : 'Inactive' }}
                                    </q-badge>
                                </div>
                                <q-btn flat round dense icon="edit" color="primary"
                                       @click="$parent.$emit('edit', props.row)">
                                    <q-tooltip>Edit</q-tooltip>
                                </q-btn>
                            </div>
                            <div class="text-caption text-grey">ID: {{ props.row.id }}</div>
                        </q-card-section>
                        <q-card-section class="q-pa-sm" v-if="props.row.stream_url">
                            <div class="text-caption text-grey-7">Stream URL:</div>
                            <a :href="props.row.stream_url" target="_blank"
                               style="color: var(--sgl-link); text-decoration: underline; word-break: break-all;">
                                {{ props.row.stream_url }}
                            </a>
                        </q-card-section>
                        <q-card-section class="q-pa-sm" v-else>
                            <div class="text-caption text-grey-7">No stream URL set</div>
                        </q-card-section>
                    </q-card>
                </div>
            ''')
            
            table.on('edit', lambda e: background_tasks.create(edit_stream_room(e.args, context.client)))

        background_tasks.create(refresh_table())
