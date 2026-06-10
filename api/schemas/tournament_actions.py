"""Request schemas for tournament write actions."""

from typing import Optional

from pydantic import BaseModel, Field


class TournamentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    seed_generator: Optional[str] = None
    bracket_url: Optional[str] = None
    rules_url: Optional[str] = None
    tournament_format: Optional[str] = None
    triforce_access_message: Optional[str] = None
    average_match_duration: Optional[int] = None
    max_match_duration: Optional[int] = None
    is_active: bool = True
    players_per_match: int = 2
    team_size: int = 1
    staff_administered: bool = False


class TournamentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    seed_generator: Optional[str] = None
    bracket_url: Optional[str] = None
    rules_url: Optional[str] = None
    tournament_format: Optional[str] = None
    triforce_access_message: Optional[str] = None
    average_match_duration: Optional[int] = None
    max_match_duration: Optional[int] = None
    is_active: Optional[bool] = None
    players_per_match: Optional[int] = None
    team_size: Optional[int] = None
    staff_administered: Optional[bool] = None


class MembershipRequest(BaseModel):
    user_id: int = Field(..., description="User to add as admin / crew coordinator")
