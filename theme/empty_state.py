from nicegui import ui

from application.utils.easter_eggs import random_cat_fact


def empty_state(message: str) -> None:
    """Render a centered empty-state message with a cat fact beneath it."""
    with ui.column().classes('empty-state items-center'):
        ui.label(message)
        with ui.row().classes('empty-state-fact items-center'):
            ui.icon('pets').props('size=xs')
            ui.label(random_cat_fact())
