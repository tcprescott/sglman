from nicegui import app, ui

from application.services import get_user_from_discord_id
from models import Match
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet, submit_on_enter
from theme.dialog.match_dialog import BaseMatchDialog


class StreamRoomDialog(BaseMatchDialog):
    def __init__(self, match: Match, on_submit=None):
        super().__init__(match=match, on_submit=on_submit)

    async def open(self):
        stream_rooms = await self.stream_room_repository.get_all()
        default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header('Assign Stage', dialog)
            with ui.column().classes('q-pa-md'):
                stream_room_options = {None: '(None)'}
                stream_room_options.update({s.id: s.name for s in stream_rooms})
                selected_stream_room = ui.select(
                    label='Stage', options=stream_room_options, value=default_stream_room, with_input=True)
                stream_candidate_checkbox = ui.checkbox(
                    'Stream candidate',
                    value=self.match.is_stream_candidate,
                )

            async def submit():
                stream_room_id = selected_stream_room.value
                try:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    await self.match_service.assign_stage(
                        self.match.id, stream_room_id if stream_room_id else None, actor=actor,
                    )
                    if stream_candidate_checkbox.value != self.match.is_stream_candidate:
                        await self.match_service.set_stream_candidate(
                            self.match.id, stream_candidate_checkbox.value, actor=actor,
                        )
                    with self.dialog:
                        ui.notify('Stage updated.', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error updating stage: {str(e)}', color='negative')

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit).props('color=primary')

            submit_on_enter(dialog, submit)
            dialog.open()
