from nicegui import background_tasks, ui

from application.services import current_user_from_storage
from models import Match
from theme.dialog.match_dialog import BaseMatchDialog


class StreamRoomDialog(BaseMatchDialog):
    def __init__(self, match: Match, on_submit=None):
        super().__init__(match=match, on_submit=on_submit)

    async def open(self):
        stream_rooms = await self.stream_room_repository.get_all()
        default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            with ui.row().classes('items-center q-pa-sm'):
                ui.label('Assign Stage').classes('text-h6 q-ma-none')
                ui.space()
                ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
            ui.separator()
            with ui.column().classes('q-pa-md'):
                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(
                    label='Stage', options=stream_room_options, value=default_stream_room, with_input=True)

            async def submit():
                stream_room_id = selected_stream_room.value
                try:
                    actor = await current_user_from_storage()
                    await self.match_service.assign_stage(
                        self.match.id, stream_room_id if stream_room_id else None, actor=actor,
                    )
                    with self.dialog:
                        ui.notify(f'Stage updated.', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error updating stage: {str(e)}', color='negative')

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit).props('color=primary')

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    background_tasks.create(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
