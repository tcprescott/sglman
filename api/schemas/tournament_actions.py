"""Request schemas for tournament write actions."""

from datetime import date, datetime
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
_SIGNUP_DESC = (
    'Bound of the player self-signup window (UTC). Null on either side is '
    'permissive: no open date means signups are open now, no close date means '
    'they stay open. Staff enrolment ignores the window entirely.'
)
_CREW_DESC = (
    'Approved crew a streamed match needs before the coverage reports count it '
    'as covered. 0 means this tournament does not use the role. Does not '
    'restrict signups.'
)
_UPDATE_NOTE = ' Omit to leave it unchanged.'


class TournamentCreateRequest(BaseModel):
    name: str = Field(..., description="The tournament's name. Can't be blank.")
    description: Optional[str] = Field(None, description="Long description shown to players, as markdown.")
    seed_generator: Optional[str] = Field(
        None, description="Key of the randomizer that rolls this tournament's seeds, or null for none.",
    )
    bracket_url: Optional[str] = Field(None, description="Link to the external bracket page. Must be http or https.")
    rules_url: Optional[str] = Field(None, description="Link to the rules. Must be http or https.")
    tournament_format: Optional[str] = Field(None, description="Short free-text format label, such as \"Double elimination\".")
    triforce_access_message: Optional[str] = Field(
        None, description="Markdown shown to players who may not submit triforce texts.",
    )
    randomizer_notes: Optional[str] = Field(
        None, description="The randomizer settings, preset and build the tournament races on, as markdown.",
    )
    average_match_duration: Optional[int] = Field(None, description="Typical match length in minutes.")
    max_match_duration: Optional[int] = Field(None, description="Longest a match is expected to run, in minutes.")
    is_active: bool = Field(True, description="Whether the tournament starts out active.")
    players_per_match: int = Field(2, description="How many players a match in this tournament has.")
    required_commentators: int = Field(default=1, ge=0, description=_CREW_DESC)
    required_trackers: int = Field(default=1, ge=0, description=_CREW_DESC)
    event_start_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    event_end_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    tournament_hours: Optional[Dict[date, Tuple[str, str]]] = Field(
        default=None, description=_HOURS_DESC,
    )
    signups_open_at: Optional[datetime] = Field(default=None, description=_SIGNUP_DESC)
    signups_close_at: Optional[datetime] = Field(default=None, description=_SIGNUP_DESC)


class TournamentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="New name. Can't be blank." + _UPDATE_NOTE)
    description: Optional[str] = Field(
        None, description="Long description, as markdown. An empty string clears it." + _UPDATE_NOTE,
    )
    seed_generator: Optional[str] = Field(
        None, description="Key of the randomizer that rolls this tournament's seeds." + _UPDATE_NOTE,
    )
    bracket_url: Optional[str] = Field(
        None, description="Link to the external bracket page. Must be http or https." + _UPDATE_NOTE,
    )
    rules_url: Optional[str] = Field(None, description="Link to the rules. Must be http or https." + _UPDATE_NOTE)
    tournament_format: Optional[str] = Field(None, description="Short free-text format label." + _UPDATE_NOTE)
    triforce_access_message: Optional[str] = Field(
        None, description="Markdown shown to players who may not submit triforce texts." + _UPDATE_NOTE,
    )
    randomizer_notes: Optional[str] = Field(
        None, description="The randomizer settings, preset and build, as markdown." + _UPDATE_NOTE,
    )
    average_match_duration: Optional[int] = Field(None, description="Typical match length in minutes." + _UPDATE_NOTE)
    max_match_duration: Optional[int] = Field(
        None, description="Longest a match is expected to run, in minutes." + _UPDATE_NOTE,
    )
    is_active: Optional[bool] = Field(
        None, description="Set false to deactivate, which hides the tournament from players." + _UPDATE_NOTE,
    )
    players_per_match: Optional[int] = Field(None, description="How many players a match has." + _UPDATE_NOTE)
    required_commentators: Optional[int] = Field(default=None, ge=0, description=_CREW_DESC + _UPDATE_NOTE)
    required_trackers: Optional[int] = Field(default=None, ge=0, description=_CREW_DESC + _UPDATE_NOTE)
    event_start_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    event_end_date: Optional[date] = Field(default=None, description=_DATE_DESC)
    tournament_hours: Optional[Dict[date, Tuple[str, str]]] = Field(
        default=None, description=_HOURS_DESC,
    )
    signups_open_at: Optional[datetime] = Field(default=None, description=_SIGNUP_DESC)
    signups_close_at: Optional[datetime] = Field(default=None, description=_SIGNUP_DESC)


class MembershipRequest(BaseModel):
    user_id: int = Field(..., description="ID of the user to add as tournament admin or crew coordinator.")
