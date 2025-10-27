"""Dialog for editing StreamRoom details"""

import asyncio

from nicegui import ui

from application.services import StreamRoomService
from models import StreamRoom


class StreamRoomEditDialog:
    def __init__(self, stream_room: StreamRoom = None, on_submit=None):
        self.stream_room = stream_room
        self.on_submit = on_submit
        self.dialog = None
        self.stream_room_service = StreamRoomService()

    async def open(self):
        # Pre-fill values for edit mode
        if self.stream_room:
            default_name = self.stream_room.name
            default_url = self.stream_room.stream_url or ''
            default_is_active = self.stream_room.is_active
        else:
            default_name = ''
            default_url = ''
            default_is_active = True

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            ui.label('Edit Stream Room' if self.stream_room else 'Add Stream Room').style(
                'font-size: 1.5em; font-weight: bold; margin-bottom: 1em;'
            )

            name_input = ui.input('Room Name', value=default_name).style('width: 100%;')
            url_input = ui.input('Stream URL', value=default_url).style('width: 100%;')
            is_active_checkbox = ui.checkbox('Active', value=default_is_active)

            async def submit():
                name = name_input.value.strip()
                url = url_input.value.strip()
                is_active = is_active_checkbox.value

                try:
                    if self.stream_room:
                        # Update existing stream room
                        result_room = await self.stream_room_service.update_stream_room(
                            self.stream_room,
                            name=name,
                            stream_url=url if url else None,
                            is_active=is_active
                        )
                        with self.dialog:
                            ui.notify(f'Stream room "{name}" updated successfully.', color='positive')
                    else:
                        # Create new stream room
                        result_room = await self.stream_room_service.create_stream_room(
                            name=name,
                            stream_url=url if url else None,
                            is_active=is_active
                        )
                        with self.dialog:
                            ui.notify(f'Stream room "{name}" created successfully.', color='positive')

                    dialog.close()
                    if self.on_submit:
                        await self.on_submit(result_room)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Save', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
