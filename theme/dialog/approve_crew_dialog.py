from typing import Callable, Optional, Union

from nicegui import ui

from models import Commentator, Tracker
from application.services import CrewService, current_user_from_storage


class ApproveCrewDialog:
    def __init__(self, crew_member: Union[Tracker, Commentator], crew_type: str, on_approve: Optional[Callable] = None):
        self.crew_member = crew_member
        self.crew_type = crew_type
        self.on_approve = on_approve
        self.dialog = None
        self.service = CrewService()

    async def open(self):
        with ui.dialog() as self.dialog:
            with ui.card().classes('dialog-card'):
                with ui.row().classes('items-center q-pa-sm'):
                    ui.label(f'Approve {self.crew_type.capitalize()}').classes('text-h6 q-ma-none')
                    ui.space()
                    ui.button(icon='close', on_click=self.dialog.close).props('flat round dense').tooltip('Close')
                ui.separator()
                with ui.column().classes('q-pa-md gap-2'):
                    ui.label(f'Name: {self.crew_member.user.preferred_name}')
                    approved_checkbox = ui.checkbox('Approved', value=self.crew_member.approved)

                async def save():
                    try:
                        actor = await current_user_from_storage()
                        await self.service.update_crew_approval(
                            crew_member=self.crew_member,
                            crew_type=self.crew_type,
                            approved=approved_checkbox.value,
                            actor=actor,
                        )
                        ui.notify(f'{self.crew_type.capitalize()} approval updated.', color='positive')
                        if self.on_approve:
                            await self.on_approve()
                        self.dialog.close()
                    except PermissionError as e:
                        ui.notify(str(e), color='negative')
                    except ValueError as e:
                        ui.notify(f'Error: {str(e)}', color='negative')

                ui.separator()
                with ui.row().classes('justify-end q-pa-sm gap-2'):
                    ui.button('Cancel', on_click=self.dialog.close).props('flat')
                    ui.button('Save', on_click=save).props('color=primary')
        await self.dialog.open()
