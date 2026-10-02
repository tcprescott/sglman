"""``PageTimer``: a ``ui.timer`` that can't outlive its page.

The race it closes, and the filters that back it up for any timer that doesn't
use it, are described in ``application/utils/timer_teardown.py``.
"""

from nicegui import ui


class PageTimer(ui.timer):
    """A ``ui.timer`` that stops quietly when its page is torn down before it starts.

    The base class waits for the client to connect and then enters its parent
    slot without re-checking deletion; a page closed during that wait leaves a
    dead slot behind and the entry raises. Checking ``is_deleted`` after the
    wait lets the timer's own cleanup run instead. Overrides a private NiceGUI
    hook, so recheck it on upgrade (``tests/test_timer_teardown_filter.py``
    does).
    """

    async def _can_start(self) -> bool:
        return await super()._can_start() and not self.is_deleted
