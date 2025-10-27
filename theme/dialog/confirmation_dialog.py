from nicegui import ui


class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm", cancel_text="Cancel"):
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.dialog = None

    def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card card-padding'):
            self.dialog = dialog
            ui.label(self.message).classes('mb-1')
            with ui.row().classes('justify-between action-row'):
                if self.on_confirm:
                    ui.button(self.confirm_text, color='negative', on_click=self.on_confirm)
                else:
                    ui.button(self.confirm_text, color='negative', on_click=dialog.close)
                ui.button(self.cancel_text, color='gray', on_click=dialog.close)
        dialog.open()
