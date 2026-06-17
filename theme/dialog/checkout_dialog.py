"""Shared equipment checkout flow — borrower picker for managers, self-checkout
for everyone else. Used by the asset detail page and the inventory tables."""

from typing import Awaitable, Callable, Optional

from nicegui import ui

from application.repositories import UserRepository
from application.services import EquipmentService
from models import User
from theme.dialog._helpers import dialog_header


class CheckoutDialog:
    """Borrower-picker checkout dialog (managers/staff check out on behalf of any user)."""

    def __init__(
        self,
        actor: User,
        equipment_id: int,
        on_done: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.actor = actor
        self.equipment_id = equipment_id
        self.on_done = on_done
        self.service = EquipmentService()

    async def open(self) -> None:
        users = await UserRepository.get_all()
        options = {str(u.id): u.preferred_name for u in users}
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            dialog_header('Check out equipment', dialog)
            with ui.column().classes('q-pa-md gap-2 full-width'):
                borrower_select = ui.select(
                    label='Borrower', options=options, value=str(self.actor.id),
                    with_input=True,
                ).classes('full-width')

            async def confirm():
                try:
                    await self.service.checkout(
                        self.actor, self.equipment_id, borrower_id=int(borrower_select.value)
                    )
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')
                    return
                dialog.close()
                ui.notify('Checked out.', color='positive')
                if self.on_done:
                    await self.on_done()

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Check out', on_click=confirm).props('color=primary')
            dialog.open()


async def open_checkout(
    actor: User,
    equipment_id: int,
    *,
    can_manage: bool,
    on_done: Optional[Callable[[], Awaitable[None]]] = None,
) -> None:
    """Check an asset out. Managers/staff get a borrower picker; everyone else
    is checked out to themselves immediately."""
    if can_manage:
        await CheckoutDialog(actor, equipment_id, on_done=on_done).open()
        return
    try:
        await EquipmentService().checkout(actor, equipment_id)
    except (ValueError, PermissionError) as e:
        ui.notify(str(e), color='warning')
        return
    ui.notify('Checked out to you.', color='positive')
    if on_done:
        await on_done()


async def quick_checkin(
    actor: User,
    equipment_id: int,
    on_done: Optional[Callable[[], Awaitable[None]]] = None,
) -> None:
    """Check an asset back in (manager/staff only — enforced by the service)."""
    try:
        await EquipmentService().checkin(actor, equipment_id)
    except (ValueError, PermissionError) as e:
        ui.notify(str(e), color='warning')
        return
    ui.notify('Checked in.', color='positive')
    if on_done:
        await on_done()
