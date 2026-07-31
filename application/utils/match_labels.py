"""Human-readable names for a match, for user-facing web copy.

The Discord side already refuses to print primary keys — see the module
docstring of :mod:`application.utils.discord_messages`, which states the rule
and identifies a match by its players, its time and its stage. The web copy was
the only place still talking in database ids ("sign up as a commentator for
match ID 17"), so the same identification lives here, built from the row the
surface already has rather than from a fresh query.

Pure formatting: takes strings and dicts, touches no ORM, so both the
presentation layer and the services can use it.
"""

from typing import Optional, Sequence


def players_label(player_names: Optional[Sequence[str]]) -> str:
    """Human-readable list of players: "A vs B" for two, comma-joined otherwise."""
    if not player_names:
        return ''
    names = list(player_names)
    if len(names) == 2:
        return ' vs '.join(names)
    return ', '.join(names)


def match_label(
    *,
    player_names: Optional[Sequence[str]] = None,
    title: str = '',
    tournament: str = '',
    scheduled_at: str = '',
    with_context: bool = True,
) -> str:
    """Name a match the way the person looking at it would.

    ``with_context`` appends the tournament and scheduled time in parentheses —
    wanted where the reader has to *decide* (a confirmation dialog), redundant
    in a toast that answers a click they just made.

    Falls back to ``'this match'`` rather than to an id: a match with no players
    and no schedule has nothing to identify it by, and the reader clicked the
    row it came from.
    """
    players = players_label(player_names)
    # Some schedule feeds set the title to the matchup itself; printing both
    # would say the same thing twice. Same suppression rule as the crew DMs.
    name = title if title and title != players else players
    context = [part for part in (tournament, scheduled_at) if part] if with_context else []

    if not name:
        # No roster: the tournament and time are all there is, so they carry the
        # label instead of trailing it.
        return ', '.join(context) if context else 'this match'
    if context:
        return f"{name} ({', '.join(context)})"
    return name


def match_row_label(row: dict, *, with_context: bool = True) -> str:
    """:func:`match_label` for a match-table row dict (``MatchDisplayService``)."""
    players = [p.get('name', '') for p in (row.get('players') or []) if p.get('name')]
    return match_label(
        player_names=players,
        title=row.get('title') or '',
        tournament=row.get('tournament') or '',
        scheduled_at=row.get('scheduled_at') or '',
        with_context=with_context,
    )
