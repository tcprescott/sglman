from nicegui import ui
from models import Match, StreamRoom
from theme.dialog.match_dialog import MatchDialog

class StreamRoomDialog(MatchDialog):
    def __init__(self, match: Match, on_submit=None):
        super().__init__(match=match, on_submit=on_submit)

    async def open(self):
        stream_rooms = await StreamRoom.all().order_by('name')
        default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            stream_room_options = {None: '(None)'}
            stream_room_options.update({s.id: s.name for s in stream_rooms})
            selected_stream_room = ui.select(
                label='Stage', options=stream_room_options, value=default_stream_room, with_input=True)

            async def submit():
                stream_room_id = selected_stream_room.value
                # Only update stream_room_id, do not touch other columns
                await Match.filter(id=self.match.id).update(stream_room_id=stream_room_id if stream_room_id else None)
                self.match.stream_room_id = stream_room_id if stream_room_id else None
                with self.dialog:
                    ui.notify(f'Stage updated: {stream_room_id}', color='positive')
                    dialog.close()
                if self.on_submit:
                    await self.on_submit(self.match)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Save', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    import asyncio
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
