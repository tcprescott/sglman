import asyncio

from nicegui import ui


class SendMessageDialog:
    def __init__(self, user, send_callback=None):
        self.user = user
        self.send_callback = send_callback if send_callback else self.send_message
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            message_input = ui.textarea(label='Message', placeholder='Enter message to send...').style('width: 100%')

            async def send_message():
                with self.dialog:
                    await self.send_callback(self.user, message_input.value)
                    with self.dialog:
                        await self.send_callback(self.user, message_input.value)
                        ui.notify('Message sent.', color='positive')
                        dialog.close()
            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Send', color='green', on_click=send_message)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(send_message())
            dialog.on('keydown', on_keydown)
            dialog.open()

    async def send_message(self, user, message):
        print(f"Send message to {user.username} ({user.id}): {message}")
