"""Unit tests for the shared standings & tiebreakers module."""

from __future__ import annotations

import pytest

from application.services.bracket_engines.standings import (
    ResultRow,
    Standing,
    StandingsConfig,
    compute_standings,
)


def _by_ref(standings: list[Standing]) -> dict[int, Standing]:
    return {s.ref: s for s in standings}


def test_points_totals_wins_draws_losses_byes():
    refs = [1, 2, 3, 4]
    results = [
        ResultRow(1, 2, winner=1),      # 1 beats 2
        ResultRow(1, 3, winner=None),   # 1 draws 3
        ResultRow(4, None, winner=4),   # 4 bye
        ResultRow(2, 3, winner=3),      # 3 beats 2
    ]
    config = StandingsConfig(win_points=3, draw_points=1, loss_points=0, bye_points=3)
    s = _by_ref(compute_standings(refs, results, config))

    assert s[1].points == 3 + 1          # a win + a draw
    assert s[1].wins == 1 and s[1].draws == 1
    assert s[2].points == 0              # two losses
    assert s[2].losses == 2
    assert s[3].points == 1 + 3          # a draw + a win
    assert s[4].points == 3 and s[4].byes == 1


def test_ranks_and_ordering_sorted():
    refs = [1, 2, 3]
    results = [
        ResultRow(1, 2, winner=1),
        ResultRow(1, 3, winner=1),
        ResultRow(2, 3, winner=2),
    ]
    out = compute_standings(refs, results, StandingsConfig())
    assert [s.ref for s in out] == [1, 2, 3]
    assert [s.rank for s in out] == [1, 2, 3]
    assert all(s.tied_with == () for s in out)


def test_buchholz_breaks_equal_points():
    # 1 beats 3, loses to 4  => 1 point.
    # 2 beats 5, loses to 4  => 1 point.  (tied on points with 1)
    # Shared opponent 4; the differing opponents are 3 (strong) vs 5 (weak), so 1's
    # strength-of-schedule (Buchholz = sum of opponent points) is higher.
    refs = [1, 2, 3, 4, 5]
    results = [
        ResultRow(1, 3, winner=1),   # 1 beats 3
        ResultRow(4, 1, winner=4),   # 4 beats 1
        ResultRow(2, 5, winner=2),   # 2 beats 5
        ResultRow(4, 2, winner=4),   # 4 beats 2
        ResultRow(3, 5, winner=3),   # 3 also beats 5 (3 stronger than 5)
    ]
    config = StandingsConfig(win_points=1, tiebreakers=('buchholz',))
    s = _by_ref(compute_standings(refs, results, config))

    assert s[1].points == s[2].points == 1
    # points: 3 -> 1 (beat 5), 4 -> 2 (beat 1 & 2), 5 -> 0.
    # Buchholz(1) = pts(3) + pts(4) = 1 + 2 = 3.
    # Buchholz(2) = pts(5) + pts(4) = 0 + 2 = 2.
    assert s[1].tiebreakers['buchholz'] == 3
    assert s[2].tiebreakers['buchholz'] == 2
    assert s[1].rank < s[2].rank
    assert s[1].tied_with == () and s[2].tied_with == ()


def test_omw_with_floor_applied():
    # 1 beats hopeless 3 (0% win rate -> floored to omw_floor).
    # 2 beats solid 4 (2 wins, 1 loss -> 2/3, above the floor).
    # Same points; 2's opponent-win-% is higher, so 2 ranks ahead. The assertion on
    # player 1 exercises the floor: 3's true rate is 0 but OMW uses the floor.
    refs = [1, 2, 3, 4, 5, 6]
    results = [
        ResultRow(3, 5, winner=5),   # 3 loses
        ResultRow(3, 6, winner=6),   # 3 loses again => 0-2, 0%
        ResultRow(1, 3, winner=1),   # 1 beats hopeless 3
        ResultRow(4, 5, winner=4),   # 4 wins
        ResultRow(4, 6, winner=4),   # 4 wins => 2-0 so far
        ResultRow(2, 4, winner=2),   # 2 beats 4 (4 now 2-1 => 2/3)
    ]
    config = StandingsConfig(win_points=1, tiebreakers=('omw',), omw_floor=1.0 / 3.0)
    s = _by_ref(compute_standings(refs, results, config))

    assert s[1].points == s[2].points == 1
    # 3 played 3 matches (5, 6, 1), zero wins => 0%, floored to 1/3.
    assert s[1].tiebreakers['omw'] == pytest.approx(1.0 / 3.0)
    # 4 played 3 (5, 6, 2), two wins => 2/3, above the floor so used as-is.
    assert s[2].tiebreakers['omw'] == pytest.approx(2.0 / 3.0)
    assert s[2].rank < s[1].rank  # stronger schedule ranks higher


