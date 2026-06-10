"""Shared helpers for serializing a Match into the API response model.

Used by both the read endpoints and the write endpoints (which reload and
return the updated match).
"""

from typing import Optional

from api.schemas.matches import MatchResponse
from models import Match

MATCH_PREFETCH = (
    'tournament',
    'stream_room',
    'generated_seed',
    'players__user',
    'commentators__user',
    'trackers__user',
)


def serialize_match(match: Match) -> MatchResponse:
    """Serialize a match, exposing only approved crew.

    Tortoise reverse relations are read-only and Pydantic v2 serialization
    bypasses any custom from_orm, so unapproved crew are dropped here.
    """
    resp = MatchResponse.model_validate(match, from_attributes=True)
    resp.commentators = [c for c in resp.commentators if c.approved]
    resp.trackers = [t for t in resp.trackers if t.approved]
    return resp


async def load_match_response(match_id: int) -> Optional[MatchResponse]:
    """Reload a match with all relations and serialize it, or None if absent."""
    match = await Match.filter(id=match_id).prefetch_related(*MATCH_PREFETCH).first()
    return serialize_match(match) if match else None
