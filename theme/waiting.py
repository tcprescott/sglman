"""The shared waiting panel — a spinner with a cat fact under it.

Used wherever someone is sitting in front of a blank screen waiting on work the
app cannot make faster: the OAuth round trip, a deferred tab build, a report
re-render. The fact is the same easter egg the empty states and the 404 page
carry, on the theory that a wait with something to read is a shorter wait.
"""

from nicegui import ui

from application.utils.easter_eggs import random_cat_fact

__all__ = ['waiting_panel']


def waiting_panel(message: str = 'Loading…', *, size: str = 'lg') -> ui.element:
    """Render a centered spinner, a message, and a cat fact.

    Returns the panel element so a caller that owns the wait can remove it when
    the work lands (``container.remove(panel)``).
    """
    with ui.column().classes('wiz-waiting items-center') as panel:
        ui.spinner(size=size)
        ui.label(message).classes('wiz-waiting-message')
        with ui.row().classes('empty-state-fact items-center'):
            ui.icon('pets').props('size=xs')
            ui.label(random_cat_fact())
    return panel
