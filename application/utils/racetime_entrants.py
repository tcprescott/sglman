"""Shared helpers for reconciling racetime entrants against local records.

Racetime room results arrive as a list of
:class:`~racetimebot.transport.RaceEntrant`. Every capture path that maps those
entrants onto local rows — the async-qualifier live-race capture and the match
race-room result recorder — needs the same idiom for the entrants it could not
link: capture a human-readable handle so staff can reconcile it afterward.
Keeping that idiom here means the two paths format unmatched entrants
identically.
"""

from racetimebot.transport import RaceEntrant


def unmatched_handle(entrant: RaceEntrant) -> str:
    """Human-readable handle for an entrant with no linked local record.

    Prefers the racetime display name, falling back to the raw account id.
    """
    return entrant.display_name or entrant.user_id
