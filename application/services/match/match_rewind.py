"""The match lifecycle as an ordered list of steps, for rewinding.

Rewinding goes back to one step and clears every later one together, so a
match can never end up finished without having started.
"""

from typing import List, Tuple

from models import Match

MATCH_STEPS: Tuple[str, ...] = ('scheduled', 'checked_in', 'started', 'finished', 'confirmed')

MATCH_STEP_LABELS = {
    'scheduled': 'Scheduled',
    'checked_in': 'Checked in',
    'started': 'Started',
    'finished': 'Finished',
    'confirmed': 'Confirmed',
}

_STEP_FIELDS = {
    'checked_in': 'seated_at',
    'started': 'started_at',
    'finished': 'finished_at',
    'confirmed': 'confirmed_at',
}

_REWIND_EXPLANATIONS = {
    'scheduled': 'Clears check-in, start, finish and confirmation. Back to the start.',
    'checked_in': 'Clears the start, finish and confirmation. Players stay checked in.',
    'started': 'Clears the finish and confirmation. The match is running again.',
    'finished': 'Clears the confirmation only.',
}


def reached_step(match: Match) -> str:
    """The furthest step this match has a timestamp for."""
    for step in reversed(MATCH_STEPS[1:]):
        if getattr(match, _STEP_FIELDS[step], None) is not None:
            return step
    return 'scheduled'


def rewind_targets(match: Match) -> List[Tuple[str, str]]:
    """``(step, explanation)`` for every step before the one reached, nearest first."""
    reached = MATCH_STEPS.index(reached_step(match))
    return [(step, _REWIND_EXPLANATIONS[step]) for step in reversed(MATCH_STEPS[:reached])]


def clear_flags_for(step: str) -> dict:
    """The ``update_match`` clear flags that take a match back to ``step``."""
    if step not in _REWIND_EXPLANATIONS:
        raise ValueError(f"Can't rewind a match to '{step}'.")
    keep = MATCH_STEPS.index(step)
    flag = {'checked_in': 'clear_seated', 'started': 'clear_started',
            'finished': 'clear_finished', 'confirmed': 'clear_confirmed'}
    return {flag[s]: True for s in MATCH_STEPS[keep + 1:]}
