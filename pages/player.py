
from nicegui import ui, app
from models import Match
from theme.dialog import MatchDialog
import asyncio
from theme.tables.match import MatchTableView

def create() -> None:
    @ui.page('/player')
    async def player_page() -> None:
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return

        with ui.tabs().style('width: 100%; max-width: 900px; margin: 0 auto;') as panels:
            ui.tab('Schedule')
            ui.tab('Edit Info')
        with ui.tab_panels(panels, value='Schedule'):
            with ui.tab_panel('Schedule'):
                render_player_dashboard(discord_id)

            with ui.tab_panel('Edit Info'):
                await render_edit_info_tab(discord_id)

    def render_player_dashboard(discord_id):
        ui.label('Your Schedule').style('font-size: 2em; margin-bottom: 1em;')

        with ui.column().style('width: 100%;'):
            columns = [
                {'name': 'id', 'label': 'ID', 'field': 'id'},
                {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                {'name': 'seated', 'label': 'Seated', 'field': 'seated'},
                {'name': 'players', 'label': 'Players', 'field': 'players'},
                {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            ]

            async def submit_match():
                dialog = MatchDialog(discord_id=discord_id)
                await dialog.open()
            def get_query():
                return Match.filter(players__user__discord_id=discord_id)
            table_view = MatchTableView(
                columns=columns,
                get_query=get_query,
                admin_controls=False,
                submit_match_callback=submit_match
            )
            asyncio.create_task(table_view.refresh())


    async def render_edit_info_tab(discord_id):
        ui.label('Edit Your Information').style('font-size: 2em; margin-bottom: 1em;')
        from models import User, Tournament, TournamentPlayers
        user = await User.get(discord_id=discord_id)
        tournaments = await Tournament.filter(is_active=True)
        user_tournaments = await TournamentPlayers.filter(user=user)
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        display_name_hint = f"(default: {user.username})" if not user.display_name else ""
        display_name_input = ui.input('Display Name', value=user.display_name or '', placeholder=display_name_hint)
        tournament_checkboxes = {}
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]

        ui.label('Player Opt-In Tournaments').style('margin-top: 1em; font-weight: bold;')
        for t in player_tournaments:
            checked = t.id in selected_tournament_ids
            tournament_checkboxes[t.id] = ui.checkbox(t.name, value=checked)

        ui.label('Staff Administered Tournaments').style('margin-top: 1em; font-weight: bold;')
        for t in staff_tournaments:
            checked = t.id in selected_tournament_ids
            tournament_checkboxes[t.id] = ui.checkbox(t.name, value=checked)

        async def save_info():
            user.display_name = display_name_input.value.strip()
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

        ui.button('Save', color='green', on_click=save_info)

