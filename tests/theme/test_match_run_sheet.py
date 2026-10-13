"""The admin Schedule run sheet: which group a match lands in, and what its status says."""

import time

from theme.dialog.match_sheet import seed_rollable
from theme.tables.match_run_sheet import (
    RUN_SHEET_COLUMNS,
    arrange_run_sheet,
    run_sheet_status,
)

PLAYERS = [{'name': 'Player One'}, {'name': 'Player Two'}]


def _row(id_, state, ts=None, **extra):
    return {'id': id_, 'state': state, 'players': PLAYERS, 'scheduled_ts': ts,
            'scheduled_at': '', **extra}


class TestStatus:
    def test_finished_splits_into_three_decisions(self):
        assert run_sheet_status(_row(1, 'Finished', needs_review=True, has_result=True)) == ('Flagged', 'cancelled')
        assert run_sheet_status(_row(1, 'Finished', has_result=False)) == ('No result', 'cancelled')
        assert run_sheet_status(_row(1, 'Finished', has_result=True)) == ('To confirm', 'pending')

    def test_late_only_before_check_in(self):
        assert run_sheet_status(_row(1, 'Scheduled', is_overdue=True)) == ('Late', 'pending')
        assert run_sheet_status(_row(1, 'Checked In', is_overdue=True)) == ('Checked in', 'neutral')

    def test_a_match_without_players_says_so(self):
        assert run_sheet_status(dict(_row(1, 'Scheduled'), players=[]))[0] == 'Waiting for players'


class TestArrange:
    def test_groups_in_decision_live_next_order_with_one_header_each(self):
        rows = [
            _row(1, 'Scheduled', 300),
            _row(2, 'Started', 200),
            _row(3, 'Finished', 100, has_result=True),
            _row(4, 'Scheduled', 100),
            _row(5, 'Confirmed', 50),
            _row(6, 'Confirmed', 60),
        ]
        arranged = arrange_run_sheet(rows)
        assert [r['id'] for r in arranged] == [3, 2, 4, 1, 6, 5]
        assert [r['_group'] for r in arranged if r['_group_start']] == [
            'Needs a decision', 'Live now', 'Up next', 'Confirmed',
        ]

    def test_names_and_stage_fallbacks(self):
        row = arrange_run_sheet([_row(1, 'Scheduled', time.time(), is_stream_candidate=True)])[0]
        assert row['_who'] == 'Player One vs Player Two'
        assert row['_stage'] == 'Candidate'
        assert row['_day'] == 'Today'

    def test_columns_are_not_sortable(self):
        # The groups are the order; a header sort would scatter them.
        assert not any(c.get('sortable') for c in RUN_SHEET_COLUMNS)


class TestSeedRollable:
    def test_mirrors_the_board_gate(self):
        base = _row(1, 'Scheduled', tournament_seed_generator='alttpr')
        assert seed_rollable(base)
        assert not seed_rollable(dict(base, is_racetime=True))
        assert not seed_rollable(dict(base, players=[]))
        assert not seed_rollable(dict(base, state='Finished'))
        assert not seed_rollable(dict(base, tournament_seed_generator=None))
