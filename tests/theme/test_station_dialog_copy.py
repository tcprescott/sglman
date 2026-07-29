"""``StationAssignmentDialog``'s two copy modes.

The same dialog does two jobs: the proctor's check-in (seat the players, then
the caller checks the match in) and correcting the stations of a match that is
already checked in. The check-in mode has to say "check in" — the audit found a
dialog that never mentioned the thing it was doing — and the stations mode must
not claim to check anything in, because in that mode nothing is checked in.

Rendering the dialog needs a live NiceGUI client, so this locks the copy table
and the constructor state ``open()`` reads from it.
"""

from theme.dialog.station_assignment_dialog import _PURPOSE_COPY, StationAssignmentDialog


class TestPurposeCopy:
    def test_checkin_copy_mentions_checking_in(self):
        assert 'check' in _PURPOSE_COPY['checkin']['title'].lower()
        assert 'check' in _PURPOSE_COPY['checkin']['submit'].lower()

    def test_station_copy_does_not_claim_to_check_in(self):
        assert 'check in' not in _PURPOSE_COPY['stations']['submit'].lower()
        assert 'check in' not in _PURPOSE_COPY['stations']['title'].lower()

    def test_every_mode_supplies_the_three_strings(self):
        for copy in _PURPOSE_COPY.values():
            assert set(copy) == {'title', 'lead', 'submit'}
            assert all(copy.values())

    def test_titles_carry_the_match_id_placeholder(self):
        for copy in _PURPOSE_COPY.values():
            assert copy['title'].format(id=11).endswith('#11')


class TestPurposeSelection:
    def test_defaults_to_stations(self):
        assert StationAssignmentDialog(match=None).purpose == 'stations'

    def test_honours_a_known_purpose(self):
        assert StationAssignmentDialog(match=None, purpose='checkin').purpose == 'checkin'

    def test_falls_back_for_an_unknown_purpose(self):
        assert StationAssignmentDialog(match=None, purpose='nonsense').purpose == 'stations'
