from nicegui import ui

from theme.dialog._helpers import dialog_actions, dialog_header


class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm",
                 cancel_text="Cancel", tone: str = "negative", title: str = "Confirm"):
        # ``tone`` defaults to negative because most callers confirm a delete;
        # a non-destructive action (start/confirm a match) opts into 'primary'.
        # ``title`` names what is being confirmed — a bare "Confirm" over a body
        # that also starts with "Confirm…" tells the reader nothing.
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.tone = tone
        self.title = title
        self.dialog = None

    def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header(self.title, dialog)
            with ui.column().classes('q-pa-md'):
                # pre-line, because callers have always written these messages as
                # paragraphs with '\n\n' and a plain label collapsed every one of
                # them onto a single line.
                ui.label(self.message).style('white-space: pre-line')
            with dialog_actions().classes('justify-end'):
                ui.button(self.cancel_text, on_click=dialog.close).props('flat')
                if self.on_confirm:
                    ui.button(self.confirm_text, on_click=self.on_confirm).props(f'color={self.tone}')
                else:
                    ui.button(self.confirm_text, on_click=dialog.close).props(f'color={self.tone}')
        dialog.open()
