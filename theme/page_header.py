"""The one way a page or tab opens: title, optional help/actions, optional lede.

Before this, admin tabs opened with a title row and a divider, home tabs with
no title, and the check-in desk with a bare label, so the same app looked built
by three people. The look is ``.wiz-page-header`` in styles.css.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from nicegui import ui

# Set while a page is rendered as one section of a bigger page (a Settings
# pane holds Appearance and Timezone). The page still calls page_header() the
# same way; it just comes out a level down, so the pane keeps a single title.
_nested: ContextVar[bool] = ContextVar('page_header_nested', default=False)


@contextmanager
def nested_page_headers() -> Iterator[None]:
    """Render every ``page_header`` inside the block as a section heading."""
    token = _nested.set(True)
    try:
        yield
    finally:
        _nested.reset(token)


def page_header(title: str, subtitle: Optional[str] = None) -> ui.row:
    """Render the header and return its title row.

    The row is a container: build help icons, a status chip or right-aligned
    actions inside ``with page_header(...):`` and they sit on the title's line.
    Give an action group ``ui.space()`` before it to push it to the right edge.
    """
    nested = _nested.get()
    with ui.column().classes('wiz-page-header' + (' wiz-page-header--nested' if nested else '')):
        with ui.row().classes('wiz-page-header__row') as row:
            ui.label(title).classes('section-title' if nested else 'page-title')
        if subtitle:
            ui.label(subtitle).classes('wiz-page-header__sub')
    return row
