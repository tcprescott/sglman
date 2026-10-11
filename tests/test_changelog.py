"""The in-app changelog: the shipped file, its parser, and the page's wiring.

The file is the part worth guarding. Entries are written by hand in PRs, so the
tests below are what keep it readable: every heading parses, entries run newest
first without overlapping, and each one covers whole Monday-to-Sunday weeks —
the changelog summarizes a week or more at a time, never a single day.
"""

import inspect
import re
from datetime import date
from itertools import pairwise

import pages.changelog as changelog_page
import pages.help as help_page
import theme.base as base
from application.changelog import parse_changelog, reload_entries
from application.changelog.catalog import CHANGELOG_PATH, ENTRY_HEADING_RE, all_entries
from middleware.auth import protected_routes


def _headings() -> list[str]:
    text = CHANGELOG_PATH.read_text(encoding='utf-8')
    return [line for line in text.splitlines() if line.startswith('## ')]


class TestShippedChangelog:
    def setup_method(self):
        reload_entries()

    def test_every_heading_is_an_entry(self):
        bad = [h for h in _headings() if not ENTRY_HEADING_RE.match(h)]
        assert not bad, f'Entry headings must read "## YYYY-MM-DD/YYYY-MM-DD Title": {bad}'
        assert len(all_entries()) == len(_headings())

    def test_nothing_before_the_first_entry(self):
        text = CHANGELOG_PATH.read_text(encoding='utf-8')
        assert text.startswith('## ')

    def test_file_is_newest_first(self):
        starts = [ENTRY_HEADING_RE.match(h)['start'] for h in _headings()]
        assert starts == sorted(starts, reverse=True)

    def test_entries_cover_whole_weeks(self):
        for entry in all_entries():
            assert entry.start.weekday() == 0, f'{entry.title}: start on a Monday'
            assert entry.end.weekday() == 6, f'{entry.title}: end on a Sunday'

    def test_entries_do_not_overlap(self):
        entries = all_entries()
        for newer, older in pairwise(entries):
            assert older.end < newer.start, f'{older.title} overlaps {newer.title}'

    def test_every_entry_has_a_body(self):
        for entry in all_entries():
            assert entry.blocks, f'{entry.title} has no content'


class TestParser:
    def test_reads_an_entry(self):
        [entry] = parse_changelog('## 2026-10-05/2026-10-11 Check-in\n\n- One\n- Two\n')
        assert entry.start == date(2026, 10, 5)
        assert entry.end == date(2026, 10, 11)
        assert entry.title == 'Check-in'
        assert entry.anchor == '2026-10-05'
        assert [b.kind for b in entry.blocks] == ['bullets']

    def test_sorts_newest_first(self):
        text = '## 2026-01-05/2026-01-11 Older\n\nA\n\n## 2026-02-02/2026-02-08 Newer\n\nB\n'
        assert [e.title for e in parse_changelog(text)] == ['Newer', 'Older']

    def test_skips_a_malformed_heading_instead_of_raising(self):
        text = '## Oct 5 Typo\n\nLost\n\n## 2026-10-05/2026-10-11 Kept\n\nShown\n'
        assert [e.title for e in parse_changelog(text)] == ['Kept']

    def test_skips_an_impossible_or_backwards_interval(self):
        text = '## 2026-02-30/2026-03-01 Bad date\n\nX\n\n## 2026-03-08/2026-03-02 Backwards\n\nY\n'
        assert parse_changelog(text) == []

    def test_period_widens_only_as_far_as_needed(self):
        def period(header: str) -> str:
            return parse_changelog(f'## {header} T\n\nx\n')[0].period

        assert period('2026-10-05/2026-10-11') == 'Oct 5 – 11, 2026'
        assert period('2026-09-28/2026-10-04') == 'Sep 28 – Oct 4, 2026'
        assert period('2025-12-29/2026-01-04') == 'Dec 29, 2025 – Jan 4, 2026'


class TestChangelogPage:
    def test_registers_the_route_as_public(self):
        assert "@public_page('/changelog')" in inspect.getsource(changelog_page.create)

    def test_route_never_joins_protected_routes(self):
        changelog_page.create()
        assert '/changelog' not in protected_routes

    def test_page_tolerates_an_anonymous_visitor(self):
        source = inspect.getsource(changelog_page)
        assert not re.search(r'(?<!storage\.)\buser\.\w', source)

    def test_never_renders_through_markdown(self):
        assert 'ui.markdown' not in inspect.getsource(changelog_page)

    def test_frontend_registers_the_page(self):
        with open('frontend.py', encoding='utf-8') as fh:
            assert 'changelog.create()' in fh.read()

    def test_help_index_links_the_page(self):
        assert "ui.navigate.to('/changelog')" in inspect.getsource(help_page)

    def test_page_links_back_to_help(self):
        assert "'/help'" in inspect.getsource(changelog_page.create)

    def test_stays_out_of_the_drawer(self):
        assert '/changelog' not in inspect.getsource(base)
