from nicegui import ui


def dialog_header(title: str, dialog) -> None:
    """Standard dialog header row: title + spacer + close button, then a separator.

    Call inside the dialog's ``ui.card()`` context so it nests correctly.
    """
    with ui.row().classes('dialog-header items-center q-pa-sm'):
        ui.label(title).classes('text-h6 q-ma-none')
        ui.space()
        ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
    ui.separator()


def dialog_actions():
    """Sticky bottom action bar for a dialog card, used as a context manager.

    Wrap the dialog's action buttons in ``with dialog_actions():``; the
    ``.dialog-actions`` class pins the row to the bottom of the scrolling card so
    the primary action stays visible without scrolling on mobile sheets.
    """
    return ui.row().classes('dialog-actions items-center gap-2')


def native_date_input(label: str, value: str = '', *, required: bool = False, clearable: bool = False):
    """A native ``type=date`` input (YYYY-MM-DD), so mobile gets the OS date picker.

    Returns the ``ui.input``; read/write its ``.value`` as a ``YYYY-MM-DD`` string.
    Centralizes the props string so the native-picker recipe lives in one place.
    """
    props = 'type=date stack-label'
    if required:
        props += ' required'
    if clearable:
        props += ' clearable'
    return ui.input(label, value=value).props(props)


def native_time_input(label: str, value: str = '', *, required: bool = False):
    """A native ``type=time`` input (HH:MM), so mobile gets the OS time picker."""
    props = 'type=time stack-label'
    if required:
        props += ' required'
    return ui.input(label, value=value).props(props)


def mobile_sheet(dialog) -> None:
    """Make a dialog fill the screen as a maximized sheet on phones (<600px).

    NiceGUI evaluates dynamic props against the global ``Quasar`` object, not
    Vue ``$q``, so the breakpoint must reference ``Quasar.Screen.lt.sm``.
    """
    dialog.props(':maximized="Quasar.Screen.lt.sm"')


def submit_on_enter(dialog, make_coro) -> None:
    """Run an async submit handler when Enter is pressed inside the dialog.

    ``make_coro`` is a zero-arg callable returning the coroutine to run.
    """
    def on_keydown(e):
        if e.args and e.args.get('key') == 'Enter':
            # Return the coroutine so NiceGUI awaits it in the dialog's slot
            # context; a bare background task has no slot and any ui.notify /
            # ui.run_javascript in the submit handler would raise.
            return make_coro()
    dialog.on('keydown', on_keydown)
