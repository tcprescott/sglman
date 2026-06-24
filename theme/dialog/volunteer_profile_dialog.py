"""Dialog for a coordinator to view a volunteer's availability and manage qualifications."""

from nicegui import ui

from application.services import current_user_from_storage
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_qualification_service import VolunteerQualificationService
from application.utils.timezone import format_eastern_date, format_eastern_time
from models import User, VolunteerAvailabilityStatus, VolunteerPosition
from theme.dialog._helpers import dialog_header

_STATUS_PROPS = {
    VolunteerAvailabilityStatus.PREFERRED: ('Preferred', 'positive'),
    VolunteerAvailabilityStatus.AVAILABLE: ('Available', 'positive outline'),
    VolunteerAvailabilityStatus.UNAVAILABLE: ('Unavailable', 'negative'),
}


class VolunteerProfileDialog:
    """Shows a volunteer's declared availability and lets the coordinator toggle position qualifications."""

    def __init__(self, user: User, positions: list[VolunteerPosition], on_submit=None):
        self.user = user
        self.positions = positions
        self.on_submit = on_submit

    async def open(self) -> None:
        availability_service = VolunteerAvailabilityService()
        qualification_service = VolunteerQualificationService()

        windows = await availability_service.availability_for(self.user)
        qualified_ids = await qualification_service.get_qualified_position_ids(self.user)

        checkboxes: dict[int, ui.checkbox] = {}

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            dialog_header(self.user.preferred_name, dialog)

            with ui.column().classes('q-pa-md gap-4').style('min-width: 420px; max-width: 560px;'):

                # --- Availability section ---
                ui.label('Availability').classes('text-subtitle2')
                if not windows:
                    ui.label('No availability windows declared.').classes('text-caption text-grey q-ml-sm')
                else:
                    with ui.column().classes('gap-1'):
                        for w in windows:
                            label_text, badge_props = _STATUS_PROPS.get(
                                w.status, (w.status, 'grey'),
                            )
                            date_str = format_eastern_date(w.starts_at)
                            start_str = format_eastern_time(w.starts_at)
                            end_str = format_eastern_time(w.ends_at)
                            with ui.row().classes('items-center gap-2 no-wrap'):
                                ui.badge(label_text).props(f'color={badge_props}')
                                ui.label(f'{date_str}  {start_str}–{end_str} ET').classes('text-caption')
                                if w.note:
                                    ui.label(f'({w.note})').classes('text-caption text-grey')

                ui.separator()

                # --- Qualifications section ---
                ui.label('Qualified Positions').classes('text-subtitle2')
                if not self.positions:
                    ui.label('No active positions configured.').classes('text-caption text-grey q-ml-sm')
                else:
                    with ui.column().classes('gap-1 q-ml-sm'):
                        for position in self.positions:
                            cb = ui.checkbox(position.name, value=(position.id in qualified_ids))
                            if position.description:
                                cb.tooltip(position.description)
                            checkboxes[position.id] = cb

            async def save() -> None:
                actor = await current_user_from_storage()
                selected_ids = [pid for pid, cb in checkboxes.items() if cb.value]
                try:
                    await qualification_service.set_qualifications(actor, self.user, selected_ids)
                    ui.notify(
                        f'Qualifications updated for {self.user.preferred_name}.',
                        color='positive',
                    )
                    dialog.close()
                    if self.on_submit:
                        await self.on_submit()
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                if self.positions:
                    ui.button('Save qualifications', on_click=save).props('color=primary')

        dialog.open()