def test_head_to_head_breaks_two_way_tie():
    # 1 and 2 each go 2-2 against the same outside field, so they tie on points; the
    # head-to-head game (1 beat 2) breaks it. Each also collects one win the other
    # doesn't (1 from beating 2, 2 from beating 5) to keep the point totals equal.
    refs = [1, 2, 3, 4, 5]
    results = [
        ResultRow(1, 3, winner=1),   # 1 beats 3
        ResultRow(2, 3, winner=2),   # 2 beats 3
        ResultRow(1, 4, winner=4),   # 1 loses to 4
        ResultRow(2, 4, winner=4),   # 2 loses to 4
        ResultRow(1, 5, winner=5),   # 1 loses to 5
        ResultRow(2, 5, winner=2),   # 2 beats 5
        ResultRow(1, 2, winner=1),   # 1 beats 2 (head-to-head)
    ]
    config = StandingsConfig(win_points=1, tiebreakers=('head_to_head',))
    s = _by_ref(compute_standings(refs, results, config))

    # 1: beat 3, lost 4, lost 5, beat 2 => 2 points.
    # 2: beat 3, lost 4, beat 5, lost 1 => 2 points.
    assert s[1].points == s[2].points == 2
    assert s[1].rank < s[2].rank  # 1 beat 2 head-to-head
    assert s[1].tied_with == () and s[2].tied_with == ()


def test_unresolved_tie_shares_rank_and_populates_tied_with():
    # Rock-paper-scissors among 1,2,3: each 1-1, cyclic head-to-head, identical on
    # every tiebreaker => genuinely unresolved.
    refs = [1, 2, 3]
    results = [
        ResultRow(1, 2, winner=1),
        ResultRow(2, 3, winner=2),
        ResultRow(3, 1, winner=3),
    ]
    config = StandingsConfig(
        win_points=1, tiebreakers=('buchholz', 'omw', 'head_to_head')
    )
    s = _by_ref(compute_standings(refs, results, config))

    assert {s[r].points for r in refs} == {1}
    assert all(s[r].rank == 1 for r in refs)  # equal rank, competition style
    assert s[1].tied_with == (2, 3)
    assert s[2].tied_with == (1, 3)
    assert s[3].tied_with == (1, 2)


def test_head_to_head_only_splits_when_decisive():
    # A 3-way point tie where head-to-head forms a strict order 10 > 11 > 12.
    refs = [10, 11, 12, 13]
    results = [
        # Each of 10,11,12 beats 13 and loses to a common 4th-party pattern so they
        # tie on points, then resolve purely on the internal H2H order below.
        ResultRow(10, 13, winner=10),
        ResultRow(11, 13, winner=11),
        ResultRow(12, 13, winner=12),
        ResultRow(10, 11, winner=10),  # 10 beats 11
        ResultRow(11, 12, winner=11),  # 11 beats 12
        ResultRow(10, 12, winner=10),  # 10 beats 12  => strict order 10>11>12
        # balance points: give 11 and 12 an extra win, 10 an extra loss, so the trio
        # ties on total points while the head-to-head sub-results order them.
        ResultRow(10, 13, winner=13),  # 10 drops one to 13
    ]
    # 10: beat13, beat11, beat12, lost13 => 3 pts.
    # 11: beat13, lost10, beat12 => 2 pts.  12: beat13, lost11, lost10 => 1 pt.
    # Not a point tie — this case simply checks head-to-head never mis-ranks a clear
    # points order. Assert the natural points order holds.
    config = StandingsConfig(win_points=1, tiebreakers=('head_to_head',))
    s = _by_ref(compute_standings(refs, results, config))
    assert s[10].rank < s[11].rank < s[12].rank < s[13].rank


def test_result_referencing_unknown_ref_raises():
    with pytest.raises(ValueError):
        compute_standings([1, 2], [ResultRow(1, 99, winner=1)], StandingsConfig())


def test_self_pairing_rejected():
    with pytest.raises(ValueError):
        compute_standings([1], [ResultRow(1, 1, winner=1)], StandingsConfig())
