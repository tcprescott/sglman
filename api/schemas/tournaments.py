"""Schemas for tournament endpoints."""

from datetime import datetime
from typing import Optional

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
    average_match_duration: Optional[int] = None
    max_match_duration: Optional[int] = None
    staff_administered: bool
    created_at: datetime
    updated_at: datetime
