"""Recognising a ``ui.timer`` that outlived the page which created it.

``Timer._run_in_loop`` sleeps for its interval, waits for the client, and only
*then* enters ``self.parent_slot`` — while its own ``_should_stop`` (which does
check ``is_deleted``) is evaluated **inside** that context. A page torn down
during that gap therefore raises out of the ``with`` instead of stopping
quietly, and every navigation away from a board carrying the 5s roll-label tick
(``theme/tables/match.py``) lands in it.

Nobody can act on the result: the page is gone, there is no UI left to notify,
and the timer stops either way. Reported as an unhandled UI exception it buried
real errors in Sentry and made ``scripts/ui_flag_sweep.sh`` fail for merely
visiting pages — which cost a full stash-and-rerun against ``main`` to establish
it was pre-existing rather than a regression.

Its own module rather than a helper inside ``frontend.py`` so a test can import
the predicate without importing the app, which builds a Discord client on the
way in.
"""

import traceback

# Raised by nicegui.element.Element.parent_slot. Matched rather than caught by
# type because NiceGUI raises a bare RuntimeError.
_DELETED_SLOT = 'parent slot of the element has been deleted'

# The frame that raises belongs to nicegui.timer, or a submodule of it
# (nicegui.elements.timer subclasses the base).
_TIMER_MODULE = 'nicegui.timer'


def is_timer_teardown_race(exc: BaseException) -> bool:
    """Whether ``exc`` is the teardown race described above.

    Deliberately narrow — the exact type, the exact message, **and** a NiceGUI
    timer frame in the traceback. An application ``RuntimeError`` that reaches a
    deleted slot is a real bug (something is writing into a page that is gone)
    and must still be reported.
    """
    if not isinstance(exc, RuntimeError):
        return False
    if _DELETED_SLOT not in str(exc):
        return False
    return any(
        frame.f_globals.get('__name__', '').startswith(_TIMER_MODULE)
        for frame, _ in traceback.walk_tb(exc.__traceback__)
    )
