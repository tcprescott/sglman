"""Pure helpers from the reports presentation layer.

There is no ``tests/pages/`` — report bodies are verified in the browser — but
these two are ordinary functions with no NiceGUI involvement, and both encode a
rule that is easy to get subtly wrong (a count that disagrees with the page it
labels; a URL that carries a hand-built tenant prefix).
"""

from datetime import date

from pages.admin_tabs.links import SCHEDULE, VOL_SCHEDULE, admin_url
from pages.admin_tabs.reports.shared import _page_range_label, reports_url


class TestPageRangeLabel:
    def test_single_page_states_the_plain_count(self):
        assert _page_range_label(12, 1, 50, 'entries') == '12 entries'

    def test_exactly_one_full_page_is_not_a_range(self):
        assert _page_range_label(50, 1, 50, 'entries') == '50 entries'

    def test_first_of_several_pages_says_so(self):
        assert _page_range_label(124, 1, 50, 'entries') == 'Showing 1–50 of 124 entries'

    def test_middle_page(self):
        assert _page_range_label(124, 2, 50, 'entries') == 'Showing 51–100 of 124 entries'

    def test_last_page_is_clamped_to_the_total(self):
        assert _page_range_label(124, 3, 50, 'entries') == 'Showing 101–124 of 124 entries'

    def test_page_past_the_end_does_not_invert(self):
        assert _page_range_label(95, 3, 50, 'entries') == '95 entries — page 3 is past the end'

    def test_thousands_are_grouped(self):
        assert _page_range_label(12345, 2, 50, 'events') == 'Showing 51–100 of 12,345 events'


class TestAdminUrl:
    def test_root_relative_with_no_tenant_prefix(self):
        """NiceGUI prepends the client's path prefix; a hand-built /t/<slug>
        here would double it under path-mode tenancy."""
        assert admin_url(SCHEDULE, match_id=412) == '/admin/schedule?match_id=412'

    def test_absent_params_are_dropped(self):
        assert admin_url(VOL_SCHEDULE, day=None, other='') == '/admin/vol-schedule'

    def test_bare_section(self):
        assert admin_url(SCHEDULE) == '/admin/schedule'

    def test_dates_are_iso_formatted(self):
        assert admin_url('reports', start=date(2026, 1, 2)) == '/admin/reports?start=2026-01-02'

    def test_reports_url_is_admin_url_with_the_report_first(self):
        assert reports_url('crew', tournament_id=3) == '/admin/reports?report=crew&tournament_id=3'

    def test_reports_url_without_a_report_is_the_dashboard(self):
        assert reports_url() == '/admin/reports'
        assert reports_url(start=date(2026, 1, 2)) == '/admin/reports?start=2026-01-02'
