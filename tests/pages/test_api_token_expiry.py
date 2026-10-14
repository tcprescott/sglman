from datetime import datetime, timedelta, timezone

from application.timezone_context import tz_scope
from pages.home_tabs.api_tokens_section import DEFAULT_EXPIRY, EXPIRY_CHOICES, expiry_hint


def test_default_is_thirty_days():
    assert EXPIRY_CHOICES[DEFAULT_EXPIRY] == timedelta(days=30)


def test_never_is_the_last_choice_and_has_no_expiry():
    assert list(EXPIRY_CHOICES)[-1] == 'Never'
    assert EXPIRY_CHOICES['Never'] is None
    assert expiry_hint('Never', datetime.now(timezone.utc)) == 'Works until you revoke it.'


def test_hint_shows_the_end_on_the_viewer_clock():
    now = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)
    with tz_scope('America/New_York'):
        assert expiry_hint('8 hours', now) == 'Expires 2026-10-14 07:00 EDT'
