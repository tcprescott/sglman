"""Copy a value to the viewer's clipboard and say so."""

import json

from nicegui import ui

__all__ = ['copy_to_clipboard']


def copy_to_clipboard(value: str, label: str) -> None:
    """Write ``value`` to the clipboard and toast ``"<label> copied to clipboard."``.

    Call from a click handler (or inside the client's context): the browser only
    grants the write to a page that has the user's attention.
    """
    ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(value)})')
    ui.notify(f'{label} copied to clipboard.', color='positive', icon='content_copy')
