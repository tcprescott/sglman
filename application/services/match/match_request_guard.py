"""Bracket-run scheduling guard for ``MatchService.submit_match_request``.

A tournament that runs on a bracket — native or Challonge — schedules only the
matchups the bracket produced. ``Tournament.allow_player_match_requests`` is
turned off when a bracket is attached, and this is where that toggle is
*enforced*: the player dialog also filters those tournaments out of its dropdown,
but the REST endpoint (``POST /api/matches/request``) reaches the service
directly, so a gap here would let a player invent a matchup the bracket never
produced — one that still notifies crew and lands on the schedule.

Extracted into its own module to keep ``match_service`` focused, mirroring its
sibling ``match_source_guard``.
"""


def assert_player_requests_allowed(tournament) -> None:
    """Raise ``PermissionError`` when the tournament is scheduled from a bracket.

    Defaults to allowing the request when the attribute is absent — mock objects
    in unit tests lack it, so ``getattr`` guards it the way the SpeedGaming guard
    does.
    """
    if not getattr(tournament, 'allow_player_match_requests', True):
        raise PermissionError(
            "This tournament is scheduled from its bracket — schedule your "
            "matchup from Your Schedule instead."
        )
