"""Request schemas for tournament write actions."""

from datetime import date
from typing import Dict, Optional, Tuple

from pydantic import BaseModel, Field

# Per-tournament "tournament days" override. The mapping keys off each day
# (``YYYY-MM-DD``) to an ``[open, close]`` pair of ``HH:MM`` strings; its
# ``model_dump()`` yields the ``{date: (open, close)}`` shape the service's
# ``validate_hours_mapping`` consumes directly. ``None`` (or omission on update)
# leaves the tournament inheriting the tenant setting.
_HOURS_DESC = (
    'Per-day match hours as {"YYYY-MM-DD": ["HH:MM open", "HH:MM close"]}. '
    'Omit or null to inherit the community setting.'
)
_DATE_DESC = 'Overrides the community event-window bound; null inherits it.'


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
    event_start_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    event_end_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    tournament_hours: Optional[Dict[date, Tuple[str, str]]] = Field(
        default=None, description=_HOURS_DESC,
    )


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
    event_start_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    event_end_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    tournament_hours: Optional[Dict[date, Tuple[str, str]]] = Field(
        default=None, description=_HOURS_DESC,
    )


class MembershipRequest(BaseModel):
    user_id: int = Field(..., description="User to add as admin / crew coordinator")
