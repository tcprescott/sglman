"""The bracket page knows who is looking, and agrees with itself about byes.

A player opening their final saw both names, no booked time and no marker for
which entry was theirs; a bye read BYE on the card and TBD in the dialog it
opened. These pin the pure halves of the fix.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from application.timezone_context import tz_scope
from models import BracketMatchState
from theme.base import HOME_SECTIONS, tab_slug
from theme.brackets.dialog import slot_display_name
from theme.brackets.render import booked_times, viewer_entries


def _match(entry1=None, entry2=None, state=BracketMatchState.OPEN, games=(), mid=1):
    return SimpleNamespace(
        id=mid, entry1_id=entry1, entry2_id=entry2, state=state, games=list(games),
    )


def _game(at, finished=None):
    return SimpleNamespace(match=SimpleNamespace(scheduled_at=at, finished_at=finished))


NAMES = {10: 'Player One', 11: 'Player Two'}


class TestByeLabel:
    def test_an_empty_side_of_a_finished_match_is_a_bye(self):
        match = _match(entry1=10, state=BracketMatchState.COMPLETE)
        assert slot_display_name(match, 1, NAMES) == 'Player One'
        assert slot_display_name(match, 2, NAMES) == 'BYE'

    def test_an_empty_side_of_an_open_match_is_still_to_be_decided(self):
        match = _match(entry1=10)
        assert slot_display_name(match, 2, NAMES) == 'TBD'

    def test_a_finished_match_with_nobody_in_it_is_not_a_bye(self):
        match = _match(state=BracketMatchState.COMPLETE)
        assert slot_display_name(match, 1, NAMES) == 'TBD'


class TestViewerEntries:
    def test_only_the_viewers_entries(self):
        entrants = [SimpleNamespace(id=1, user_id=7), SimpleNamespace(id=2, user_id=8)]
        entries = [
            SimpleNamespace(id=100, entrant_id=1),
            SimpleNamespace(id=101, entrant_id=2),
        ]
        assert viewer_entries(entrants, entries, 7) == {100}

    def test_signed_out_marks_nothing(self):
        entrants = [SimpleNamespace(id=1, user_id=None)]
        entries = [SimpleNamespace(id=100, entrant_id=1)]
        assert viewer_entries(entrants, entries, None) == set()


class TestBookedTimes:
    def test_the_earliest_unfinished_game_wins(self):
        early = datetime(2026, 7, 4, 15, 0, tzinfo=timezone.utc)
        late = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
        done = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
        match = _match(games=[_game(late), _game(early), _game(done, finished=done)])
        with tz_scope('UTC'):
            short, full = booked_times([match])[1]
        assert short == 'Sat 15:00'
        assert full.startswith('2026-07-04 15:00')

    def test_a_finished_matchup_shows_no_time(self):
        at = datetime(2026, 7, 4, 15, 0, tzinfo=timezone.utc)
        match = _match(state=BracketMatchState.COMPLETE, games=[_game(at)])
        assert booked_times([match]) == {}

    def test_an_unbooked_matchup_shows_no_time(self):
        assert booked_times([_match(games=[_game(None)])]) == {}


class TestHomeSectionsMatchHome:
    def test_the_drawer_offers_homes_own_tabs(self):
        """A tab-less page offers a member home's sections; they must be home's."""
        from pathlib import Path

        source = Path('pages/home.py').read_text()
        for label, icon in HOME_SECTIONS:
            assert f"'label': '{label}', 'icon': '{icon}'" in source, label
        assert [tab_slug(label) for label, _ in HOME_SECTIONS] == [
            'event', 'my-schedule', 'tournaments', 'profile',
        ]
