from nicegui import background_tasks, ui

from application.repositories import TournamentRepository
from application.services import AuthService, TournamentService, UserService, current_user_from_storage
from models import Role, User
from theme.dialog.send_message_dialog import SendMessageDialog


class BaseUserDialog:
    """Base class for user dialogs with common functionality."""

    def __init__(self, user: User = None, on_submit=None):
        self.user = user
        self.on_submit = on_submit
        self.dialog = None
        self._initial_updated_at = user.updated_at if user else None
        self.user_service = UserService()
        self.tournament_service = TournamentService()

    async def _get_tournament_data(self):
        """Fetch tournament data for the user."""
        tournaments = await TournamentRepository.get_all(active_only=True)
        user_tournaments = []
        if self.user:
            user_tournaments = await TournamentRepository.get_enrolled_players_by_user(self.user)
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]
        tournament_options = {str(t.id): t.name for t in tournaments}
        return tournaments, user_tournaments, selected_tournament_ids, tournament_options

    async def _update_tournament_enrollments(self, tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect, actor):
        selected_ids = set(map(int, tournament_multiselect.value))
        await self.user_service.update_user_tournament_registrations(
            user=self.user,
            actor=actor,
            selected_tournament_ids=selected_ids,
            current_registrations=user_tournaments,
        )

    async def _add_tournament_enrollments(self, tournaments, tournament_multiselect, new_user, actor):
        selected_ids = set(map(int, tournament_multiselect.value))
        if selected_ids:
            await self.user_service.manage_tournament_enrollments(
                user=new_user,
                actor=actor,
                tournament_ids=selected_ids,
                is_update=False,
            )


