"""Schemas for tournament endpoints."""

from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class TournamentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    seed_generator: Optional[str] = None
    is_active: bool
    players_per_match: int
    team_size: int
    bracket_url: Optional[str] = None
    rules_url: Optional[str] = None
    tournament_format: Optional[str] = None
    triforce_access_message: Optional[str] = None
    average_match_duration: Optional[int] = None
    max_match_duration: Optional[int] = None
    # Approved crew a streamed match needs before the coverage reports call it
    # covered; 0 means the tournament does not use that role.
    required_commentators: int
    required_trackers: int
    staff_administered: bool
    # False once a bracket is attached: the tournament schedules only its own
    # matchups, so POST /matches/request is refused for it.
    allow_player_match_requests: bool
    # Per-tournament "tournament days" override; null means the tournament
    # inherits the community (tenant) setting for that facet.
    event_start_date: Optional[date] = None
    event_end_date: Optional[date] = None
    tournament_hours: Optional[Dict[str, Any]] = None
    # The player self-signup window. Null on either side is permissive — no open
    # date means signups are open now, no close date means they stay open — so a
    # tournament with both null accepts signups indefinitely.
    signups_open_at: Optional[datetime] = None
    signups_close_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
