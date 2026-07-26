"""The bracket card's live-status rendering contract (U2).

Two halves, both testable without a NiceGUI client: the pure class-selection the
card layer does, and the stylesheet rules those classes rely on. Between them
they pin the thing that made the bracket read as a static document — a card that
said "Scheduled" for a match the schedule was calling "In Progress".
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.services.match.match_status import MatchStatus
from models import BracketMatchState
from theme.brackets.cards import BracketContext, _card_classes

CSS_PATH = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'brackets.css'


@pytest.fixture(scope='module')
def css() -> str:
    return re.sub(r'/\*.*?\*/', '', CSS_PATH.read_text(), flags=re.DOTALL)


def _ctx(live: dict | None = None) -> BracketContext:
    return BracketContext(entry_name={}, live_state=live or {})


def _match(match_id: int = 1, state=BracketMatchState.OPEN):
    return SimpleNamespace(id=match_id, state=state)


class TestCardClasses:
    def test_without_live_state_the_card_is_exactly_what_it_was(self):
        """A caller that didn't resolve live state renders the pre-U2 card."""
        assert _card_classes(_match(), _ctx()) == 'is-open'
        assert _card_classes(
            _match(state=BracketMatchState.PENDING), _ctx(),
        ) == 'is-pending'
        assert _card_classes(
            _match(state=BracketMatchState.COMPLETE), _ctx(),
        ) == 'is-complete'

    @pytest.mark.parametrize('status,expected', [
        (MatchStatus.LIVE, 'is-live'),
        (MatchStatus.CHECKED_IN, 'is-checked-in'),
        (MatchStatus.AWAITING_RESULT, 'is-awaiting-result'),
        (MatchStatus.NEEDS_RESCHEDULE, 'is-needs-reschedule'),
    ])
    def test_a_live_status_overrides_the_matchup_state(self, status, expected):
        ctx = _ctx({1: {'status': status}})
        assert _card_classes(_match(), ctx) == expected

    @pytest.mark.parametrize('status', [
        MatchStatus.SCHEDULED, MatchStatus.UNSCHEDULED,
        MatchStatus.COMPLETE, MatchStatus.PENDING, MatchStatus.CANCELLED,
    ])
    def test_the_quiet_statuses_leave_the_state_class_alone(self, status):
        """These say nothing the matchup state doesn't; a card that shouted about
        every status would stop drawing the eye to the one being played."""
        ctx = _ctx({1: {'status': status}})
        assert _card_classes(_match(), ctx) == 'is-open'

    def test_another_matchups_live_state_is_not_applied(self):
        ctx = _ctx({2: {'status': MatchStatus.LIVE}})
        assert _card_classes(_match(match_id=1), ctx) == 'is-open'


class TestStylesheet:
    @pytest.mark.parametrize('cls', [
        'is-live', 'is-checked-in', 'is-awaiting-result', 'is-needs-reschedule',
    ])
    def test_every_live_class_the_card_can_emit_is_styled(self, css, cls):
        assert f'.bracket-match.{cls}' in css

    def test_the_live_pill_and_its_pulse_exist(self, css):
        assert '.bracket-live-pill' in css
        assert '@keyframes bracket-live-pulse' in css

    def test_the_pulse_respects_reduced_motion(self, css):
        """A bracket left open on a stream overlay for hours must not force
        animation on someone who asked for none."""
        block = css.split('@media (prefers-reduced-motion: reduce)')[1]
        assert 'bracket-live-pill' in block
        assert 'animation: none' in block

    @pytest.mark.parametrize('tone', ['imminent', 'attention', 'done'])
    def test_every_non_live_pill_tone_is_styled(self, css, tone):
        assert f'.bracket-status-pill.tone-{tone}' in css

    def test_the_live_tone_is_defined_for_both_themes(self, css):
        """The tone names come from ``match_status.STATUS_TONES``; a variable
        defined only on ``body`` would leave the dark theme with a light accent."""
        light = css.split('body {')[1].split('}')[0]
        dark = css.split('.q-dark {')[1].split('}')[0]
        for var in ('--bracket-live', '--bracket-attention', '--bracket-done'):
            assert var in light
            assert var in dark