class UserDialog(BaseUserDialog):
    """Self-edit dialog: profile fields + tournament enrollments. No role editing."""

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            pronouns_input = ui.input('Pronouns', value=self.user.pronouns if self.user else '')

            tournaments, user_tournaments, selected_tournament_ids, tournament_options = await self._get_tournament_data()
            tournament_multiselect = ui.select(
                label='Tournaments',
                options=tournament_options,
                value=[str(tid) for tid in selected_tournament_ids],
                multiple=True,
            ).props('use-chips')

            async def submit():
                if not self.user:
                    with self.dialog:
                        ui.notify('Self-edit dialog requires an existing user.', color='warning')
                    return
                actor = await current_user_from_storage()
                if actor is None:
                    with self.dialog:
                        ui.notify('You must be logged in to edit your profile.', color='negative')
                    return
                try:
                    with self.dialog:
                        await self.user_service.update_user_profile(
                            self.user,
                            display_name=display_name_input.value,
                            pronouns=pronouns_input.value,
                            check_concurrency=True,
                            initial_updated_at=self._initial_updated_at,
                            actor=actor,
                        )
                        await self._update_tournament_enrollments(
                            tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect, actor,
                        )
                        ui.notify('User updated.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.user)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            with ui.row().classes('justify-between action-row'):
                ui.button('Save', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class AdminUserDialog(BaseUserDialog):
    """Staff-edit dialog: profile + active flag + roles + TA/CC tournament assignments."""

    async def open(self):
        actor = await current_user_from_storage()
        if actor is None or not await AuthService.is_staff(actor):
            ui.notify('Only Staff can manage users.', color='negative')
            return

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            pronouns_input = ui.input('Pronouns', value=self.user.pronouns if self.user else '')
            is_active_checkbox = ui.checkbox('Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input('Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None

            role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
            current_roles = []
            if self.user:
                current_roles = [r.value for r in await AuthService.get_roles(self.user)]
            role_select = ui.select(
                label='Roles',
                options=role_options,
                value=list(current_roles),
                multiple=True,
            ).props('use-chips')

            tournaments, user_tournaments, selected_tournament_ids, tournament_options = await self._get_tournament_data()
            tournament_multiselect = ui.select(
                label='Tournaments (Player)',
                options=tournament_options,
                value=[str(tid) for tid in selected_tournament_ids],
                multiple=True,
            ).props('use-chips')

            admin_tournament_ids = []
            if self.user:
                admin_tournament_ids = [str(t.id) for t in await self.user.admin_tournaments.all()]
            admin_tournament_multiselect = ui.select(
                label='Tournament Admin of',
                options=tournament_options,
                value=admin_tournament_ids,
                multiple=True,
            ).props('use-chips')

            cc_tournament_ids = []
            if self.user:
                cc_tournament_ids = [str(t.id) for t in await self.user.crew_coordinated_tournaments.all()]
            cc_tournament_multiselect = ui.select(
                label='Crew Coordinator of',
                options=tournament_options,
                value=cc_tournament_ids,
                multiple=True,
            ).props('use-chips')

            async def sync_role_assignments(target_user):
                desired = set(role_select.value or [])
                current = set(current_roles) if target_user is self.user else set()
                if target_user is not self.user:
                    current = {r.value for r in await AuthService.get_roles(target_user)}
                for added in desired - current:
                    await self.user_service.grant_role(target_user, Role(added), actor=actor)
                for removed in current - desired:
                    await self.user_service.revoke_role(target_user, Role(removed), actor=actor)

            async def sync_tournament_memberships(target_user, multiselect, current_ids_str, add_method, remove_method):
                desired = set(map(int, multiselect.value or []))
                current = set(map(int, current_ids_str))
                tournaments_by_id = {t.id: t for t in tournaments}
                for tid in desired - current:
                    t = tournaments_by_id.get(tid)
                    if t:
                        await add_method(t, target_user, actor=actor)
                for tid in current - desired:
                    t = tournaments_by_id.get(tid)
                    if t:
                        await remove_method(t, target_user, actor=actor)

            async def submit():
                try:
                    if self.user:
                        with self.dialog:
                            await self.user_service.update_user_profile(
                                self.user,
                                display_name=display_name_input.value,
                                pronouns=pronouns_input.value,
                                check_concurrency=True,
                                initial_updated_at=self._initial_updated_at,
                                actor=actor,
                            )
                            await self.user_service.update_user_admin_fields(
                                self.user,
                                is_active=is_active_checkbox.value,
                                actor=actor,
                            )
                            await self._update_tournament_enrollments(
                                tournaments, user_tournaments, selected_tournament_ids, tournament_multiselect, actor,
                            )
                            await sync_role_assignments(self.user)
                            await sync_tournament_memberships(
                                self.user, admin_tournament_multiselect, admin_tournament_ids,
                                self.tournament_service.add_admin, self.tournament_service.remove_admin,
                            )
                            await sync_tournament_memberships(
                                self.user, cc_tournament_multiselect, cc_tournament_ids,
                                self.tournament_service.add_crew_coordinator,
                                self.tournament_service.remove_crew_coordinator,
                            )
                            ui.notify('User updated.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(self.user)
                    else:
                        new_user = await self.user_service.create_user(
                            username=username_input.value,
                            display_name=display_name_input.value,
                            pronouns=pronouns_input.value,
                            is_active=is_active_checkbox.value,
                            discord_id=discord_id_input.value if discord_id_input else None,
                            actor=actor,
                        )
                        await self._add_tournament_enrollments(tournaments, tournament_multiselect, new_user, actor)
                        await sync_role_assignments(new_user)
                        await sync_tournament_memberships(
                            new_user, admin_tournament_multiselect, [],
                            self.tournament_service.add_admin, self.tournament_service.remove_admin,
                        )
                        await sync_tournament_memberships(
                            new_user, cc_tournament_multiselect, [],
                            self.tournament_service.add_crew_coordinator,
                            self.tournament_service.remove_crew_coordinator,
                        )
                        with self.dialog:
                            ui.notify('User created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_user)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            async def open_message_dialog():
                if self.user:
                    dialog_instance = SendMessageDialog(self.user)
                    await dialog_instance.open()

            with ui.row().classes('justify-between action-row'):
                if self.user:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Send Message', color='primary', on_click=open_message_dialog)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
