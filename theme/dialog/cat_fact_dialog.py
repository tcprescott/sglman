from nicegui import ui

from application.utils.easter_eggs import random_cat_fact
from theme.dialog._helpers import dialog_actions, dialog_header


class CatFactDialog:
    """A hidden easter-egg dialog that serves up a random cat fact."""

    def __init__(self):
        self.dialog = None
        self._fact_label = None

    def _reroll(self) -> None:
        if self._fact_label is not None:
            self._fact_label.set_text(random_cat_fact())

    def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            dialog_header('🐱 Cat fact', dialog)
            with ui.column().classes('q-pa-md items-center'):
                ui.icon('pets').props('size=lg')
                self._fact_label = ui.label(random_cat_fact()).classes('text-center')
            with dialog_actions().classes('justify-end'):
                ui.button('Meow another', icon='refresh', on_click=self._reroll).props('flat')
                ui.button('Close', on_click=dialog.close).props('color=primary')
        dialog.open()
