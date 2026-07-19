import html

from nicegui import ui

from application.utils.easter_eggs import random_cat_fact


def empty_state(message: str) -> None:
    """Render a centered empty-state message with a cat fact beneath it."""
    with ui.column().classes('empty-state items-center'):
        ui.label(message)
        with ui.row().classes('empty-state-fact items-center'):
            ui.icon('pets').props('size=xs')
            ui.label(random_cat_fact())


def no_data_slot(message: str = 'Nothing here yet.', icon: str = 'inbox') -> str:
    """Vue template for a Quasar table ``no-data`` slot: the branded empty state
    (icon + message + a cat fact) instead of Quasar's bare "No data available".

    The cat fact is interpolated once at build time. ``message`` is HTML-escaped
    so a caller-supplied string can't inject markup.
    """
    safe_message = html.escape(message)
    safe_fact = html.escape(random_cat_fact())
    safe_icon = html.escape(icon)
    return (
        '<div class="full-width row flex-center empty-state q-py-lg">'
        '<div class="column items-center text-center">'
        f'<q-icon name="{safe_icon}" size="md" class="q-mb-sm wiz-empty-icon"></q-icon>'
        f'<div>{safe_message}</div>'
        '<div class="empty-state-fact row items-center q-mt-sm">'
        '<q-icon name="pets" size="xs" class="q-mr-xs"></q-icon>'
        f'<span>{safe_fact}</span>'
        '</div></div></div>'
    )
