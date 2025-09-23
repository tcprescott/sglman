from nicegui import ui, app
from theme.base import BaseLayout
from models import Match, User, Permissions
from theme.dialog import MatchDialog
import asyncio
from theme.tables.match import MatchTableView

def create() -> None:
    @ui.page('/crew')
    async def crew_page() -> None:
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return

        user = await User.get(discord_id=discord_id)

        tabs = [
            {'label': 'Available Matches', 'content': (render_crew_dashboard, None, {'discord_id': discord_id})},
            {'label': 'Edit Info', 'content': (render_edit_info_tab, None, {'discord_id': discord_id})},
        ]
        await BaseLayout(tabs=tabs, page_name='crew', user=user).render()

    def render_crew_dashboard(discord_id):
        ui.label('Available Matches for Crew Signup').style('font-size: 2em; margin-bottom: 1em;')

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

            extra_slots = {
                'body-cell-commentators': '''<q-td :props="props">
                    <span>
                        <template v-for="(name, idx) in props.value">
                            <span style="margin-right: 4px;">{{ name }}</span>
                        </template>
                        <q-btn label="Sign Up" color="primary" size="sm" @click="$parent.$emit('signup_commentator', props.row)" style="margin-left: 8px;" />
                    </span>
                </q-td>''',
                'body-cell-trackers': '''<q-td :props="props">
                    <span>
                        <template v-for="(name, idx) in props.value">
                            <span style="margin-right: 4px;">{{ name }}</span>
                        </template>
                        <q-btn label="Sign Up" color="primary" size="sm" @click="$parent.$emit('signup_tracker', props.row)" style="margin-left: 8px;" />
                    </span>
                </q-td>'''
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

    async def render_edit_info_tab(discord_id):
        ui.label('Edit Your Crew Information').style('font-size: 2em; margin-bottom: 1em;')
        ui.separator()
        from models import User
        user = await User.get(discord_id=discord_id)

        with ui.card().style('padding: 1em;'):
            display_name_hint = f"(default: {user.username})" if not user.display_name else ""
            display_name_input = ui.input('Display Name', value=user.display_name or '', placeholder=display_name_hint)

        async def save_info():
            user.display_name = display_name_input.value.strip()
            await user.save()
            ui.notify('Information updated.', color='positive')

        with ui.row().style('margin-top: 1em;'):
            ui.button('Save', color='green', on_click=save_info)
