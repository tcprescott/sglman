import asyncio

from nicegui import ui

from application.repositories import UserRepository, TournamentRepository
from models import User
from theme.dialog.send_message_dialog import SendMessageDialog


class BaseUserDialog:
    """Base class for user dialogs with common functionality."""
    
    def __init__(self, user: User = None, on_submit=None):
        self.user = user
        self.on_submit = on_submit
        self.dialog = None
        self._initial_updated_at = user.updated_at if user else None

    async def _get_tournament_data(self):
        """Fetch tournament data for the user."""
        tournaments = await TournamentRepository.get_all(active_only=True)
        user_tournaments = []
        if self.user:
            user_tournaments = await TournamentRepository.get_enrolled_players_by_user(self.user)
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]
        tournament_options = {str(t.id): t.name for t in tournaments}
        return tournaments, user_tournaments, selected_tournament_ids, tournament_options

    async def _update_tournament_enrollments(self, tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect):
        """Update tournament enrollments for the user."""
        selected_ids = set(map(int, tournament_multiselect.value))
        current_ids = set(selected_tournament_ids)
        
        # Remove deselected tournaments
        for tp in user_tournaments:
            if tp.tournament_id not in selected_ids:
                await TournamentRepository.unenroll_player(tp.tournament, self.user)
        
        # Add newly selected tournaments
        for tid in selected_ids:
            if tid not in current_ids:
                tournament = next((t for t in tournaments if t.id == tid), None)
                if tournament:
                    await TournamentRepository.enroll_player(tournament, self.user)

    async def _add_tournament_enrollments(self, tournaments, tournament_multiselect, new_user):
        """Add tournament enrollments for a new user."""
        selected_ids = set(map(int, tournament_multiselect.value))
        for tid in selected_ids:
            tournament = next((t for t in tournaments if t.id == tid), None)
            if tournament:
                await TournamentRepository.enroll_player(tournament, new_user)


