

from nicegui import app, background_tasks, ui

from application.services import MatchService
from theme.dialog.match_dialog import UserMatchDialog
from theme.tables.match import MatchTableView


def schedule():
    discord_id = app.storage.user.get('discord_id', None)
    match_service = MatchService()

    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Schedule & Crew Signup').classes('page-title')
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')

        ui.separator().classes('separator-spacing')

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            {'name': 'players', 'label': 'Players', 'field': 'players', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room', 'sortable': True, 'filterable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
        ]
        if discord_id:
            columns.append({'name': 'watch', 'label': 'Watch', 'field': 'watch'})

        async def get_query():
            return await match_service.get_all_matches_for_schedule()

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
                <div v-else style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <q-icon name="schedule" class="st-neutral" size="sm" />
                        <span>{{ props.value || 'Scheduled' }}</span>
                    </div>
                    <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
                </div>
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

        async def on_edit(match_id: int):
            if not discord_id:
                return
            match = await match_service.get_by_id(match_id)
            if not match:
                ui.notify('Match not found.', color='warning')
                return
            dialog = UserMatchDialog(
                discord_id=discord_id,
                match=match,
                on_submit=lambda *_: table_view.refresh(),
            )
            await dialog.open()

        # Include crew signup functionality with centralized green/yellow status rendering
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            extra_slots=extra_slots,
            on_edit=on_edit if discord_id else None,
            grid_breakpoint='lt.lg',
        )

        # Initial table load
        background_tasks.create(table_view.refresh())
