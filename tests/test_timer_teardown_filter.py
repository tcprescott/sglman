"""A `ui.timer` outliving its page is not an error anyone can act on.

`Timer._run_in_loop` sleeps for its interval, waits for the client, and only then
enters `self.parent_slot` — while its own `_should_stop` (which does check
`is_deleted`) is evaluated *inside* that context. Navigating away from any board
carrying the 5s roll-label tick lands in that gap, so the timer raises instead of
stopping quietly.

It was logged as an unhandled UI exception, which buried real errors in Sentry
and made `scripts/ui_flag_sweep.sh` report a failure for merely visiting pages —
costing a full stash-and-rerun against `main` to establish it was pre-existing.

The filter has to stay narrow: an application `RuntimeError` that happens to
reach a deleted slot is a real bug and must still be reported.
"""

import pytest

from theme.timer_teardown import is_timer_teardown_race

MESSAGE = 'The parent slot of the element has been deleted.'


def _raised_in(module_name: str, exc: Exception) -> Exception:
    """Give ``exc`` a traceback whose frame claims to belong to ``module_name``.

    `walk_tb` reads `frame.f_globals['__name__']`, so a function executing with a
    doctored `__name__` global produces a frame indistinguishable from one raised
    inside that module.
    """
    source = compile('raise exc', f'<{module_name}>', 'exec')
    namespace = {'__name__': module_name, 'exc': exc}
    try:
        exec(source, namespace)
    except Exception as raised:
        # Broad on purpose: the caller chooses the exception, and returning it
        # with a real traceback attached is the whole point of this helper.
        return raised
    raise AssertionError('exc was not raised')


class TestItFiltersTheRace:
    def test_a_timer_teardown_is_filtered(self):
        exc = _raised_in('nicegui.timer', RuntimeError(MESSAGE))
        assert is_timer_teardown_race(exc)

    def test_the_elements_timer_submodule_counts_too(self):
        # nicegui.elements.timer subclasses nicegui.timer; the frame that raises
        # can belong to either.
        exc = _raised_in('nicegui.timer.something', RuntimeError(MESSAGE))
        assert is_timer_teardown_race(exc)


class TestItFiltersNothingElse:
    def test_the_same_error_from_application_code_is_reported(self):
        # A deleted slot reached from our own code is a real bug: something is
        # writing into a page that is gone, and we want the traceback.
        exc = _raised_in('pages.home_tabs.event', RuntimeError(MESSAGE))
        assert not is_timer_teardown_race(exc)

    def test_a_different_runtime_error_from_a_timer_is_reported(self):
        exc = _raised_in('nicegui.timer', RuntimeError('database is gone'))
        assert not is_timer_teardown_race(exc)

    @pytest.mark.parametrize('exc_type', [ValueError, KeyError, AttributeError, TypeError])
    def test_other_exception_types_are_reported(self, exc_type):
        exc = _raised_in('nicegui.timer', exc_type(MESSAGE))
        assert not is_timer_teardown_race(exc)

    def test_an_exception_with_no_traceback_is_reported(self):
        assert not is_timer_teardown_race(RuntimeError(MESSAGE))
