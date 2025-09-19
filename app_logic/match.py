from datetime import datetime
from models import Match, MatchPlayers, User

async def create_match(tournament_id, date_value, time_value, comment_value, player_ids=None):
    match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    match = await Match.create(tournament_id=tournament_id, scheduled_at=match_time)
    if player_ids:
        for pid in player_ids:
            user = await User.get(id=pid)
            await MatchPlayers.create(match=match, user=user)
    if comment_value:
        match.comment = comment_value
        await match.save()
    return match
