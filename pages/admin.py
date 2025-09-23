import asyncio
import random
from datetime import datetime

from nicegui import ui, app

from models import GeneratedSeeds, Match, Tournament, User, Permissions
from theme.dialog import ConfirmationDialog, MatchDialog, TournamentDialog, UserDialog
from theme.tables.match import MatchTableView
from theme.tables.tournament import TournamentTableView
from theme.tables.user import UserTableView
from theme.base import BaseLayout


def create() -> None:
    @ui.page('/admin')
    async def admin_dashboard_page() -> None:
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return

        user = await User.get(discord_id=discord_id)
        if user.permission < Permissions.TOURNAMENT_ADMIN:
            await BaseLayout(page_name='admin2').render()
            ui.label('You do not have permission to view this page.').style('color: red; font-weight: bold;')
            return

        # Define tab data model: label and content function
        tabs = [
            {'label': 'Schedule Management', 'content': admin_schedule_page},
            {'label': 'Players', 'content': admin_users_page},
            {'label': 'Tournaments', 'content': admin_tournaments_page},
            {'label': 'Settings', 'content': admin_settings_page},
        ]

        await BaseLayout(tabs=tabs, page_name='admin', user=user).render()

    def admin_settings_page() -> None:
        ui.label('Settings Management').style(
            'font-size: 2em; margin-bottom: 1em;')
        ui.label('This section is under construction.').style(
            'color: red; font-weight: bold;')

    def admin_users_page() -> None:
        ui.label('User Management').style(
            'font-size: 2em; margin-bottom: 1em;')
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'username', 'label': 'Username', 'field': 'username'},
            {'name': 'display_name', 'label': 'Display Name', 'field': 'display_name'},
            {'name': 'discord_id', 'label': 'Discord ID', 'field': 'discord_id'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
            {'name': 'permission', 'label': 'Permission', 'field': 'permission'},
            {'name': 'created_at', 'label': 'Created At', 'field': 'created_at'},
            {'name': 'updated_at', 'label': 'Updated At', 'field': 'updated_at'},
        ]

        def get_query():
            return User.all()

        async def add_user():
            async def after_submit(_):
                await table_view.refresh()
            dialog = UserDialog(on_submit=after_submit)
            await dialog.open()

        table_view = UserTableView(
            columns=columns, get_query=get_query, submit_user_callback=add_user)
        asyncio.create_task(table_view.refresh())

    def admin_tournaments_page() -> None:
        ui.label('Tournament Management').style(
            'font-size: 2em; margin-bottom: 1em;')
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'name', 'label': 'Name', 'field': 'name'},
            {'name': 'description', 'label': 'Description', 'field': 'description'},
            {'name': 'seed_generator', 'label': 'Seed Generator', 'field': 'seed_generator'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
            {'name': 'players_per_match', 'label': 'Players/Match', 'field': 'players_per_match'},
            {'name': 'team_size', 'label': 'Team Size', 'field': 'team_size'},
            {'name': 'staff_administered', 'label': 'Staff Administered', 'field': 'staff_administered'},
            {'name': 'player_count', 'label': 'Player Count', 'field': 'player_count'},
        ]

        async def add_tournament():
            async def after_submit(_):
                await table_view.refresh()
            dialog = TournamentDialog(on_submit=after_submit)
            await dialog.open()

        def get_query():
            return Tournament.all()
        table_view = TournamentTableView(
            columns=columns, get_query=get_query, submit_tournament_callback=add_tournament)
        asyncio.create_task(table_view.refresh())

    def admin_schedule_page() -> None:
        ui.label('Schedule Management').style(
            'font-size: 2em; margin-bottom: 1em;')
        with ui.column().style('width: 100%;'):
            columns = [
                {'name': 'edit', 'label': 'Edit', 'field': 'edit'},
                {'name': 'id', 'label': 'ID', 'field': 'id'},
                {'name': 'tournament', 'label': 'Tournament',
                    'field': 'tournament', 'sortable': True, 'filterable': True},
                {'name': 'scheduled_at', 'label': 'Scheduled At',
                    'field': 'scheduled_at', 'sortable': True, 'filterable': True},
                {'name': 'seated', 'label': 'Seated', 'field': 'seated',
                    'sortable': True, 'filterable': True},
                {'name': 'finished', 'label': 'Finished',
                    'field': 'finished', 'filterable': True},
                {'name': 'players', 'label': 'Players',
                    'field': 'players', 'filterable': True},
                {'name': 'stream_room', 'label': 'Stream Room',
                    'field': 'stream_room', 'sortable': True, 'filterable': True, 'clickable': True},
                {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
            ]

            def get_query():
                return Match.all()
            extra_slots = {
                'body-cell-edit': '''<q-td :props="props">
                    <q-btn @click="$parent.$emit('edit', props)" icon="edit" flat />
                </q-td>''',
                'body-cell-generated_seed': '''<q-td :props="props">
                    <q-btn v-if="props.row.tournament_seed_generator && !props.value" @click="$parent.$emit('roll', props)" icon="casino" flat />
                    <span v-if="props.value">
                        <template v-if="/^https?:\/\//.test(props.value)">
                            <a :href="props.value" target="_blank" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
                        </template>
                        <template v-else>{{ props.value }}</template>
                    </span>
                </q-td>''',
                'body-cell-seated': '''<q-td :props="props">
                    <q-btn v-if="!props.value" @click="$parent.$emit('seat', props)" icon="chair" flat />
                    <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%;">
                        <q-icon name="check" color="green" size="md" />
                    </div>
                </q-td>''',
                'body-cell-finished': '''<q-td :props="props">
                    <q-btn v-if="!props.value && props.row.seated" @click="$parent.$emit('finish', props)" icon="sports_score" flat />
                    <div v-else-if="!props.value && !props.row.seated" style="display: flex; justify-content: center; align-items: center; height: 100%;" />
                    <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%;">
                        <q-icon name="flag" color="green" size="md" />
                    </div>
                </q-td>''',
                'body-cell-stream_room': '''<q-td :props="props">
                    <q-btn v-if="!props.value" @click="$parent.$emit('edit-stream-room', props)" icon="movie" flat />
                    <template v-else>{{ props.value }}</template>
                </q-td>''',
            }
            async def edit_stream_room(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id)
                from theme.dialog.stream_room_dialog import StreamRoomDialog
                async def after_edit(_):
                    await table_view.update_row_by_id(row_id)
                dialog = StreamRoomDialog(match=match, on_submit=after_edit)
                await dialog.open()

            async def submit_admin_match():
                async def after_submit(_):
                    await table_view.refresh()
                dialog = MatchDialog(on_submit=after_submit)
                await dialog.open()

            async def edit_row(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id)

                async def after_edit(_):
                    await table_view.update_row_by_id(row_id)
                dialog = MatchDialog(match=match, on_submit=after_edit)
                await dialog.open()

            async def roll_seed(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id).prefetch_related('tournament')
                random_number = random.randint(1, 1000)
                if match.tournament.seed_generator:
                    match.generated_seed = await GeneratedSeeds.create(
                        tournament=match.tournament,
                        seed_url=f"https://example.com/seed/{random_number}",
                        seed_info=f"Generated seed for match {match.id}"
                    )
                    await match.save()
                await table_view.update_row_by_id(row_id)

            async def seat_players(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id).prefetch_related('players', 'players__user')
                player_names = ', '.join(
                    [p.user.username for p in match.players])

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
                await table_view.update_row_by_id(match.id)

            async def finish_match(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id).prefetch_related('players', 'players__user')
                player_names = ', '.join(
                    [p.user.username for p in match.players])

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
                await table_view.update_row_by_id(match.id)

            table_view = MatchTableView(
                columns=columns,
                get_query=get_query,
                admin_controls=True,
                extra_slots=extra_slots,
                submit_match_callback=submit_admin_match
            )

            table_view.table.on('edit', edit_row)
            table_view.table.on('roll', roll_seed)
            table_view.table.on('seat', seat_players)
            table_view.table.on('finish', finish_match)
            table_view.table.on('edit-stream-room', edit_stream_room)

            # Initial table load
            asyncio.create_task(table_view.refresh())
