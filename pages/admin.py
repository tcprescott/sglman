import asyncio
from datetime import datetime
from typing import Dict

from nicegui import app, ui

from application.seedgen import RANDOMIZERS
from pages.announcement_admin import announcement_admin_page
from models import GeneratedSeeds, Match, Permissions, Tournament, User
from theme.base import BaseLayout
from theme.dialog import (ConfirmationDialog, MatchDialog, TournamentDialog,
                          UserDialog)
from theme.dialog.stream_room_dialog import StreamRoomDialog
from theme.tables.match import MatchTableView
from theme.tables.tournament import TournamentTableView
from theme.tables.user import UserTableView

# per-match locks to avoid concurrent seed generation for the same match
_seed_locks: Dict[int, asyncio.Lock] = {}


def create() -> None:
    @ui.page('/admin')
    async def admin_dashboard_page(tab: str = None) -> None:
        ui.page_title('Speedgaming Live Onsite - Admin Dashboard')
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.row():
                ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return

        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.row():
                ui.label('User not found in the database.').style('color: red; font-weight: bold;')
            return
        if user.permission < Permissions.TOURNAMENT_ADMIN:
            await BaseLayout(page_name='admin2').render()
            with ui.row():
                ui.label('You do not have permission to view this page.').style('color: red; font-weight: bold;')
            return

        # Define tab data model: label and content function
        tabs = [
            {'label': 'Schedule', 'icon': 'schedule', 'content': admin_schedule_page},
            {'label': 'Users', 'icon': 'people', 'content': admin_users_page},
            {'label': 'Reports', 'icon': 'report', 'content': lambda: ui.label('Reports section is under construction.').style('color: red; font-weight: bold;')},
            {'label': 'Settings', 'icon': 'settings', 'content': admin_settings_page},
            {'label': 'Announcements', 'icon': 'announcement', 'content': announcement_admin_page},
        ]

        base_layout = BaseLayout(tabs=tabs, default_tab=tab, page_name='admin', user=user)
        await base_layout.render()

def admin_settings_page() -> None:
    admin_tournaments_page()

def admin_users_page() -> None:
    with ui.row().style('width: 100%;'):
        ui.label('User Management').style('font-size: 2em; margin-bottom: 1em;')
    columns = [
        {'name': 'username', 'label': 'Username', 'field': 'username'},
        {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name'},
        {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns'},
        {'name': 'permission', 'label': 'Permission', 'field': 'permission'},
    ]

    def get_query():
        return User.all()

    async def add_user():
        async def after_submit(_):
            await table_view.refresh()
        dialog = UserDialog(on_submit=after_submit, admin_view=True)
        await dialog.open()

    table_view = UserTableView(
        columns=columns, get_query=get_query, submit_user_callback=add_user)
    def on_tab_selected():
        asyncio.create_task(table_view.refresh())
    ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)

def admin_tournaments_page() -> None:
    with ui.row().style('width: 100%;'):
        ui.label('Tournament Management').style('font-size: 2em; margin-bottom: 1em;')
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
    def on_tab_selected():
        asyncio.create_task(table_view.refresh())
    ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Tournaments' else None)

def admin_schedule_page() -> None:
    with ui.row().style('width: 100%;'):
        ui.label('Schedule Management').style('font-size: 2em; margin-bottom: 1em;')
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
            {'name': 'commentators', 'label': 'Commentators',
                'field': 'commentators', 'filterable': True},
            {'name': 'trackers', 'label': 'Trackers',
                'field': 'trackers', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage',
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
                <q-btn v-if="props.row.tournament_seed_generator && !props.value"
                       :loading="props.row._generating_seed"
                       :disabled="props.row._generating_seed"
                       @click="(props.row._generating_seed = true, $parent.$emit('roll', props))"
                       icon="casino" flat />
                <span v-if="props.value">
                    <template v-if="/^https?:\\/\\//.test(props.value)">
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
            # ensure only one generator runs per match id at a time
            lock = _seed_locks.get(row_id)
            if lock is None:
                lock = asyncio.Lock()
                _seed_locks[row_id] = lock

            if lock.locked():
                # another generation is in progress for this row; skip and refresh the row to clear client spinner
                await table_view.update_row_by_id(row_id)
                return

            async with lock:
                try:
                    match = await Match.get(id=row_id).prefetch_related('tournament')
                    # sanity check: if a seed has already been generated for this match, skip
                    if match.generated_seed:
                        ui.notify('A seed has already been generated for this match.', color='warning')
                        table_view.update_row_by_id(row_id)
                        return
                    if match.tournament.seed_generator:
                        seed_generator = RANDOMIZERS.get(match.tournament.seed_generator)
                        if seed_generator:
                            seed_url = await seed_generator()
                            match.generated_seed = await GeneratedSeeds.create(
                                tournament=match.tournament,
                                seed_url=seed_url,
                                seed_info=f"Generated seed for match {match.id}"
                            )
                            await match.save()
                        else:
                            ui.notify(f"Seed generator '{match.tournament.seed_generator}' not found.", color='negative')
                finally:
                    # refresh the row so client clears spinner. Keep the lock dict entry for reuse.
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

        def on_tab_selected():
            asyncio.create_task(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
