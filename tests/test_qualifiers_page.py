"""Unit tests for the player qualifier page's own helpers and its wiring.

The parser itself is covered by ``tests/test_duration.py``; what is asserted here
is that the page *uses* the shared strict parser rather than carrying a local,
tolerant copy — that local copy is what made ``1:23`` mean 83 seconds, and
reintroducing it is the regression worth a test.
"""

import inspect

import pages.qualifiers as qualifiers_page
from application.utils.duration import format_hms, parse_hms


class TestNoLocalDurationHelpers:
    def test_page_has_no_local_parser_or_formatter(self):
        assert not hasattr(qualifiers_page, '_parse_hms')
        assert not hasattr(qualifiers_page, '_fmt_hms')

    def test_page_uses_the_shared_helpers(self):
        assert qualifiers_page.parse_hms is parse_hms
        assert qualifiers_page.format_hms is format_hms


class TestWords:
    def test_all_three_segments(self):
        assert qualifiers_page._words(5025) == '1 hour, 23 minutes, 45 seconds'

    def test_zero_segments_are_omitted(self):
        assert qualifiers_page._words(45) == '45 seconds'
        assert qualifiers_page._words(3600) == '1 hour'

    def test_singular_and_plural(self):
        assert qualifiers_page._words(3661) == '1 hour, 1 minute, 1 second'
        assert qualifiers_page._words(7322) == '2 hours, 2 minutes, 2 seconds'

    def test_zero(self):
        assert qualifiers_page._words(0) == '0 seconds'


class TestForfeitIsConfirmed:
    def test_the_run_card_routes_forfeit_through_a_confirmation(self):
        source = inspect.getsource(qualifiers_page.create)
        assert 'on_click=_confirm_forfeit' in source
        assert 'ConfirmationDialog(' in source
        assert "title='Forfeit this run?'" in source

    def test_service_errors_go_through_notify_error(self):
        source = inspect.getsource(qualifiers_page.create)
        assert "ui.notify(str(e)" not in source
        assert source.count('notify_error(e)') == 3
