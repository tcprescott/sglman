"""The ``datetime-local`` form-value converters.

Every admin form that edits a stored instant on the viewer's clock goes through
this pair, so a one-sided bug shows up as a time that silently moves by the
zone's offset each time somebody opens and saves the form without touching it.
The round trip is the property worth pinning.
"""

from datetime import datetime, timezone

import pytest

from application.timezone_context import tz_scope
from theme.dialog._helpers import datetime_to_local_input, local_input_to_datetime

KOLKATA = 'Asia/Kolkata'      # +05:30, no DST — catches a half-hour offset
NEW_YORK = 'America/New_York'  # DST, so it has a nonexistent wall clock


def test_a_blank_value_means_no_datetime():
    assert local_input_to_datetime('') is None
    assert local_input_to_datetime(None) is None
    assert local_input_to_datetime('not-a-datetime') is None


def test_no_datetime_prefills_as_blank():
    assert datetime_to_local_input(None) == ''


@pytest.mark.parametrize('zone', [KOLKATA, NEW_YORK, 'UTC'])
def test_a_stored_instant_survives_a_round_trip_through_the_form(zone):
    """Open the form, change nothing, save: the stored instant must not move."""
    stored = datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)
    with tz_scope(zone):
        back = local_input_to_datetime(datetime_to_local_input(stored))
    assert back == stored


def test_a_typed_wall_clock_is_read_on_the_viewers_zone():
    with tz_scope(KOLKATA):
        stored = local_input_to_datetime('2026-06-15T20:00')
    # 20:00 in +05:30 is 14:30 UTC — not 20:00 UTC.
    assert stored == datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)


def test_a_naive_stored_value_is_read_as_utc_rather_than_raising():
    """SQLite hands back naive datetimes where Postgres returns aware ones."""
    with tz_scope('UTC'):
        assert datetime_to_local_input(datetime(2026, 6, 15, 14, 30)) == '2026-06-15T14:30'


def test_a_wall_clock_the_zone_skips_raises_rather_than_moving_an_hour():
    """02:30 on the US spring-forward date does not exist. Accepting it would
    store a time an hour from the one that was typed, with nothing on screen to
    show it had moved — callers surface the error instead."""
    with tz_scope(NEW_YORK):
        with pytest.raises(ValueError):
            local_input_to_datetime('2026-03-08T02:30')
