import asyncio

from nicegui import app, ui

from models import Match, Permissions, User
from theme.base import BaseLayout
from theme.dialog import MatchDialog
from theme.tables.match import MatchTableView


def render_crew_dashboard():
    with ui.row().style('width: 100%;'):
        ui.label('Available Matches for Crew Signup').style('font-size: 2em; margin-bottom: 1em;')
    discord_id = app.storage.user.get('discord_id', None)
    if not discord_id:
        with ui.row():
            ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login', text='Login with Discord').style('margin-left: auto;')
        with ui.row():
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
        return

    with ui.column().style('width: 100%;'):
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
            {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room'},
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
        ]

        def slot_template(role):
            return f'''<q-td :props="props">
                <div class="wrap">
                    <q-btn v-if="props.value.some(item => item[2] === {discord_id})" icon="undo" color="negative" size="sm" @click="$parent.$emit('undo_{role}', props.row)" style="margin-left: 8px;" />
                    <q-btn v-if="!props.value.some(item => item[2] === {discord_id})" icon="assignment" color="primary" size="sm" @click="$parent.$emit('signup_{role}', props.row)" style="margin-left: 8px;" />
                    <template v-for="(item, idx) in props.value">
                        <span :style="'color: ' + (item[1] ? '#1976d2' : 'red') + '; margin-right: 4px; font-weight:' + (item[1] ? 'bold' : 'normal')">{{{{ item[0] }}}}</span><br/>
                    </template>
                </div>
            </q-td>'''
        extra_slots = {
            'body-cell-commentators': slot_template('commentator'),
            'body-cell-trackers': slot_template('tracker'),
        }

        def get_query():
            return Match.all()

        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            extra_slots=extra_slots
        )
        asyncio.create_task(table_view.refresh())
