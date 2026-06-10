from nicegui import background_tasks, ui


def dialog_header(title: str, dialog) -> None:
    """Standard dialog header row: title + spacer + close button, then a separator.

    Call inside the dialog's ``ui.card()`` context so it nests correctly.
    """
    with ui.row().classes('items-center q-pa-sm'):
        ui.label(title).classes('text-h6 q-ma-none')
        ui.space()
        ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
    ui.separator()


def submit_on_enter(dialog, make_coro) -> None:
    """Run an async submit handler when Enter is pressed inside the dialog.

    ``make_coro`` is a zero-arg callable returning the coroutine to run.
    """
    def on_keydown(e):
        if e.args and e.args.get('key') == 'Enter':
            background_tasks.create(make_coro())
    dialog.on('keydown', on_keydown)
