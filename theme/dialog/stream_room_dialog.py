from nicegui import ui

from application.repositories import StreamRoomRepository, MatchRepository
from models import Match
from theme.dialog.match_dialog import BaseMatchDialog


class StreamRoomDialog(BaseMatchDialog):
    def __init__(self, match: Match, on_submit=None):
        super().__init__(match=match, on_submit=on_submit)
        # Initialize repositories
        self.stream_room_repository = StreamRoomRepository()
        self.match_repository = MatchRepository()

    async def open(self):
        stream_rooms = await self.stream_room_repository.get_all()
        default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog
            stream_room_options = {None: '(None)'}
            stream_room_options.update({s.id: s.name for s in stream_rooms})
            selected_stream_room = ui.select(
                label='Stage', options=stream_room_options, value=default_stream_room, with_input=True)

            async def submit():
                stream_room_id = selected_stream_room.value
                try:
                    # Update using repository
                    await self.match_repository.update(
                        self.match,
                        stream_room_id=stream_room_id if stream_room_id else None
                    )
                    with self.dialog:
                        ui.notify(f'Stage updated: {stream_room_id}', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error updating stage: {str(e)}', color='negative')

            with ui.row().classes('justify-between action-row'):
                ui.button('Save', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    import asyncio
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
