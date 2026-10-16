"""The volunteer shift rows on My Schedule: which chip and which button.

Both are pure so they can be asserted without a slot context.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pages.home_tabs.my_volunteer_shifts import primary_action, shift_status

UTC = timezone.utc
NOW = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)


def _assignment(start_in_min, *, acked=False, checked_in=False, late=None, hours=2):
    starts_at = NOW + timedelta(minutes=start_in_min)
    return SimpleNamespace(
        shift=SimpleNamespace(starts_at=starts_at, ends_at=starts_at + timedelta(hours=hours)),
        acknowledged_at=NOW if acked else None,
        checked_in_at=NOW if checked_in else None,
        checked_in_by_id=None,
        late_minutes=late,
        auto_generated=False,
    )


def test_unacknowledged_shift_asks_for_an_ok():
    a = _assignment(24 * 60)
    assert shift_status(a, NOW)[2] == 'Needs your OK'
    assert primary_action(a, NOW) == 'ack'


def test_acknowledged_shift_far_off_has_no_button():
    a = _assignment(24 * 60, acked=True)
    assert shift_status(a, NOW)[2] == 'Acknowledged'
    assert primary_action(a, NOW) is None


def test_check_in_window_offers_im_here_even_unacknowledged():
    a = _assignment(15)
    assert primary_action(a, NOW) == 'arrive'


def test_shift_under_way_reads_on_now():
    a = _assignment(-30, acked=True)
    assert shift_status(a, NOW)[:2] == ('live', 'radio_button_checked')
    assert primary_action(a, NOW) == 'arrive'


def test_arrived_beats_everything():
    a = _assignment(-30, acked=True, checked_in=True, late=10)
    kind, _, text = shift_status(a, NOW)
    assert kind == 'ok' and text.startswith('Arrived')
    assert primary_action(a, NOW) is None


def test_running_late_beats_on_now():
    a = _assignment(-5, acked=True, late=10)
    assert shift_status(a, NOW)[2].startswith('Running late')
