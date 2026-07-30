"""Which event day the coordinator's grid opens on.

`tests/theme/` cannot exercise `app.storage.user` without a client, so the
precedence rule is a pure function — mirroring why
`MatchTableView._stored_or_default_states` exists.
"""

from pages.admin_tabs.admin_volunteers import stored_or_default_day

DAYS = ['2026-10-04', '2026-10-05', '2026-10-06']


def test_a_stored_day_in_this_event_wins():
    assert stored_or_default_day('2026-10-06', DAYS, DAYS[0]) == '2026-10-06'


def test_a_stored_day_from_a_previous_event_falls_back():
    assert stored_or_default_day('2025-01-01', DAYS, DAYS[0]) == DAYS[0]


def test_nothing_stored_falls_back():
    assert stored_or_default_day(None, DAYS, DAYS[0]) == DAYS[0]


def test_an_empty_event_window_returns_the_fallback():
    assert stored_or_default_day('2026-10-06', [], '2026-10-04') == '2026-10-04'
