"""The "copy it now, you won't see it again" dialog for a freshly minted credential."""

from nicegui import ui

from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_actions, form_dialog

__all__ = ['show_secret_dialog']


def show_secret_dialog(title: str, secret: str, *, noun: str = 'secret') -> None:
    """Show ``secret`` once, read-only, with a Copy button beside Done.

    ``noun`` names the thing in the warning and the copy toast ("token",
    "signing secret"). The service never returns it again, so this dialog is the
    only place the reader can get it.
    """
    with form_dialog(title, card_classes='dialog-card dialog-card--sm') as dialog:
        with ui.column().classes('q-pa-md gap-2 full-width'):
            ui.label(f"Copy this {noun} now. You won't be able to see it again.") \
                .classes('text-warning')
            ui.input(value=secret).props('readonly outlined dense') \
                .classes('input-full-width font-mono')
        with dialog_actions().classes('justify-end'):
            ui.button(
                'Copy', icon='content_copy',
                on_click=lambda: copy_to_clipboard(secret, noun[:1].upper() + noun[1:]),
            ).props('flat')
            ui.button('Done', on_click=dialog.close).props('color=primary')
    dialog.open()
