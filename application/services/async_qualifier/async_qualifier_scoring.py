"""Async-qualifier par + score + leaderboard math (PR 9).

Pure, DB-free functions ported from SahasrahBot's async-tournament scoring so the
formulas are unit-testable in isolation; :class:`AsyncQualifierService` assembles
the inputs from repositories and applies the results.

- **par** = mean of the ``sample_size`` fastest *finished + approved* runs on a
  permalink (whole seconds).
- **score** = ``clamp(0, 105, (2 - elapsed/par) * 100)`` — 100 at par, 0 at twice
  par, capped at 105 for a run ~5% under par.
- **leaderboard** = per-pool ``runs_per_pool`` slots; a user's best scores fill
  their slots, unfilled slots count 0 (``actual``); a separate ``estimate``
  projects the user's mean realized-slot score across all slots (finished runs
  only, so a partial entrant isn't understated). No tie-break — Python's stable
  sort preserves the provided (deterministic) input order.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

# Score bounds and the reference multipliers behind ``(2 - elapsed/par) * 100``.
SCORE_MIN = 0.0
SCORE_MAX = 105.0
# Default number of fastest approved runs averaged into a permalink's par. Read
# from ``AsyncQualifier.config['par_sample_size']`` when set; this is the
# fallback so a freshly-authored qualifier scores sensibly with no config.
DEFAULT_PAR_SAMPLE_SIZE = 5


def compute_par(finished_elapsed_seconds: Sequence[int], sample_size: int = DEFAULT_PAR_SAMPLE_SIZE) -> Optional[int]:
    """Mean (rounded) of the ``sample_size`` fastest finished times, or None.

    ``finished_elapsed_seconds`` need not be pre-sorted. Returns None when there
    are no finished runs yet (par is undefined, so runs stay unscored).
    """
    times = sorted(t for t in finished_elapsed_seconds if t is not None and t > 0)
    if not times:
        return None
    n = max(1, sample_size)
    fastest = times[:n]
    return round(sum(fastest) / len(fastest))


def compute_score(elapsed_seconds: Optional[int], par_seconds: Optional[int]) -> Optional[float]:
    """``clamp(0, 105, (2 - elapsed/par) * 100)``; None if not computable."""
    if not elapsed_seconds or not par_seconds or elapsed_seconds <= 0 or par_seconds <= 0:
        return None
    raw = (2 - elapsed_seconds / par_seconds) * 100
    return max(SCORE_MIN, min(SCORE_MAX, raw))


@dataclass(frozen=True)
class ScoredRun:
    """One approved, scored run's contribution to a user's leaderboard total."""

    user_id: int
    username: str
    pool_id: int
    score: float


@dataclass(frozen=True)
class LeaderboardEntry:
    user_id: int
    username: str
    actual: float          # realized total: filled slots + zeros for unfilled
    estimate: float        # projected total at the user's mean realized score
    slots_filled: int
    slots_total: int


def build_leaderboard(
    *,
    pool_ids: Sequence[int],
    runs_per_pool: int,
    scored_runs: Sequence[ScoredRun],
) -> List[LeaderboardEntry]:
    """Rank users by ``actual`` (desc). Stable for ties (input order preserved).

    Per user and pool, the top ``runs_per_pool`` scores fill that pool's slots;
    unfilled slots across all pools score 0 in ``actual``. ``estimate`` fills
    every slot at the user's mean realized-slot score, so it never understates a
    partial entrant. Pass ``scored_runs`` in a deterministic order (e.g. sorted
    by username) so tie ordering is stable.
    """
    per_pool = max(1, runs_per_pool)
    slots_total = len(pool_ids) * per_pool
    pool_id_set = set(pool_ids)

    # Preserve first-seen order for stable tie handling.
    order: List[int] = []
    names: Dict[int, str] = {}
    by_user_pool: Dict[int, Dict[int, List[float]]] = {}
    for run in scored_runs:
        if run.pool_id not in pool_id_set:
            continue
        if run.user_id not in by_user_pool:
            by_user_pool[run.user_id] = {}
            order.append(run.user_id)
            names[run.user_id] = run.username
        by_user_pool[run.user_id].setdefault(run.pool_id, []).append(run.score)

    entries: List[LeaderboardEntry] = []
    for user_id in order:
        pools = by_user_pool[user_id]
        actual = 0.0
        filled = 0
        for pool_id in pool_ids:
            top = sorted(pools.get(pool_id, []), reverse=True)[:per_pool]
            actual += sum(top)
            filled += len(top)
        estimate = (actual / filled) * slots_total if filled else 0.0
        entries.append(LeaderboardEntry(
            user_id=user_id,
            username=names[user_id],
            actual=round(actual, 2),
            estimate=round(estimate, 2),
            slots_filled=filled,
            slots_total=slots_total,
        ))

    entries.sort(key=lambda e: e.actual, reverse=True)
    return entries
