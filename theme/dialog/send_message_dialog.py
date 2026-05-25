from nicegui import background_tasks, ui
from application.services import DiscordService

class SendMessageDialog:
    def __init__(self, user, send_callback=None):
        self.user = user
        self.send_callback = send_callback if send_callback else self.send
        self.dialog = None
        self.discord_service = DiscordService()

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog
            message_input = ui.textarea(
                label='Message',
                placeholder='Enter message to send...',
            ).props('required').classes('full-width')
            ui.label('* required').classes('required-legend')

            async def send_message():
                message = (message_input.value or '').strip()
                if not message:
                    with self.dialog:
                        ui.notify('Please enter a message before sending.', color='warning')
                    return
                with self.dialog:
                    await self.send_callback(self.user, message)
                    ui.notify('Message sent.', color='positive')
                    dialog.close()
            with ui.row().classes('justify-between action-row'):
                send_button = ui.button('Send', color='green', on_click=send_message)
                send_button.bind_enabled_from(
                    message_input, 'value',
                    backward=lambda v: bool(v and v.strip()),
                )
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(send_message())
            dialog.on('keydown', on_keydown)
            dialog.open()

    async def send(self, user, message):
        result, msg = await self.discord_service.send_dm(user.discord_id, message)
        if not result:
            ui.notify(f'Failed to send message.  Bot returned error: {msg}', color='negative')
        else:
            ui.notify(f"Send message to {user.username} ({user.id}): {message}", color='positive')
