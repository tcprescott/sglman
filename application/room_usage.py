from models import Match, MatchPlayers
from tortoise.expressions import Q

async def count_active_race_players(tournament_id=None, exclude_stage=False):
    """
    Returns the number of players currently involved in a race where seated_at is set, but finished_at is not.
    If tournament_id is provided, only counts players in that tournament.
    If exclude_stage is True, excludes races where stream_room (stage) is set.
    """
    match_filter = Q(seated_at__isnull=False) & Q(finished_at__isnull=True)
    if tournament_id is not None:
        match_filter &= Q(tournament_id=tournament_id)
    if exclude_stage:
        match_filter &= Q(stream_room_id__isnull=True)
    active_matches = await Match.filter(match_filter).all()
    if not active_matches:
        return 0
    match_ids = [m.id for m in active_matches]
    return await MatchPlayers.filter(match_id__in=match_ids).count()
