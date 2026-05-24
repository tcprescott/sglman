

from nicegui import app, background_tasks, ui

from application.services import MatchService
from theme.dialog.match_dialog import UserMatchDialog
from theme.tables.match import MatchTableView


def render_player_dashboard():
    discord_id = app.storage.user.get('discord_id', None)
    match_service = MatchService()
    
    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Your Schedule').classes('page-title')
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')
        
        ui.separator().classes('separator-spacing')
        
        if not discord_id:
            with ui.card().classes('card-centered'):
                ui.icon('lock', size='3em').classes('icon-large')
                ui.label('You must be logged in to view this page.').classes('text-muted')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
            {'name': 'state', 'label': 'State', 'field': 'state'},
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'acknowledgments', 'label': 'Acks', 'field': 'acknowledgments'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room'},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
        ]

        extra_slots = {
            'body-cell-state': '''<q-td :props="props">
                <!-- Confirmed state -->
                <div v-if="props.value === 'Confirmed'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="verified" color="green" size="sm" />
                        <span style="font-weight: 500;">{{ props.value }}</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #666;">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Finished state -->
                <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="flag" color="orange" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #666;">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Started state -->
                <div v-else-if="props.value === 'Started'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="play_arrow" color="blue" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #666;">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Checked In state -->
                <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="check" color="grey" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span style="font-size: 0.75rem; color: #666;">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Scheduled state -->
                <span v-else>{{ props.value || 'Scheduled' }}</span>
            </q-td>''',
            'body-cell-generated_seed': '''<q-td :props="props">
                <span v-if="props.value">
                    <template v-if="/^https?:\\/\\//.test(props.value)">
                        <a :href="props.value" target="_blank" style="color: #1976d2; text-decoration: underline;" :title="props.value">
                            {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
                        </a>
                    </template>
                    <template v-else>{{ props.value }}</template>
                </span>
            </q-td>''',
        }

        async def submit_match():
            dialog = UserMatchDialog(discord_id=discord_id)
            await dialog.open()
        
        async def get_query():
            return await match_service.get_matches_for_player(discord_id)
        
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            submit_match_callback=submit_match,
            extra_slots=extra_slots
        )
        background_tasks.create(table_view.refresh())

