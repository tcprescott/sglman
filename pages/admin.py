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
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id'},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                    {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
                    {'name': 'finished', 'label': 'Finished', 'field': 'finished'},
                    {'name': 'players', 'label': 'Players', 'field': 'players'},
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                    {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ]
                from pages.match_table_common import render_match_table
                def get_query():
                    return Match.all()
                extra_slots = {
                    'body-cell-actions': '''<q-td :props="props">
                        <q-btn @click="$parent.$emit('edit', props)" icon="edit" flat />
                    </q-td>''',
                    'body-cell-generated_seed': '''<q-td :props="props">
                        <q-btn v-if="!props.value" @click="$parent.$emit('roll', props)" icon="casino" flat />
                        <span v-else>{{ props.value }}</span><q-btn v-if="props.value" @click="$parent.$emit('undo_roll', props)" icon="close" flat />
                    </q-td>''',
                    'body-cell-seated': '''<q-td :props="props">
                        <q-btn v-if="!props.value" @click="$parent.$emit('seat', props)" icon="chair" flat />
                        <span v-else>{{ props.value }}</span>
                    </q-td>''',
                    'body-cell-finished': '''<q-td :props="props">
                        <q-btn v-if="!props.value" @click="$parent.$emit('finish', props)" icon="check" flat />
                        <span v-else>{{ props.value }}</span>
                    </q-td>''',
                }

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

                async def finish_match(event):
                    row_id = event.args['key']
                    match = await Match.get(id=row_id).prefetch_related('players', 'players__user')
                    player_names = ', '.join([p.user.username for p in match.players])
                    async def handle_confirm(_):
                        dialog.dialog.close()
                        await confirm_finishing(match)
                    dialog = ConfirmationDialog(
                        message=f'Are you sure you want to mark the following players as finished for match ID {match.id}?\n\n{player_names}',
                        on_confirm=handle_confirm
                    )
                    dialog.open()

                async def confirm_finishing(match: Match):
                    match.finished_at = datetime.now()
                    await match.save()
                    await refresh()

                table, refresh = render_match_table(
                    columns=columns,
                    get_query=get_query,
                    admin_controls=True,
                    extra_slots=extra_slots,
                    submit_match_callback=submit_admin_match
                )

                table.on('edit', edit_row)
                table.on('roll', roll_seed)
                table.on('seat', seat_players)
                table.on('finish', finish_match)

                # Initial table load
                asyncio.create_task(refresh())