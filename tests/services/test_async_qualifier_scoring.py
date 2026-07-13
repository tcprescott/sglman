"""Unit tests for the async-qualifier par/score/leaderboard math (pure, no DB)."""

from application.services.async_qualifier_scoring import (
    ScoredRun,
    build_leaderboard,
    compute_par,
    compute_score,
)


class TestComputePar:
    def test_mean_of_n_fastest(self):
        # fastest 3 of [100,120,140,900] → mean(100,120,140)=120
        assert compute_par([900, 100, 140, 120], sample_size=3) == 120

    def test_fewer_than_sample_uses_all(self):
        assert compute_par([100, 200], sample_size=5) == 150

    def test_no_runs_is_none(self):
        assert compute_par([], sample_size=3) is None

    def test_ignores_nonpositive(self):
        assert compute_par([0, -5, 120], sample_size=3) == 120


class TestComputeScore:
    def test_at_par_is_100(self):
        assert compute_score(120, 120) == 100.0

    def test_twice_par_is_zero(self):
        assert compute_score(240, 120) == 0.0

    def test_fast_run_caps_at_105(self):
        assert compute_score(1, 120) == 105.0

    def test_slow_run_floors_at_zero(self):
        assert compute_score(10_000, 120) == 0.0

    def test_missing_inputs_none(self):
        assert compute_score(None, 120) is None
        assert compute_score(120, None) is None
        assert compute_score(120, 0) is None


class TestLeaderboard:
    def test_fills_slots_and_pads_missing_with_zero(self):
        # 2 pools, 1 run/pool → 2 slots. 'a' fills both, 'b' fills one.
        entries = build_leaderboard(
            pool_ids=[1, 2], runs_per_pool=1,
            scored_runs=[
                ScoredRun(1, 'a', 1, 100.0),
                ScoredRun(1, 'a', 2, 80.0),
                ScoredRun(2, 'b', 1, 90.0),
            ],
        )
        by_user = {e.user_id: e for e in entries}
        assert by_user[1].actual == 180.0
        assert by_user[1].estimate == 180.0
        assert by_user[2].actual == 90.0        # only one slot filled
        assert by_user[2].estimate == 180.0     # projected across both slots
        assert entries[0].user_id == 1          # ranked by actual desc

    def test_caps_scores_per_pool_at_runs_per_pool(self):
        # runs_per_pool=1 but two runs in the same pool → only the best counts.
        entries = build_leaderboard(
            pool_ids=[1], runs_per_pool=1,
            scored_runs=[ScoredRun(1, 'a', 1, 40.0), ScoredRun(1, 'a', 1, 95.0)],
        )
        assert entries[0].actual == 95.0
        assert entries[0].slots_filled == 1

    def test_ignores_runs_in_unknown_pools(self):
        entries = build_leaderboard(
            pool_ids=[1], runs_per_pool=1,
            scored_runs=[ScoredRun(1, 'a', 99, 100.0)],
        )
        assert entries == []