class UserDialog(BaseUserDialog):
    """Dialog for editing users (non-admin view - tournaments only)."""
    
    async def open(self):
        with ui.dialog() as dialog, ui.card().style('min-width: 700px; max-width: 90vw;'):
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            pronouns_input = ui.input('Pronouns', value=self.user.pronouns if self.user else '')
            is_active_checkbox = ui.checkbox('Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input('Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None
            permission_select = ui.select(label='Permission', options={0: 'User', 1: 'Tournament Admin', 2: 'Superadmin'}, value=self.user.permission if self.user else 0)

            # Tournament multi-select (participation)
            tournaments, user_tournaments, selected_tournament_ids, tournament_options = await self._get_tournament_data()
            tournament_multiselect = ui.select(
                label='Tournaments',
                options=tournament_options,
                value=[str(tid) for tid in selected_tournament_ids],
                multiple=True
            ).props('use-chips')

            async def submit():
                try:
                    if self.user:
                        latest_user = await UserRepository.get_by_id(self.user.id)
                        if latest_user.updated_at != self._initial_updated_at:
                            with self.dialog:
                                ui.notify('This user has been modified by another admin. Please reload and try again.', color='warning')
                            return
                        with self.dialog:
                            await UserRepository.update(
                                self.user,
                                display_name=display_name_input.value,
                                pronouns=pronouns_input.value,
                                is_active=is_active_checkbox.value,
                                permission=permission_select.value
                            )
                            await self._update_tournament_enrollments(
                                tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect
                            )
                            ui.notify('User updated.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(self.user)
                    else:
                        username = username_input.value.strip()
                        display_name = display_name_input.value.strip()
                        is_active = is_active_checkbox.value
                        permission = permission_select.value
                        discord_id = discord_id_input.value if discord_id_input else None
                        pronouns = pronouns_input.value

                        if not username:
                            with self.dialog:
                                ui.notify('Username is required.', color='warning')
                            return
                        
                        new_user = await UserRepository.create(
                            username=username,
                            display_name=display_name,
                            pronouns=pronouns,
                            is_active=is_active,
                            permission=permission,
                            discord_id=discord_id
                        )
                        await self._add_tournament_enrollments(tournaments, tournament_multiselect, new_user)
                        with self.dialog:
                            ui.notify('User created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_user)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            async def open_message_dialog():
                if self.user:
                    dialog_instance = SendMessageDialog(self.user)
                    await dialog_instance.open()

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.user:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Send Message', color='primary', on_click=open_message_dialog)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class AdminUserDialog(BaseUserDialog):
    """Dialog for editing users (admin view - includes tournament admin assignments)."""
    
    async def open(self):
        with ui.dialog() as dialog, ui.card().style('min-width: 700px; max-width: 90vw;'):
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            pronouns_input = ui.input('Pronouns', value=self.user.pronouns if self.user else '')
            is_active_checkbox = ui.checkbox('Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input('Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None
            permission_select = ui.select(label='Permission', options={0: 'User', 1: 'Tournament Admin', 2: 'Superadmin'}, value=self.user.permission if self.user else 0)

            # Tournament multi-select (participation)
            tournaments, user_tournaments, selected_tournament_ids, tournament_options = await self._get_tournament_data()
            tournament_multiselect = ui.select(
                label='Tournaments',
                options=tournament_options,
                value=[str(tid) for tid in selected_tournament_ids],
                multiple=True
            ).props('use-chips')

            # Tournament admin multi-select (only if permission >= 1)
            admin_tournament_multiselect = None
            admin_tournament_ids = []
            if self.user and self.user.permission >= 1:
                admin_tournament_ids = [str(t.id) for t in await self.user.admin_tournaments.all()]
                admin_tournament_multiselect = ui.select(
                    label='Admin of Tournaments',
                    options=tournament_options,
                    value=admin_tournament_ids,
                    multiple=True
                ).props('use-chips')
            elif not self.user:
                # For new user, show admin selector if permission is set to >= 1
                def on_permission_change(e):
                    if e.value >= 1:
                        admin_tournament_multiselect.enable()
                    else:
                        admin_tournament_multiselect.disable()
                admin_tournament_multiselect = ui.select(
                    label='Admin of Tournaments',
                    options=tournament_options,
                    value=[],
                    multiple=True
                ).props('use-chips')
                admin_tournament_multiselect.disable()
                permission_select.on('update:model-value', on_permission_change)

            async def submit():
                try:
                    if self.user:
                        latest_user = await UserRepository.get_by_id(self.user.id)
                        if latest_user.updated_at != self._initial_updated_at:
                            with self.dialog:
                                ui.notify('This user has been modified by another admin. Please reload and try again.', color='warning')
                            return
                        with self.dialog:
                            await UserRepository.update(
                                self.user,
                                display_name=display_name_input.value,
                                pronouns=pronouns_input.value,
                                is_active=is_active_checkbox.value,
                                permission=permission_select.value
                            )
                            await self._update_tournament_enrollments(
                                tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect
                            )
                            
                            # Update admin tournaments if permission >= 1
                            if self.user.permission >= 1 and admin_tournament_multiselect:
                                admin_selected_ids = set(map(int, admin_tournament_multiselect.value))
                                current_admin_ids = set(map(int, admin_tournament_ids))
                                # Remove deselected
                                for t in await self.user.admin_tournaments.all():
                                    if t.id not in admin_selected_ids:
                                        await self.user.admin_tournaments.remove(t)
                                # Add newly selected
                                for tid in admin_selected_ids:
                                    if tid not in current_admin_ids:
                                        tournament = next((t for t in tournaments if t.id == tid), None)
                                        if tournament:
                                            await self.user.admin_tournaments.add(tournament)
                            
                            ui.notify('User updated.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(self.user)
                    else:
                        username = username_input.value.strip()
                        display_name = display_name_input.value.strip()
                        is_active = is_active_checkbox.value
                        permission = permission_select.value
                        discord_id = discord_id_input.value if discord_id_input else None
                        pronouns = pronouns_input.value

                        if not username:
                            with self.dialog:
                                ui.notify('Username is required.', color='warning')
                            return
                        
                        new_user = await UserRepository.create(
                            username=username,
                            display_name=display_name,
                            pronouns=pronouns,
                            is_active=is_active,
                            permission=permission,
                            discord_id=discord_id
                        )
                        await self._add_tournament_enrollments(tournaments, tournament_multiselect, new_user)
                        
                        # Add admin tournaments if permission >= 1
                        if permission >= 1 and admin_tournament_multiselect:
                            admin_selected_ids = set(map(int, admin_tournament_multiselect.value))
                            for tid in admin_selected_ids:
                                tournament = next((t for t in tournaments if t.id == tid), None)
                                if tournament:
                                    await new_user.admin_tournaments.add(tournament)
                        
                        with self.dialog:
                            ui.notify('User created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_user)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            async def open_message_dialog():
                if self.user:
                    dialog_instance = SendMessageDialog(self.user)
                    await dialog_instance.open()

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.user:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Send Message', color='primary', on_click=open_message_dialog)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()

