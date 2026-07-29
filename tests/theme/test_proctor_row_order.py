"""The proctor board's row ordering — what needs a proctor next comes first.

``proctor_row_order`` is a pure function over the display-service row dicts, so
it is testable without a DB or a browser. The board's whole premise is that the
top of the table is the work; a regression here is invisible in a screenshot but
puts the current hour back in the middle of three days of rows.
"""

from pages.volunteer_tabs.proctor_station import proctor_row_order


def row(id_, state, ts=None, overdue=False):
    return {'id': id_, 'state': state, 'scheduled_ts': ts, 'is_overdue': overdue}


def ids(rows):
    return [r['id'] for r in proctor_row_order(rows)]


def test_overdue_scheduled_sorts_above_checked_in():
    rows = [
        row(1, 'Checked In', ts=100),
        row(2, 'Scheduled', ts=50, overdue=True),
    ]
    assert ids(rows) == [2, 1]


def test_a_not_yet_due_scheduled_row_sorts_below_started():
    rows = [
        row(1, 'Scheduled', ts=999),
        row(2, 'Started', ts=100),
    ]
    assert ids(rows) == [2, 1]


def test_within_a_bucket_earlier_scheduled_time_wins():
    rows = [
        row(1, 'Started', ts=300),
        row(2, 'Started', ts=100),
        row(3, 'Started', ts=200),
    ]
    assert ids(rows) == [2, 3, 1]


def test_finished_sorts_below_everything_live():
    rows = [
        row(1, 'Finished', ts=1),
        row(2, 'Confirmed', ts=1),
        row(3, 'Scheduled', ts=9999),
        row(4, 'Started', ts=9999),
        row(5, 'Checked In', ts=9999),
    ]
    assert ids(rows) == [5, 4, 3, 1, 2]


def test_missing_scheduled_ts_does_not_raise():
    rows = [row(1, 'Started'), row(2, 'Started', ts=5)]
    assert ids(rows) == [1, 2]


def test_missing_state_is_treated_as_scheduled():
    rows = [{'id': 1}, row(2, 'Checked In', ts=1)]
    assert ids(rows) == [2, 1]


def test_an_unknown_state_falls_into_the_scheduled_bucket():
    rows = [row(1, 'Cancelled', ts=1), row(2, 'Finished', ts=1)]
    assert ids(rows) == [1, 2]


def test_overdue_only_promotes_a_scheduled_row():
    """A started match past its time is in play, not waiting on the proctor."""
    rows = [
        row(1, 'Started', ts=10, overdue=True),
        row(2, 'Checked In', ts=20),
    ]
    assert ids(rows) == [2, 1]
