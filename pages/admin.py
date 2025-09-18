from nicegui import ui
from models import Match
from theme.match_table import MatchTable
import asyncio
from datetime import datetime, timedelta
from pages.dialogues import MatchDialog, ConfirmationDialog

def create() -> None:
    @ui.page('/admin')
    def admin_page() -> None:
        ui.label('Admin Page').style('font-size: 2em; margin-bottom: 1em;')
        ui.label('This is the admin dashboard for managing matches, players, and tournaments.')

        with ui.card().style('width: 100%; max-width: 1100px; margin: 0 auto; padding: 0;'):
            with ui.column().style('width: 100%;'):
                show_upcoming_checkbox = ui.checkbox('Show only upcoming matches', value=True)

                async def submit_admin_match():
                    async def after_submit(_):
                        await refresh()
                    dialog = MatchDialog(select_multiple=True, on_submit=after_submit)
                    await dialog.open()

                async def edit_row(event):
                    row_id = event.args['key']
                    match = await Match.get(id=row_id)
                    async def after_edit(_):
                        await refresh()
                    dialog = MatchDialog(match=match, is_edit=True, on_submit=after_edit)
                    await dialog.open()

                async def roll_seed(event):
                    row_id = event.args['key']
                    print(f'Roll seed for row with ID: {row_id}')

                async def seat_players(event):
                    row_id = event.args['key']
                    match = await Match.get(id=row_id).prefetch_related('players', 'players__user')
                    player_names = ', '.join([p.user.username for p in match.players])
                    async def handle_confirm(_):
                        dialog.dialog.close()
                        await confirm_seating(match)
                    dialog = ConfirmationDialog(
                        message=f'Are you sure you want to mark the following players as seated for match ID {match.id}?\n\n{player_names}',
                        on_confirm=handle_confirm
                    )
                    dialog.open()

                async def confirm_seating(match: Match):
                    match.seated_at = datetime.now()
                    await match.save()
                    await refresh()

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
                            'tournament': m.tournament.name,
                            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else None,
                            'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else None,
                            'players': player_names,
                            'stream_room': m.stream_room.name if m.stream_room else None,
                            'seed': m.generated_seed.seed_url if m.generated_seed else None,
                            'actions': ''  # Placeholder for action buttons
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
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ]
                match_table = MatchTable(columns=columns, admin_controls=True)
                table = match_table.render()
                # Add slot for actions column using a Vue template string
                match_table.table.add_slot(
                    'body-cell-actions',
                    '''<q-td :props="props">
                        <q-btn @click="$parent.$emit('edit', props)" icon="edit" flat />
                    </q-td>'''
                )

                match_table.table.add_slot(
                    'body-cell-generated_seed',
                    '''<q-td :props="props">
                        <q-btn v-if="!props.value" @click="$parent.$emit('roll', props)" icon="casino" flat />
                        <span v-else>{{ props.value }}</span><q-btn v-if="props.value" @click="$parent.$emit('undo_roll', props)" icon="close" flat />
                    </q-td>'''
                )

                match_table.table.add_slot(
                    'body-cell-seated',
                    '''<q-td :props="props">
                        <q-btn v-if="!props.value" @click="$parent.$emit('seat', props)" icon="chair" flat />
                        <span v-else>{{ props.value }}</span><q-btn v-if="props.value" @click="$parent.$emit('undo_seat', props)" icon="close" flat />
                    </q-td>'''
                )

                # Listen for the custom 'action' event and call your dialog logic
                match_table.table.on('edit', edit_row)
                match_table.table.on('roll', roll_seed)
                match_table.table.on('seat', seat_players)


                # Initial table load
                asyncio.create_task(refresh())