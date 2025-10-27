
import asyncio

from nicegui import app, ui

from models import Match
from theme.dialog import MatchDialog
from theme.tables.match import MatchTableView


def render_player_dashboard():
    discord_id = app.storage.user.get('discord_id', None)
    
    with ui.column().style('width: 100%; max-width: 1400px; margin: 0 auto;'):
        # Header section
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Your Schedule').style('font-size: 2em; font-weight: bold;')
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
        if not discord_id:
            with ui.card().style('padding: 2em; text-align: center;'):
                ui.icon('lock', size='3em').style('color: #FF9800; margin-bottom: 0.5em;')
                ui.label('You must be logged in to view this page.').style('color: #666; font-size: 1.2em; margin-bottom: 1em;')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return

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
    with ui.column().style('width: 100%; max-width: 1200px; margin: 0 auto;'):
        # Header
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Edit Your Information').style('font-size: 2em; font-weight: bold;')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
        from models import Tournament, TournamentPlayers, User
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.card().style('padding: 2em; text-align: center;'):
                ui.icon('lock', size='3em').style('color: #FF9800; margin-bottom: 0.5em;')
                ui.label('You must be logged in to view this page.').style('color: #666; font-size: 1.2em; margin-bottom: 1em;')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return
        
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.card().style('padding: 2em; text-align: center;'):
                ui.icon('error', size='3em').style('color: #f44336; margin-bottom: 0.5em;')
                ui.label('User not found in the database.').style('color: #666; font-size: 1.2em;')
            return

        tournaments = await Tournament.filter(is_active=True)
        user_tournaments = await TournamentPlayers.filter(user=user)
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        # Personal Information Section
        with ui.card().style('width: 100%; margin-bottom: 1.5em; padding: 1.5em;'):
            ui.label('Personal Information').style('font-size: 1.5em; font-weight: bold; margin-bottom: 1em; color: #1976d2;')
            
            with ui.grid(columns=2).style('width: 100%; gap: 1em;'):
                display_name_hint = f"Default: {user.username}" if not user.display_name else ""
                with ui.column():
                    ui.label('Display Name').style('font-weight: 500; margin-bottom: 0.3em; color: #666;')
                    display_name_input = ui.input(
                        '', 
                        value=user.display_name or '', 
                        placeholder=display_name_hint
                    ).style('width: 100%;').props('outlined dense')
                
                with ui.column():
                    ui.label('Pronouns').style('font-weight: 500; margin-bottom: 0.3em; color: #666;')
                    pronouns_input = ui.input(
                        '', 
                        value=user.pronouns or '', 
                        placeholder='e.g. they/them'
                    ).style('width: 100%;').props('outlined dense')
        
        tournament_checkboxes = {}
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]

        def render_tournament_grid(tournament_list, label, icon, columns=4):
            if not tournament_list:
                return
                
            with ui.card().style('width: 100%; margin-bottom: 1.5em; padding: 1.5em;'):
                with ui.row().style('align-items: center; margin-bottom: 1em;'):
                    ui.icon(icon, size='sm').style('color: #1976d2; margin-right: 0.5em;')
                    ui.label(label).style('font-size: 1.5em; font-weight: bold; color: #1976d2;')
                
                rows = [tournament_list[i:i+columns] for i in range(0, len(tournament_list), columns)]
                for row in rows:
                    with ui.row().style('width: 100%; gap: 1em; margin-bottom: 0.5em;'):
                        for t in row:
                            checked = t.id in selected_tournament_ids
                            with ui.column().style('flex: 1; min-width: 0;'):
                                tournament_checkboxes[t.id] = ui.checkbox(
                                    t.name, 
                                    value=checked
                                ).style('width: 100%;')
                        # Fill empty cells if less than columns
                        for _ in range(columns - len(row)):
                            ui.column().style('flex: 1; min-width: 0;')

        # Tournament Sections
        render_tournament_grid(staff_tournaments, 'Staff Administered Tournaments', 'emoji_events', columns=1)
        render_tournament_grid(player_tournaments, 'Community Tournaments', 'groups', columns=1)

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
            ui.notify('Information updated successfully!', color='positive', icon='check_circle')

        # Save Button
        with ui.row().style('width: 100%; justify-content: flex-end; margin-top: 1em;'):
            ui.button('Save Changes', icon='save', on_click=save_info).props('color=primary size=lg')

