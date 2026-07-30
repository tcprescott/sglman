"""The auto-fill dialog's defaults are the safe reading of availability.

Only the policy builder is tested: it is module-level precisely so the two
defaults that decide whether a run can repeat the audit's 16-hour draft can be
asserted without a slot context.
"""

from application.services.volunteer.volunteer_autoschedule_service import DEFAULT_MAX_HOURS
from theme.dialog.volunteer_autofill_dialog import build_policy


def test_untouched_dialog_keeps_the_conservative_defaults():
    policy = build_policy(DEFAULT_MAX_HOURS, False)
    assert policy.max_hours == DEFAULT_MAX_HOURS
    assert policy.fill_outside_availability is False


def test_blank_hours_means_no_ceiling():
    assert build_policy('', False).max_hours == 0.0
    assert build_policy(None, False).max_hours == 0.0


def test_checkbox_opts_into_filling_outside_availability():
    assert build_policy(8, True).fill_outside_availability is True


def test_junk_hours_falls_back_to_the_default_rather_than_no_limit():
    assert build_policy('eight', False).max_hours == DEFAULT_MAX_HOURS


def test_negative_hours_is_clamped():
    assert build_policy(-4, False).max_hours == 0.0
