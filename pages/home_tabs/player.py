

from nicegui import app, background_tasks, ui

from application.services import ChallongeService, MatchService, get_user_from_discord_id
from models import User
from theme.dialog.challonge_schedule_dialog import ChallongeScheduleDialog
from theme.dialog.match_dialog import UserMatchDialog
from theme.tables.match import MatchTableView


async def render_player_dashboard():
    discord_id = app.storage.user.get('discord_id', None)
    match_service = MatchService()
    challonge_service = ChallongeService()
    
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

        # Challonge: upcoming bracket matches the player can schedule in a few clicks.
        @ui.refreshable
        async def challonge_section():
            if not challonge_service.is_configured():
                return
            user = await User.get_or_none(discord_id=discord_id)
            if user is None:
                return
            matches = await challonge_service.list_unscheduled_matches_for_user(user)
            if not matches:
                return
            # The refreshable renders into its own container, so create elements
            # directly (there is no separate challonge_container to enter).
            with ui.card().classes('card-full-width'):
                ui.label('Upcoming matches to schedule').classes('section-title')
                ui.label('From your Challonge bracket. Pick a time and your opponent confirms.').classes(
                    'text-caption text-grey-7'
                )
                for cm in matches:
                    me_is_p1 = cm.participant1 is not None and cm.participant1.user_id == user.id
                    opponent = cm.participant2 if me_is_p1 else cm.participant1
                    opponent_name = opponent.name if opponent else 'TBD'
                    opponent_linked = opponent is not None and opponent.user_id is not None
                    with ui.row().classes('items-center full-width q-my-xs'):
                        ui.label(cm.tournament.name).classes('text-bold')
                        ui.label(f'vs {opponent_name}')
                        if cm.round is not None:
                            ui.label(f'Round {cm.round}').classes('text-caption text-muted')
                        ui.space()
                        if opponent_linked:
                            async def do_schedule(_=None, m=cm, oname=opponent_name):
                                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))

                                async def after():
                                    challonge_section.refresh()
                                    await table_view.refresh()

                                dialog = ChallongeScheduleDialog(
                                    m, actor=actor, opponent_name=oname, on_submit=after,
                                )
                                await dialog.open()

                            ui.button('Schedule', icon='event', on_click=do_schedule).props('color=primary flat')
                        else:
                            disabled_btn = ui.button('Schedule', icon='event').props('flat color=primary')
                            disabled_btn.disable()
                            disabled_btn.tooltip("Waiting for your opponent to link their Challonge account")

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
            {'name': 'state', 'label': 'State', 'field': 'state'},
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room'},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            {'name': 'watch', 'label': 'Watch', 'field': 'watch'},
        ]

        extra_slots = {
            'body-cell-state': '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <!-- Confirmed state -->
                <div v-if="props.value === 'Confirmed'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="verified" class="st-ok" size="sm" />
                        <span style="font-weight: 500;">{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Finished state -->
                <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="flag" class="st-pending" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Started state -->
                <div v-else-if="props.value === 'Started'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="play_arrow" class="st-live" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Checked In state -->
                <div v-else-if="props.value === 'Checked In'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="check" class="st-neutral" size="sm" />
                        <span>{{ props.value }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
                <!-- Scheduled state -->
                <span v-else>{{ props.value || 'Scheduled' }}</span>
            </q-td>''',
            'body-cell-generated_seed': '''<q-td :props="props" :class="props.row._flash ? 'sgl-row-flash' : ''">
                <span v-if="props.value">
                    <template v-if="/^https?:\\/\\//.test(props.value)">
                        <a :href="props.value" target="_blank" style="color: var(--sgl-link); text-decoration: underline;" :title="props.value">
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
            extra_slots=extra_slots,
            player_discord_id=discord_id
        )
        await challonge_section()
        background_tasks.create(table_view.refresh())

