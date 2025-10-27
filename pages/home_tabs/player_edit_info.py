"""Player Edit Info Tab - Allows players to edit their personal information and tournament registrations."""

from nicegui import app, ui

from application.services import UserService
from models import User


async def render_edit_info_tab():
    """Render the edit info tab for players to update their information."""
    # Initialize service
    user_service = UserService()
    
    with ui.column().style('width: 100%; max-width: 1200px; margin: 0 auto;'):
        # Header
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Edit Your Information').style('font-size: 2em; font-weight: bold;')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
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

        # Get tournaments and user registrations from service
        tournament_data = await user_service.get_active_tournaments_categorized()
        user_tournaments = await user_service.get_user_tournament_registrations(user)
        
        tournaments = tournament_data['all_tournaments']
        staff_tournaments = tournament_data['staff_tournaments']
        player_tournaments = tournament_data['player_tournaments']
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
            # Update personal information using service
            await user_service.update_user_personal_info(
                user=user,
                display_name=display_name_input.value,
                pronouns=pronouns_input.value
            )
            
            # Update tournament registrations using service
            selected_ids = set(tid for tid, cb in tournament_checkboxes.items() if cb.value)
            await user_service.update_user_tournament_registrations(
                user=user,
                selected_tournament_ids=selected_ids,
                current_registrations=user_tournaments
            )
            
            ui.notify('Information updated successfully!', color='positive', icon='check_circle')

        # Save Button
        with ui.row().style('width: 100%; justify-content: flex-end; margin-top: 1em;'):
            ui.button('Save Changes', icon='save', on_click=save_info).props('color=primary size=lg')
