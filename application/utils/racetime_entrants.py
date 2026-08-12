"""Shared helpers for reconciling racetime entrants against local records.

Racetime room results arrive as a list of
:class:`~racetimebot.transport.RaceEntrant`. Every capture path that maps those
entrants onto local rows — the async-qualifier live-race capture and the match
race-room result recorder — needs the same two judgements: which entrants
actually finished, and a human-readable handle for the ones it could not link.
Keeping both here means the two paths cannot answer them differently.
"""

from racetimebot.transport import EntrantStatus, RaceEntrant


def unmatched_handle(entrant: RaceEntrant) -> str:
    """Human-readable handle for an entrant with no linked local record.

    Prefers the racetime display name, falling back to the raw account id.
    """
    return entrant.display_name or entrant.user_id


def is_scored_finish(entrant: RaceEntrant) -> bool:
    """True when racetime reported a finish **and** the time that goes with it.

    ``DONE`` alone is not enough: the payload can carry a null ``finish_time``,
    and neither path can do anything useful with a finish it cannot measure. The
    match recorder would sort it against ``None``, and the qualifier capture
    would write an approved run with no elapsed time — one par cannot score and
    the leaderboard drops, spending the racer's pool slot on a run nobody sees.
    Such an entrant belongs on the staff-reconcile route instead.
    """
    return entrant.status == EntrantStatus.DONE and entrant.finish_time is not None
