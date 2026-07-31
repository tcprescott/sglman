"""Pending crew is work; it has to be countable.

A signup awaiting approval was communicated to staff by text colour and
nothing else — the words "pending", "awaiting approval" and "to approve"
appeared nowhere on the Schedule board, and ``.st-pending`` (its only marker)
is the same class the overdue-timestamp cell uses. The board now carries a
strip built from this module.
"""

from application.utils.crew_queue import PendingCrew, pending_crew_summary


def _row(match_id, state='Scheduled', commentators=(), trackers=()):
    return {
        'id': match_id,
        'state': state,
        'commentators': [{'name': n, 'approved': a} for n, a in commentators],
        'trackers': [{'name': n, 'approved': a} for n, a in trackers],
    }


class TestCounting:
    def test_an_empty_board_has_no_queue(self):
        assert pending_crew_summary([]).total == 0
        assert pending_crew_summary([]).label == ''

    def test_a_fully_approved_board_has_no_queue(self):
        rows = [_row(1, commentators=[('Alice', True)], trackers=[('Bob', True)])]
        assert pending_crew_summary(rows).total == 0

    def test_the_two_roles_are_counted_apart(self):
        """They are staffed by different people and triaged differently."""
        rows = [
            _row(1, commentators=[('Alice', False), ('Bea', False)]),
            _row(2, trackers=[('Cy', False)]),
        ]
        summary = pending_crew_summary(rows)
        assert (summary.commentators, summary.trackers) == (2, 1)
        assert summary.total == 3

    def test_it_names_the_matches_so_the_count_can_be_filtered_to(self):
        rows = [
            _row(1, commentators=[('Alice', False)]),
            _row(2, commentators=[('Bea', True)]),
            _row(3, trackers=[('Cy', False)]),
        ]
        assert pending_crew_summary(rows).match_ids == (1, 3)

    def test_a_match_is_listed_once_however_many_signups_it_has(self):
        rows = [_row(1, commentators=[('A', False), ('B', False)], trackers=[('C', False)])]
        assert pending_crew_summary(rows).match_ids == (1,)

    def test_a_settled_match_is_not_outstanding_work(self):
        """Otherwise the queue is permanently non-empty and stops being read."""
        rows = [
            _row(1, state='Confirmed', commentators=[('Alice', False)]),
            _row(2, state='Cancelled', trackers=[('Bea', False)]),
        ]
        assert pending_crew_summary(rows).total == 0

    def test_a_finished_but_unconfirmed_match_still_counts(self):
        """It can still be un-approved or corrected, and the DM already went."""
        rows = [_row(1, state='Finished', commentators=[('Alice', False)])]
        assert pending_crew_summary(rows).total == 1

    def test_a_row_without_crew_keys_is_not_an_error(self):
        assert pending_crew_summary([{'id': 1, 'state': 'Scheduled'}]).total == 0

    def test_junk_in_a_crew_cell_is_skipped_rather_than_counted(self):
        rows = [{'id': 1, 'state': 'Scheduled', 'commentators': ['Alice', None]}]
        assert pending_crew_summary(rows).total == 0


class TestLabel:
    def test_one_of_each_reads_as_singular(self):
        assert PendingCrew(commentators=1, trackers=1).label == (
            '1 commentator and 1 tracker awaiting approval')

    def test_a_role_with_none_pending_is_left_out(self):
        assert PendingCrew(commentators=3).label == '3 commentators awaiting approval'
        assert PendingCrew(trackers=2).label == '2 trackers awaiting approval'

    def test_nothing_pending_says_nothing(self):
        assert PendingCrew().label == ''

    def test_the_words_the_board_was_missing_are_in_it(self):
        """The measured finding: "pending" / "awaiting approval" / "to approve"
        appeared nowhere on the page."""
        assert 'awaiting approval' in PendingCrew(commentators=1).label
