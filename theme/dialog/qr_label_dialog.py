"""Pick equipment assets and open a printable sheet of their QR labels.

Opened from the admin Equipment tab's "Print QR labels" button. The manager
ticks the assets to include (all pre-selected), picks a column count, and the
dialog opens ``/equipment/qr-labels`` in a new tab with the chosen ids. The
target is a bare in-app path — ``ui.navigate.to`` prepends the request's
``root_path`` (the ``/t/<slug>`` in path mode, empty on a custom domain), the
same convention the per-asset "Open asset page" links use — so the new tab
stays on the community the manager is already viewing and carries the session.
"""

from nicegui import ui

from application.services import EquipmentService
from models import User
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet


class QrLabelDialog:
    """Select lending assets and open a printable QR-label sheet for them."""

    def __init__(self, actor: User):
        self.actor = actor
        self.service = EquipmentService()
        self.dialog = None
        self._checks: dict[int, ui.checkbox] = {}

    def _set_all(self, value: bool) -> None:
        for cb in self._checks.values():
            cb.value = value

    async def open(self) -> None:
        assets = await self.service.list_assets()

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header('Print QR labels', dialog)

            cols_toggle = None
            with ui.column().classes('q-pa-md gap-2 full-width'):
                if not assets:
                    ui.label('No equipment to print.').classes('italic-note')
                else:
                    ui.label(
                        'Pick the assets to print; each becomes a QR label on an '
                        '8.5×11 sheet you can print from your browser.'
                    ).classes('text-caption')
                    with ui.row().classes('items-center gap-2 full-width'):
                        ui.button('Select all', on_click=lambda: self._set_all(True)).props('flat dense')
                        ui.button('Select none', on_click=lambda: self._set_all(False)).props('flat dense')
                        ui.space()
                        ui.label('Columns').classes('text-caption')
                        cols_toggle = ui.toggle({2: '2', 3: '3', 4: '4'}, value=3).props('dense')
                    with ui.column().classes('gap-1 full-width').style('max-height: 50vh; overflow-y: auto'):
                        for asset in assets:
                            self._checks[asset.id] = ui.checkbox(
                                f'#{asset.asset_number} · {asset.name}', value=True,
                            )

            async def generate() -> None:
                selected = [aid for aid, cb in self._checks.items() if cb.value]
                if not selected:
                    with self.dialog:
                        ui.notify('Select at least one asset.', color='warning')
                    return
                cols = int(cols_toggle.value) if cols_toggle is not None else 3
                ids_csv = ','.join(str(i) for i in selected)

                dialog.close()
                # Bare path: ui.navigate.to prepends the tenant's root_path, so
                # the new tab opens on this community (path or host mode).
                ui.navigate.to(f'/equipment/qr-labels?ids={ids_csv}&cols={cols}', new_tab=True)

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                if assets:
                    ui.button(
                        'Open printable sheet', icon='print', on_click=generate,
                    ).props('color=primary')

            dialog.open()
