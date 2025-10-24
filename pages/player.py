
import asyncio

from nicegui import app, ui

from models import Match, Permissions, User
from theme.base import BaseLayout
from theme.dialog import MatchDialog
from theme.tables.match import MatchTableView


def render_player_dashboard():
    with ui.row().style('width: 100%;'):
        ui.label('Your Schedule').style('font-size: 2em; margin-bottom: 1em;')
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
            # {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room'},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
        ]

        extra_slots = {
            'body-cell-generated_seed': '''<q-td :props="props">
                <span v-if="props.value">
                    <template v-if="/^https?:\\/\\//.test(props.value)">
                        <a :href="props.value" target="_blank" style="color: #1976d2; text-decoration: underline;" :title="props.value">
                            {{ props.value.length > 40 ? props.value.substring(0, 37) + '...' : props.value }}
                        </a>
                    </template>
                    <template v-else>{{ props.value }}</template>
                </span>
            </q-td>''',
        }

        async def submit_match():
            dialog = MatchDialog(discord_id=discord_id)
            await dialog.open()
        def get_query():
            return Match.filter(players__user__discord_id=discord_id)
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            submit_match_callback=submit_match,
            extra_slots=extra_slots
        )
        asyncio.create_task(table_view.refresh())


async def render_edit_info_tab():
    with ui.row().style('width: 100%;'):
        ui.label('Edit Your Information').style('font-size: 2em; margin-bottom: 1em;')
    ui.separator()
    from models import Tournament, TournamentPlayers, User
    discord_id = app.storage.user.get('discord_id', None)
    if not discord_id:
        with ui.row():
            ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login', text='Login with Discord').style('margin-left: auto;')
        with ui.row():
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
        return
    user = await User.get_or_none(discord_id=discord_id)
    if user is None:
        with ui.row():
            ui.label('User not found in the database.').style('color: red; font-weight: bold;')
        return

    tournaments = await Tournament.filter(is_active=True)
    user_tournaments = await TournamentPlayers.filter(user=user)
    selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

    with ui.row().style('width: 100%;'):
        with ui.card().style('padding: 1em;'):
            display_name_hint = f"(default: {user.username})" if not user.display_name else ""
            display_name_input = ui.input('Display Name', value=user.display_name or '', placeholder=display_name_hint)
            pronouns_input = ui.input('Pronouns', value=user.pronouns or '', placeholder='e.g. they/them')
    tournament_checkboxes = {}
    staff_tournaments = [t for t in tournaments if t.staff_administered]
    player_tournaments = [t for t in tournaments if not t.staff_administered]

    def render_tournament_grid(tournament_list, label, columns=4):
        ui.label(label).style('margin-top: 1em; font-weight: bold;')
        rows = [tournament_list[i:i+columns] for i in range(0, len(tournament_list), columns)]
        for row in rows:
            with ui.row():
                for t in row:
                    checked = t.id in selected_tournament_ids
                    tournament_checkboxes[t.id] = ui.checkbox(t.name, value=checked)
                # Fill empty cells if less than columns
                for _ in range(columns - len(row)):
                    ui.label('')

    with ui.row().style('width: 100%;'):
        with ui.card().style('padding: 1em;'):
            render_tournament_grid(staff_tournaments, 'Staff Administered Tournaments', columns=4)
    with ui.row().style('width: 100%;'):
        with ui.card().style('padding: 1em;'):
            render_tournament_grid(player_tournaments, 'Community Tournaments', columns=4)

    async def save_info():
        user.display_name = display_name_input.value.strip()
        user.pronouns = pronouns_input.value.strip()
        await user.save()
        # Update tournaments
        selected_ids = set(tid for tid, cb in tournament_checkboxes.items() if cb.value)
        current_ids = set(selected_tournament_ids)
        # Remove deselected
        for tp in user_tournaments:
            if tp.tournament_id not in selected_ids:
                await tp.delete()
        # Add newly selected
        for tid in selected_ids:
            if tid not in current_ids:
                tournament = next((t for t in tournaments if t.id == tid), None)
                if tournament:
                    await TournamentPlayers.create(user=user, tournament=tournament)
        ui.notify('Information updated.', color='positive')

    with ui.row().style('margin-top: 1em;'):
        ui.button('Save', color='green', on_click=save_info)

