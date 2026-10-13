"""Which attendance buttons a community event shows the viewer.

``attendance_controls`` is pure so it can be checked without a NiceGUI client.
The case it exists for: someone who asked for a reminder before the host turned
RSVPs on. They hold a plain subscription, and with only an RSVP button they had
no way to switch that reminder off.
"""

from types import SimpleNamespace

from pages.community_events import attendance_controls


def event(rsvp_enabled: bool):
    return SimpleNamespace(id=7, rsvp_enabled=rsvp_enabled)


def state(subscribed=(), going=()):
    return {'subscribed': set(subscribed), 'going': set(going), 'counts': {}, 'going_counts': {}}


def test_without_rsvps_it_is_the_reminder_toggle():
    assert attendance_controls(event(False), state()) == ('reminder',)
    assert attendance_controls(event(False), state(subscribed={7}, going={7})) == ('reminder',)


def test_with_rsvps_it_is_the_rsvp_button():
    assert attendance_controls(event(True), state()) == ('rsvp',)


def test_someone_going_gets_only_the_rsvp_button():
    assert attendance_controls(event(True), state(subscribed={7}, going={7})) == ('rsvp',)


def test_an_earlier_reminder_subscriber_keeps_the_toggle_to_switch_it_off():
    assert attendance_controls(event(True), state(subscribed={7})) == ('rsvp', 'reminder')
