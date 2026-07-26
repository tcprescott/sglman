"""Settled-bracket-game guard for ``MatchService.record_match_result`` (D6).

The match→bracket direction of the seam has two doors to a result: staff can
settle a matchup with ``BracketService.report_result``, or they can record the
result on the ``Match`` and let ``advance_if_linked`` push it through. Once the
second door has fired, re-recording the ``Match``'s ranks would rewrite the game
the bracket **already advanced on** — the series' win count, the downstream
slots, and any completed stage would all keep the old answer, and nothing would
say so.

So the edit is blocked, and staff are pointed at ``override_result``, which
re-advances properly. Same shape and same reasoning as the sibling
``match_source_guard``: a pure, ORM-free assertion the service calls with a row
it already loaded. The UI hides the control too, but this is the enforcement.
"""

from typing import Optional

from models import BracketMatchGameState


def assert_bracket_result_editable(game: Optional[object]) -> None:
    """Raise ``ValueError`` if ``game`` is a bracket game that already settled.

    A no-op for the overwhelming majority of matches, which back no bracket game
    at all (``game is None``), and for a game still ``SCHEDULED`` — recording a
    result on that one is the normal path, and settling it is what advances the
    bracket. A ``CANCELLED`` game is also left alone: the series clinched without
    it, so its ``Match`` no longer feeds anything.
    """
    if game is None:
        return
    if getattr(game, 'state', None) != BracketMatchGameState.COMPLETE:
        return

    raise ValueError(
        f"This match's result is already recorded in {_bracket_name(game)}. "
        "Correct it from the bracket (Results → Override) so the bracket "
        "re-advances with it."
    )


def _bracket_name(game: object) -> str:
    """The stage name to name in the error, or a generic fallback.

    Defensive rather than trusting the prefetch chain: the guard's job is to
    block the edit, and a message that says "the bracket" is still actionable if
    a caller handed us a lean row.
    """
    bracket_match = getattr(game, 'bracket_match', None)
    bracket = getattr(bracket_match, 'bracket', None) if bracket_match else None
    name = getattr(bracket, 'name', None) if bracket else None
    return name or 'the bracket'
