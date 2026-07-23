"""Reusable bracket-graph simulation harness (NOT a test module).

Engine-agnostic helpers other engine units (double-elim, etc.) reuse to validate
the structural output of a ``generate()`` call and to play a match graph to a
champion. Leading underscore keeps pytest from collecting it.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from application.services.bracket_engines import GeneratedMatch


def build_index(matches) -> Dict[Tuple[int, int], GeneratedMatch]:
    """Index a match list by ``(round, position)``."""
    return {(m.round, m.position): m for m in matches}


def validate_graph(matches) -> None:
    """Assert the graph is internally consistent.

    Unique ``(round, position)`` keys; every ``winner_to``/``loser_to`` points at
    an existing match with ``slot`` in {1, 2}; no match places the same seed in
    both slots.
    """
    keys = [(m.round, m.position) for m in matches]
    assert len(keys) == len(set(keys)), "duplicate (round, position)"

    index = build_index(matches)
    for m in matches:
        for dest in (m.winner_to, m.loser_to):
            if dest is None:
                continue
            assert dest.slot in (1, 2), f"bad slot {dest.slot}"
            assert (dest.round, dest.position) in index, (
                f"dangling pointer to ({dest.round}, {dest.position})"
            )
        if m.entry1_seed is not None and m.entry2_seed is not None:
            assert m.entry1_seed != m.entry2_seed, "same seed in both slots"


def simulate_single_elim(
    matches,
    num_entries: int,
    winner_pick: Callable[[int, int], int],
) -> dict:
    """Play a single-elimination graph to completion.

    ``winner_pick(seed_a, seed_b) -> winning_seed`` decides each contested match.
    Byes and initial seeds come from the graph's round-1 placements; ``is_bye``
    matches auto-resolve to the present seed. Returns ``champion``, ``losses``
    (seed -> loss count), ``played`` (contested, non-bye matches) and
    ``bye_count``.
    """
    index = build_index(matches)

    # slots[(round, position)] = [entry1_seed_or_None, entry2_seed_or_None]
    slots: Dict[Tuple[int, int], list] = {
        key: [m.entry1_seed, m.entry2_seed] for key, m in index.items()
    }
    resolved: set = set()
    losses: Dict[int, int] = {}
    played = 0
    bye_count = 0
    champion: Optional[int] = None

    def place(dest, seed: int) -> None:
        slots[(dest.round, dest.position)][dest.slot - 1] = seed

    # Repeatedly resolve any match whose both slots are settled (or that is a bye).
    progressed = True
    while progressed:
        progressed = False
        for key, m in index.items():
            if key in resolved:
                continue
            a, b = slots[key]
            if m.is_bye:
                present = a if a is not None else b
                if present is None:
                    continue
                winner = present
                bye_count += 1
            else:
                if a is None or b is None:
                    continue
                winner = winner_pick(a, b)
                loser = b if winner == a else a
                losses[loser] = losses.get(loser, 0) + 1
                played += 1
            resolved.add(key)
            progressed = True
            if m.winner_to is not None:
                place(m.winner_to, winner)
            else:
                champion = winner

    return {
        'champion': champion,
        'losses': losses,
        'played': played,
        'bye_count': bye_count,
    }
