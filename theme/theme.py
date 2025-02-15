from contextlib import contextmanager

from .menu import menu
from .message import message

from nicegui import ui


@contextmanager
def frame(navigation_title: str):
    """Custom page frame to share the same styling and behavior across all pages"""
    ui.page_title(navigation_title)
    ui.colors(primary='#6E93D6', secondary='#53B689', accent='#111B1E', positive='#53B689')
    with ui.header():
        ui.label('SGLive Tournament Manager').classes('font-bold')
        ui.space()
        ui.label(navigation_title)
        # ui.space()
        # with ui.row():
        #     menu()
    with ui.column().classes('absolute-center items-center'):
        yield