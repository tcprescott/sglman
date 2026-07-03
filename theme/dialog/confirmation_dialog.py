from nicegui import ui

from theme.dialog._helpers import dialog_actions, dialog_header


class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm", cancel_text="Cancel"):
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.dialog = None

    def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header('Confirm', dialog)
            with ui.column().classes('q-pa-md'):
                ui.label(self.message)
            with dialog_actions().classes('justify-end'):
                ui.button(self.cancel_text, on_click=dialog.close).props('flat')
                if self.on_confirm:
                    ui.button(self.confirm_text, on_click=self.on_confirm).props('color=negative')
                else:
                    ui.button(self.confirm_text, on_click=dialog.close).props('color=negative')
        dialog.open()
