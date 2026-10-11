"""The one way a page or tab opens: title, optional help/actions, optional lede.

Before this, admin tabs opened with a title row and a divider, home tabs with
no title, and the check-in desk with a bare label, so the same app looked built
by three people. The look is ``.wiz-page-header`` in styles.css.
"""

from typing import Optional

from nicegui import ui


def page_header(title: str, subtitle: Optional[str] = None) -> ui.row:
    """Render the header and return its title row.

    The row is a container: build help icons, a status chip or right-aligned
    actions inside ``with page_header(...):`` and they sit on the title's line.
    Give an action group ``ui.space()`` before it to push it to the right edge.
    """
    with ui.column().classes('wiz-page-header'):
        with ui.row().classes('wiz-page-header__row') as row:
            ui.label(title).classes('page-title')
        if subtitle:
            ui.label(subtitle).classes('wiz-page-header__sub')
    return row
