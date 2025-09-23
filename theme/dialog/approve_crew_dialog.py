from nicegui import ui
from typing import Union, Callable, Optional
from models import Tracker, Commentator

class ApproveCrewDialog:
    def __init__(self, crew_member: Union[Tracker, Commentator], crew_type: str, on_approve: Optional[Callable] = None):
        """
        crew_member: instance of Tracker or Commentator
        crew_type: 'tracker' or 'commentator'
        on_approve: optional callback to run after approval
        """
        self.crew_member = crew_member
        self.crew_type = crew_type
        self.on_approve = on_approve
        self.dialog = None

    async def open(self):
        with ui.dialog() as self.dialog:
            with ui.card().style('min-width: 350px; padding: 2em;'):
                ui.label(f"Approve {self.crew_type.capitalize()}").style('font-size: 1.5em; font-weight: bold;')
                ui.label(f"Name: {self.crew_member.user.preferred_name}")
                approved_checkbox = ui.checkbox('Approved', value=self.crew_member.approved)
                async def save():
                    self.crew_member.approved = approved_checkbox.value
                    await self.crew_member.save()
                    ui.notify(f"{self.crew_type.capitalize()} approval updated.", color='positive')
                    if self.on_approve:
                        await self.on_approve()
                    self.dialog.close()
                with ui.row().style('margin-top: 1em;'):
                    ui.button('Save', color='green', on_click=save)
                    ui.button('Cancel', color='grey', on_click=self.dialog.close)
        await self.dialog.open()
