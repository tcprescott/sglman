from typing import Any, Optional

from nicegui import ui

from theme.dialog._helpers import dialog_actions, dialog_header


class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm",
                 cancel_text="Cancel", tone: str = "negative", title: str = "Confirm",
                 require_phrase: Optional[str] = None):
        # ``tone`` defaults to negative because most callers confirm a delete;
        # a non-destructive action (start/confirm a match) opts into 'primary'.
        # ``title`` names what is being confirmed — a bare "Confirm" over a body
        # that also starts with "Confirm…" tells the reader nothing.
        #
        # ``require_phrase`` adds a second gate for the irreversible ones: the
        # confirm button stays disabled until the reader types the phrase back.
        # ``on_confirm`` is then called with what they typed, so the service —
        # which enforces the same phrase and is the only thing that actually
        # gates the write — sees the real input rather than a constant the UI
        # supplied on its behalf.
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.tone = tone
        self.title = title
        self.require_phrase = require_phrase
        # Any: bound to the ui.dialog in open(); callers reach through it to close.
        self.dialog: Any = None

    def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header(self.title, dialog)
            with ui.column().classes('q-pa-md'):
                # pre-line, because callers have always written these messages as
                # paragraphs with '\n\n' and a plain label collapsed every one of
                # them onto a single line.
                ui.label(self.message).style('white-space: pre-line')
                phrase_input = None
                if self.require_phrase:
                    phrase_input = ui.input(
                        f'Type “{self.require_phrase}” to confirm',
                    ).classes('input-full-width').props('autocomplete=off')

            def _typed() -> str:
                return (phrase_input.value or '') if phrase_input else ''

            required = (self.require_phrase or '').lower()

            def _matches(value) -> bool:
                return (value or '').strip().lower() == required

            with dialog_actions().classes('justify-end'):
                ui.button(self.cancel_text, on_click=dialog.close).props('flat')
                if self.on_confirm:
                    confirm_button = ui.button(
                        self.confirm_text,
                        on_click=(
                            (lambda: self.on_confirm(_typed())) if self.require_phrase
                            else self.on_confirm
                        ),
                    ).props(f'color={self.tone}')
                else:
                    confirm_button = ui.button(
                        self.confirm_text, on_click=dialog.close,
                    ).props(f'color={self.tone}')
                if phrase_input is not None:
                    confirm_button.bind_enabled_from(
                        phrase_input, 'value', backward=_matches,
                    )
        dialog.open()
