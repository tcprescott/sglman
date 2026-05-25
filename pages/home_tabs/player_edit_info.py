"""Player Edit Info Tab - Allows players to edit their personal information and tournament registrations."""

from nicegui import app, ui

from application.services import UserService
from models import User


async def render_edit_info_tab():
    """Render the edit info tab for players to update their information."""
    # Initialize service
    user_service = UserService()

    # Install a beforeunload guard so unsaved edits prompt before navigation.
    ui.add_head_html("""
    <script>
      if (!window.__sglman_dirty_guard_installed) {
        window.__sglman_dirty_guard_installed = true;
        window.sglman_dirty = false;
        window.addEventListener('beforeunload', (e) => {
          if (window.sglman_dirty) {
            e.preventDefault();
            e.returnValue = '';
          }
        });
      }
    </script>
    """)

    def mark_dirty():
        ui.run_javascript('window.sglman_dirty = true;')

    def mark_clean():
        ui.run_javascript('window.sglman_dirty = false;')
    
    with ui.column().classes('page-container-narrow'):
        # Header
        with ui.row().classes('header-row'):
            ui.label('Edit Your Information').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.card().classes('card-centered'):
                ui.icon('lock', size='3em').classes('icon-large')
                ui.label('You must be logged in to view this page.').classes('text-muted')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return
        
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.card().classes('card-centered'):
                ui.icon('error', size='3em').classes('icon-error')
                ui.label('User not found in the database.').classes('text-italic')
            return

        # Get tournaments and user registrations from service
        tournament_data = await user_service.get_active_tournaments_categorized()
        user_tournaments = await user_service.get_user_tournament_registrations(user)
        
        tournaments = tournament_data['all_tournaments']
        staff_tournaments = tournament_data['staff_tournaments']
        player_tournaments = tournament_data['player_tournaments']
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        # Personal Information Section
        with ui.card().classes('card-full-width'):
            ui.label('Personal Information').classes('section-title')
            
            with ui.grid(columns=2).classes('form-grid'):
                display_name_hint = f"Default: {user.username}" if not user.display_name else ""
                with ui.column():
                    ui.label('Display Name').classes('input-label')
                    display_name_input = ui.input(
                        '',
                        value=user.display_name or '',
                        placeholder=display_name_hint,
                        on_change=lambda _: mark_dirty(),
                    ).classes('input-full-width').props('outlined dense')

                with ui.column():
                    ui.label('Pronouns').classes('input-label')
                    pronouns_input = ui.input(
                        '',
                        value=user.pronouns or '',
                        placeholder='e.g. they/them',
                        on_change=lambda _: mark_dirty(),
                    ).classes('input-full-width').props('outlined dense')

        with ui.card().classes('card-full-width'):
            ui.label('Notifications').classes('section-title')
            dm_checkbox = ui.checkbox(
                'Receive Discord DM notifications for match updates',
                value=user.dm_notifications,
                on_change=lambda _: mark_dirty(),
            )

        tournament_checkboxes = {}
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]

        def render_tournament_grid(tournament_list, label, icon, columns=4):
            if not tournament_list:
                return
                
            with ui.card().classes('card-full-width'):
                with ui.row().classes('row-centered'):
                    ui.icon(icon, size='sm').classes('icon-primary')
                    ui.label(label).classes('section-title')
                
                rows = [tournament_list[i:i+columns] for i in range(0, len(tournament_list), columns)]
                for row in rows:
                    with ui.row().classes('row-spacing'):
                        for t in row:
                            checked = t.id in selected_tournament_ids
                            with ui.column().classes('flex-1'):
                                tournament_checkboxes[t.id] = ui.checkbox(
                                    t.name,
                                    value=checked,
                                    on_change=lambda _: mark_dirty(),
                                ).classes('input-full-width')
                        # Fill empty cells if less than columns
                        for _ in range(columns - len(row)):
                            ui.column().classes('flex-1')

        # Tournament Sections
        render_tournament_grid(staff_tournaments, 'Staff Administered Tournaments', 'emoji_events', columns=1)
        render_tournament_grid(player_tournaments, 'Community Tournaments', 'groups', columns=1)

        async def save_info():
            await user_service.update_user_personal_info(
                user=user,
                actor=user,
                display_name=display_name_input.value,
                pronouns=pronouns_input.value,
                dm_notifications=dm_checkbox.value,
            )

            selected_ids = set(tid for tid, cb in tournament_checkboxes.items() if cb.value)
            await user_service.update_user_tournament_registrations(
                user=user,
                actor=user,
                selected_tournament_ids=selected_ids,
                current_registrations=user_tournaments,
            )

            mark_clean()
            ui.notify('Information updated successfully!', color='positive', icon='check_circle')

        # Save Button
        with ui.row().classes('button-row'):
            ui.button('Save Changes', icon='save', on_click=save_info).props('color=primary size=lg')
