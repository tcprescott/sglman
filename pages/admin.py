import asyncio
import random
from datetime import datetime

from nicegui import ui

from models import GeneratedSeeds, Match, Tournament, User
from pages.dialogues import ConfirmationDialog, MatchDialog, TournamentEditDialog, UserEditDialog
from pages.match_table_common import MatchTableView
from pages.tournament_table_common import TournamentTableView
from pages.user_table_common import UserTableView


def create() -> None:
    @ui.page('/admin')
    def admin_dashboard_page() -> None:
        with ui.tabs().style('width: 100%; max-width: margin: 0 auto;') as panels:
            ui.tab('Schedule')
            ui.tab('Users')
            ui.tab('Tournaments')
            ui.tab('Settings')
        with ui.tab_panels(panels, value='Schedule'):
            with ui.tab_panel('Schedule'):
                with ui.row().classes('justify-center').style('width: 100%;'):
                    admin_schedule_page()
            with ui.tab_panel('Users'):
                with ui.row().classes('justify-center').style('width: 100%;'):
                    admin_users_page()
            with ui.tab_panel('Tournaments'):
                with ui.row().classes('justify-center').style('width: 100%;'):
                    admin_tournaments_page()
            with ui.tab_panel('Settings'):
                with ui.row().classes('justify-center').style('width: 100%;'):
                    admin_settings_page()

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
            dialog = UserEditDialog(on_submit=after_submit)
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
        ]

        async def add_tournament():
            async def after_submit(_):
                await table_view.refresh()
            dialog = TournamentEditDialog(on_submit=after_submit)
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
                    'field': 'stream_room', 'sortable': True, 'filterable': True},
                {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
            ]

            def get_query():
                return Match.all()
            extra_slots = {
                'body-cell-edit': '''<q-td :props="props">
                    <q-btn @click="$parent.$emit('edit', props)" icon="edit" flat />
                </q-td>''',
                'body-cell-generated_seed': '''<q-td :props="props">
                    <q-btn v-if="!props.value" @click="$parent.$emit('roll', props)" icon="casino" flat />
                    <span v-else>
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
            }

            async def submit_admin_match():
                async def after_submit(_):
                    await table_view.refresh()
                dialog = MatchDialog(
                    select_multiple=True, on_submit=after_submit)
                await dialog.open()

            async def edit_row(event):
                row_id = event.args['key']
                match = await Match.get(id=row_id)

                async def after_edit(_):
                    await table_view.update_row_by_id(row_id)
                dialog = MatchDialog(
                    match=match, is_edit=True, on_submit=after_edit)
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

            # Initial table load
            asyncio.create_task(table_view.refresh())
