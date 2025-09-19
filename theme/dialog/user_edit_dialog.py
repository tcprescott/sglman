from nicegui import ui
from models import User

import asyncio

from theme.dialog.send_message_dialog import SendMessageDialog

class UserDialog:
    def __init__(self, user: User = None, on_submit=None):
        self.user = user
        self.on_submit = on_submit
        self.dialog = None
        self._initial_updated_at = user.updated_at if user else None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props('readonly' if self.user else '')
            display_name_input = ui.input('Display Name', value=self.user.display_name if self.user else '')
            is_active_checkbox = ui.checkbox('Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input('Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None
            permission_select = ui.select(label='Permission', options={0: 'User', 1: 'Tournament Admin', 2: 'Superadmin'}, value=self.user.permission if self.user else 0)

            async def submit():
                if self.user:
                    latest_user = await User.get(id=self.user.id)
                    if latest_user.updated_at != self._initial_updated_at:
                        with self.dialog:
                            ui.notify('This user has been modified by another admin. Please reload and try again.', color='warning')
                        return
                    with self.dialog:
                        self.user.display_name = display_name_input.value
                        self.user.is_active = is_active_checkbox.value
                        self.user.permission = permission_select.value
                        await self.user.save()
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

                    if not username:
                        with self.dialog:
                            ui.notify('Username is required.', color='warning')
                        return
                    new_user = await User.create(
                        username=username,
                        display_name=display_name,
                        is_active=is_active,
                        permission=permission,
                        discord_id=discord_id
                    )
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
