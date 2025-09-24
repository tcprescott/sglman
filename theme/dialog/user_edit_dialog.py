import asyncio

from nicegui import ui

from models import User
from theme.dialog.send_message_dialog import SendMessageDialog


class UserDialog:
    def __init__(self, user: User = None, on_submit=None):
        self.user = user
        self.on_submit = on_submit
        self.dialog = None
        self._initial_updated_at = user.updated_at if user else None

    async def open(self):
        from models import Tournament, TournamentPlayers
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            pronouns_input = ui.input('Pronouns', value=self.user.pronouns if self.user else '')
            is_active_checkbox = ui.checkbox('Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input('Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None
            permission_select = ui.select(label='Permission', options={0: 'User', 1: 'Tournament Admin', 2: 'Superadmin'}, value=self.user.permission if self.user else 0)

            # Tournament multi-select
            tournaments = await Tournament.filter(is_active=True)
            user_tournaments = []
            if self.user:
                user_tournaments = await TournamentPlayers.filter(user=self.user)
            selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]
            tournament_options = {str(t.id): t.name for t in tournaments}
            tournament_multiselect = ui.select(
                label='Tournaments',
                options=tournament_options,
                value=[str(tid) for tid in selected_tournament_ids],
                multiple=True
            )

            async def submit():
                if self.user:
                    latest_user = await User.get(id=self.user.id)
                    if latest_user.updated_at != self._initial_updated_at:
                        with self.dialog:
                            ui.notify('This user has been modified by another admin. Please reload and try again.', color='warning')
                        return
                    with self.dialog:
                        self.user.display_name = display_name_input.value
                        self.user.pronouns = pronouns_input.value
                        self.user.is_active = is_active_checkbox.value
                        self.user.permission = permission_select.value
                        await self.user.save()
                        # Update tournaments
                        selected_ids = set(map(int, tournament_multiselect.value))
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
                                    await TournamentPlayers.create(user=self.user, tournament=tournament)
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
                    new_user = await User.create(
                        username=username,
                        display_name=display_name,
                        pronouns=pronouns,
                        is_active=is_active,
                        permission=permission,
                        discord_id=discord_id
                    )
                    # Add tournaments for new user
                    selected_ids = set(map(int, tournament_multiselect.value))
                    for tid in selected_ids:
                        tournament = next((t for t in tournaments if t.id == tid), None)
                        if tournament:
                            await TournamentPlayers.create(user=new_user, tournament=tournament)
                    with self.dialog:
                        ui.notify('User created.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(new_user)

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
