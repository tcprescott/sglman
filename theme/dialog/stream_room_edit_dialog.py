"""Dialog for editing StreamRoom details"""

from nicegui import background_tasks, ui

from application.services import StreamRoomService, current_user_from_storage
from models import StreamRoom


class StreamRoomEditDialog:
    def __init__(self, stream_room: StreamRoom = None, on_submit=None):
        self.stream_room = stream_room
        self.on_submit = on_submit
        self.dialog = None
        self.stream_room_service = StreamRoomService()

    async def open(self):
        if self.stream_room:
            default_name = self.stream_room.name
            default_url = self.stream_room.stream_url or ''
            default_is_active = self.stream_room.is_active
            title = 'Edit Stream Room'
        else:
            default_name = ''
            default_url = ''
            default_is_active = True
            title = 'Add Stream Room'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            with ui.row().classes('items-center q-pa-sm'):
                ui.label(title).classes('text-h6 q-ma-none')
                ui.space()
                ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
            ui.separator()
            with ui.column().classes('q-pa-md gap-2'):
                name_input = ui.input('Room Name', value=default_name).classes('input-full-width')
                url_input = ui.input('Stream URL', value=default_url).classes('input-full-width')
                is_active_checkbox = ui.checkbox('Active', value=default_is_active)

            async def submit():
                name = name_input.value.strip()
                url = url_input.value.strip()
                is_active = is_active_checkbox.value
                try:
                    actor = await current_user_from_storage()
                    if self.stream_room:
                        result_room = await self.stream_room_service.update_stream_room(
                            self.stream_room,
                            name=name,
                            stream_url=url if url else None,
                            is_active=is_active,
                            actor=actor,
                        )
                        with self.dialog:
                            ui.notify(f'Stream room "{name}" updated successfully.', color='positive')
                    else:
                        result_room = await self.stream_room_service.create_stream_room(
                            name=name,
                            stream_url=url if url else None,
                            is_active=is_active,
                            actor=actor,
                        )
                        with self.dialog:
                            ui.notify(f'Stream room "{name}" created successfully.', color='positive')
                    dialog.close()
                    if self.on_submit:
                        await self.on_submit(result_room)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save' if self.stream_room else 'Create', on_click=submit).props('color=primary')

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
