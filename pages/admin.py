from nicegui import ui
from models import Match
from theme.match_table import MatchTable
import asyncio
from datetime import datetime, timedelta
from pages.dialogues import MatchSubmissionDialog, ConfirmationDialog

def create() -> None:
    @ui.page('/admin')
    def admin_page() -> None:
        ui.label('Admin Page').style('font-size: 2em; margin-bottom: 1em;')
        ui.label('This is the admin dashboard for managing matches, players, and tournaments.')

        with ui.card().style('width: 100%; max-width: 1100px; margin: 0 auto; padding: 0;'):
            with ui.column().style('width: 100%;'):
                show_upcoming_checkbox = ui.checkbox('Show only upcoming matches', value=True)

                async def submit_admin_match():
                    dialog = MatchSubmissionDialog(select_both_players=True)
                    await dialog.open()

                async def refresh():
                    now = datetime.now()
                    match_query = Match.all()
                    if show_upcoming_checkbox.value:
                        match_query = match_query.filter(scheduled_at__gte=now - timedelta(minutes=30))
                    all_matches = await match_query.prefetch_related(
                        'tournament', 'players', 'players__user', 'stream_room', 'generated_seed'
                    ).order_by('scheduled_at')
                    rows = []
                    for m in all_matches:
                        player_names = ', '.join([p.user.username for p in m.players])
                        rows.append({
                            'id': m.id,
                            'tournament': m.tournament.name if m.tournament else '',
                            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
                            'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else '',
                            'players': player_names,
                            'stream_room': m.stream_room.name if m.stream_room else '',
                            'seed': m.generated_seed.seed_url if m.generated_seed else '',
                        })
                    table.rows = rows
                    table.update()

                show_upcoming_checkbox.on('change', lambda e: asyncio.create_task(refresh()))

                with ui.row().style('width: 100%;'):
                    ui.button('Submit Match', on_click=submit_admin_match)
                    ui.button('Refresh', on_click=refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id'},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                    {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
                    {'name': 'players', 'label': 'Players', 'field': 'players'},
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                    {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
                ]
                match_table = MatchTable(columns=columns)
                table = match_table.render()
                match_table.table.add_slot('header', '''
                    <q-tr :props="props">
                        <q-th auto-width />
                        <q-th v-for="col in props.cols" :key="col.name" :props="props">
                            {{ col.label }}
                        </q-th>
                    </q-tr>
                ''')
                match_table.table.add_slot('body', '''
                    <q-tr :props="props">
                        <q-td auto-width>
                            <q-btn size="sm" color="accent" round dense
                                @click="props.expand = !props.expand"
                                :icon="props.expand ? 'remove' : 'add'" />
                        </q-td>
                        <q-td v-for="col in props.cols" :key="col.name" :props="props">
                            {{ col.value }}
                        </q-td>
                    </q-tr>
                    <q-tr v-show="props.expand" :props="props">
                        <q-td colspan="100%">
                            <div class="text-left">This is {{ props.row.id }}.</div>
                        </q-td>
                    </q-tr>
                ''')
                match_table.table.on('approve', lambda e: ui.notify(f'Approved match ID {e.props.row.id}', color='positive'))
                match_table.table.on('deny', lambda e: ui.notify(f'Denied match ID {e.props.row.id}', color='negative'))

                # Initial table load
                asyncio.create_task(refresh())