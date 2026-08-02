"""The edit dialog must describe the match it is editing.

Three of its statements were wrong or missing, and all three were found by
opening the dialog on one real match — Finished, flagged for review, with a
winner recorded and two players. It showed none of those four facts, offered
five unlabelled arming buttons, and said "No players assigned."

These are pure-string tests against the helpers the dialog renders from; the
NiceGUI layer around them has no coverage by design (see current-state.md), so
the copy has to be testable without it.
"""

import inspect

import pytest

from theme.dialog.match_dialog_base import (
    BaseMatchDialog,
    acknowledgment_empty_state,
)


class TestAcknowledgmentEmptyState:
    """F5: the copy described the wrong absence."""

    def test_no_players_says_so(self):
        assert acknowledgment_empty_state(0, sg_sourced=False) == 'No players assigned yet.'

    def test_players_without_rows_does_not_claim_nobody_is_assigned(self):
        text = acknowledgment_empty_state(2, sg_sourced=False)
        assert 'No players assigned' not in text
        assert '2 players are assigned' in text
        assert 'acknowledgment rows' in text

    def test_one_player_reads_as_singular(self):
        assert '1 player is assigned' in acknowledgment_empty_state(1, sg_sourced=False)

    def test_a_sourced_match_names_the_cause(self):
        """This state is reachable almost only through the SpeedGaming sync."""
        text = acknowledgment_empty_state(2, sg_sourced=True)
        assert 'SpeedGaming' in text

    def test_an_unsourced_match_does_not_blame_speedgaming(self):
        assert 'SpeedGaming' not in acknowledgment_empty_state(2, sg_sourced=False)


class TestClearSummary:
    """F6: arming five lifecycle-clear buttons produced no summary at all."""

    def test_nothing_armed_says_nothing(self):
        assert BaseMatchDialog._clear_summary({}) == ''
        assert BaseMatchDialog._clear_summary({'Check In': False}) == ''

    def test_one_armed_step_is_named(self):
        assert BaseMatchDialog._clear_summary(
            {'Check In': True}) == 'Save will undo: Check In.'

    def test_two_armed_steps_read_as_a_sentence(self):
        assert BaseMatchDialog._clear_summary(
            {'Check In': True, 'Started': True},
        ) == 'Save will undo: Check In and Started.'

    def test_three_armed_steps_keep_the_serial_comma_shape(self):
        assert BaseMatchDialog._clear_summary(
            {'Check In': True, 'Started': True, 'Finish': True},
        ) == 'Save will undo: Check In, Started and Finish.'

    def test_un_arming_removes_the_step_from_the_sentence(self):
        """The whole point: the buttons used to be one-way."""
        assert BaseMatchDialog._clear_summary(
            {'Check In': True, 'Started': False},
        ) == 'Save will undo: Check In.'


def test_the_clear_buttons_toggle_rather_than_disable_themselves():
    """A one-way arm meant closing the dialog — and losing every other edit —
    was the only way to change your mind."""
    src = inspect.getsource(BaseMatchDialog._render_clear_buttons)
    assert 'btn.disable()' in src, 'a step the match never reached stays disabled'
    # The arming path itself must not disable; it flips a flag both ways.
    toggle = src[src.index('def toggle():'):src.index('btn = ui.button')]
    assert 'disable()' not in toggle
    assert 'not getattr(self, attr_flag)' in toggle


def test_the_rewind_group_says_what_it_does():
    src = inspect.getsource(BaseMatchDialog._render_clear_buttons)
    assert 'Rewind the lifecycle' in src
    assert 'undone when you press Save' in src


class TestStateSummary:
    """RC2: the dialog read none of the match's own state."""

    def test_it_reads_the_three_facts_that_explain_the_match(self):
        src = inspect.getsource(BaseMatchDialog._render_state_summary)
        for fact in ('resolve(match=self.match)', 'finish_rank', 'needs_review'):
            assert fact in src, f'the state summary never reads {fact}'

    def test_the_dispute_flag_is_text_not_a_tooltip(self):
        """The board hides its explanation behind a hover; repeating that here
        would leave it unreadable on every touch screen."""
        src = inspect.getsource(BaseMatchDialog._render_state_summary)
        flag = src[src.index("'Flagged by the proctor"):]
        assert 'tooltip' not in flag.lower()

    @pytest.mark.parametrize('tone', [
        'neutral', 'info', 'imminent', 'live', 'done', 'settled', 'cancelled', 'attention',
    ])
    def test_every_status_tone_maps_to_a_chip(self, tone):
        """A missing tone would silently fall back to neutral, so a Live match
        and a Cancelled one would render identically."""
        from application.services.match.match_status import STATUS_TONES
        from theme.dialog.match_dialog_base import _TONE_CHIP

        assert tone in _TONE_CHIP
        assert set(STATUS_TONES.values()) <= set(_TONE_CHIP)
