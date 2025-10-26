
import asyncio

from nicegui import app, ui

from models import Match
from theme.tables.match import MatchTableView


def schedule():
    discord_id = app.storage.user.get('discord_id', None)
    
    with ui.column().style('width: 100%; max-width: 1400px; margin: 0 auto;'):
        # Header section
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Schedule & Crew Signup').style('font-size: 2em; font-weight: bold;')
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
            {'name': 'players', 'label': 'Players', 'field': 'players', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room', 'sortable': True, 'filterable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
        ]

        def get_query():
            return Match.all().prefetch_related('tournament', 'players', 'stream_room', 'generated_seed').order_by('scheduled_at')

        extra_slots = {
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

        # Include crew signup functionality with centralized green/yellow status rendering
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            extra_slots=extra_slots
        )

        # Initial table load
        asyncio.create_task(table_view.refresh())
