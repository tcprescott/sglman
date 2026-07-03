"""Dialog for creating/editing a VolunteerPosition."""

from nicegui import app, ui

from application.services import get_user_from_discord_id
from application.services.volunteer_position_service import VolunteerPositionService
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet, submit_on_enter
from models import VolunteerPosition


class VolunteerPositionDialog:
    def __init__(self, position: VolunteerPosition = None, on_submit=None):
        self.position = position
        self.on_submit = on_submit
        self.dialog = None
        self.service = VolunteerPositionService()

    async def open(self):
        editing = self.position is not None
        default_name = self.position.name if editing else ''
        default_desc = (self.position.description or '') if editing else ''
        default_order = self.position.display_order if editing else 0
        default_active = self.position.is_active if editing else True
        default_length = self.position.shift_length_minutes if editing else None
        default_stagger = self.position.stagger_minutes if editing else None
        title = 'Edit Position' if editing else 'Add Position'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(title, dialog)
            with ui.column().classes('q-pa-md gap-2'):
                name_input = ui.input('Position Name', value=default_name).classes('input-full-width')
                desc_input = ui.input('Description', value=default_desc).classes('input-full-width')
                order_input = ui.number('Display Order', value=default_order, format='%d').props('inputmode=numeric').classes('input-full-width')
                active_checkbox = ui.checkbox('Active', value=default_active)
                length_input = ui.number(
                    'Shift length (min)', value=default_length, format='%d',
                ).props('inputmode=numeric').classes('input-full-width')
                stagger_input = ui.number(
                    'Stagger interval (min)', value=default_stagger, format='%d',
                ).props('inputmode=numeric').classes('input-full-width')
                ui.label(
                    'Leave both blank for fixed shared blocks; set both to stagger handoffs.'
                ).classes('text-caption text-grey')

            def _opt_int(value):
                if value is None or value == '':
                    return None
                return int(value)

            async def submit():
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                try:
                    order_value = int(order_input.value or 0)
                    length_value = _opt_int(length_input.value)
                    stagger_value = _opt_int(stagger_input.value)
                    if editing:
                        result = await self.service.update(
                            actor, self.position,
                            name=name_input.value.strip(),
                            description=(desc_input.value or '').strip() or None,
                            display_order=order_value,
                            is_active=active_checkbox.value,
                            shift_length_minutes=length_value,
                            stagger_minutes=stagger_value,
                        )
                    else:
                        result = await self.service.create(
                            actor,
                            name=name_input.value.strip(),
                            description=(desc_input.value or '').strip() or None,
                            display_order=order_value,
                            is_active=active_checkbox.value,
                            shift_length_minutes=length_value,
                            stagger_minutes=stagger_value,
                        )
                    dialog.close()
                    if self.on_submit:
                        await self.on_submit(result)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save' if editing else 'Create', on_click=submit).props('color=primary')

            submit_on_enter(dialog, submit)
            dialog.open()
