"""The volunteer's own hours line, and the comp-tier config field.

Both are module-level pure functions precisely so the copy and the validation
can be checked without a slot context or a database.
"""

import pytest

from application.services.volunteer.volunteer_hours import HoursSummary
from pages.admin_tabs.admin_system_config import _validate_comp_tiers
from pages.volunteer_tabs.my_shifts import hours_message


def _summary(hours, cleared=None, next_tier=None):
    return HoursSummary(
        user_id=1, user_name='Vol', hours=hours,
        tier_cleared=cleared, next_tier=next_tier,
    )


class TestHoursMessage:
    def test_no_hours_names_the_first_tier(self):
        assert hours_message(_summary(0, next_tier=8)) == (
            'No shifts on the books yet. 8 hours gets you to the first tier.'
        )

    def test_no_hours_and_no_tiers_stays_quiet_about_them(self):
        assert hours_message(_summary(0)) == 'No shifts on the books yet.'

    def test_below_the_first_tier_gives_the_gap(self):
        assert hours_message(_summary(5, next_tier=8)) == (
            "You're down for 5 hours this event. 3 more reaches 8."
        )

    def test_cleared_tier_is_named_alongside_the_next(self):
        assert hours_message(_summary(9, cleared=8, next_tier=12)) == (
            "You're down for 9 hours this event. You've cleared 8. 3 more reaches 12."
        )

    def test_top_tier_has_nothing_left_to_reach(self):
        assert hours_message(_summary(20, cleared=16)) == (
            "You're down for 20 hours this event. You've cleared 16."
        )

    def test_half_hours_do_not_render_a_trailing_zero(self):
        assert '6.5 hours' in hours_message(_summary(6.5, next_tier=8))


class TestValidateCompTiers:
    def test_blank_stays_blank(self):
        assert _validate_comp_tiers('  ') == ''

    def test_sorts_and_dedupes(self):
        assert _validate_comp_tiers('16, 8, 12, 8') == '8, 12, 16'

    def test_rejects_words(self):
        with pytest.raises(ValueError, match='numbers of hours'):
            _validate_comp_tiers('eight, twelve')

    def test_rejects_negatives(self):
        with pytest.raises(ValueError, match='negative'):
            _validate_comp_tiers('-4')

    def test_zero_is_kept_as_the_off_switch(self):
        assert _validate_comp_tiers('0') == '0'
