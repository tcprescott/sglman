
import asyncio

from nicegui import app, ui

from models import Match, Permissions, User
from theme.base import BaseLayout
from theme.tables.match import MatchTableView


def schedule():
    discord_id = app.storage.user.get('discord_id', None)
    with ui.row().style('width: 100%; margin-bottom: 1em; justify-content: center;'):
        ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login', text='Login with Discord').style('font-size: 1.5em; color: white; background-color: #4CAF50; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; justify-content: center;') if not discord_id else None

    with ui.row().style('width: 100%;'):
        ui.label('Scheduled Matches').style('font-size: 2em; margin-bottom: 1em;')
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id'},
        {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True, 'filterable': True},
        {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at', 'sortable': True, 'filterable': True},
        {'name': 'players', 'label': 'Players', 'field': 'players', 'filterable': True},
        {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room', 'sortable': True, 'filterable': True},
        {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
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

    # No admin controls or extra slots for schedule view
    table_view = MatchTableView(
        columns=columns,
        get_query=get_query,
        admin_controls=False,
        extra_slots=extra_slots
    )

    # Initial table load
    asyncio.create_task(table_view.refresh())
