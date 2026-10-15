"""Schemas for tournament endpoints."""

from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class TournamentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="The tournament's ID.")
    name: str = Field(..., description="The tournament's name.")
    description: Optional[str] = Field(None, description="Long description shown to players, as markdown.")
    seed_generator: Optional[str] = Field(
        None,
        description=(
            "Key of the randomizer that rolls this tournament's seeds. When a preset is "
            "attached it is the preset's randomizer. Null when the tournament rolls no seeds."
        ),
    )
    is_active: bool = Field(..., description="Whether the tournament is running. Inactive tournaments are hidden from players.")
    players_per_match: int = Field(..., description="How many players a match in this tournament has.")
    bracket_url: Optional[str] = Field(None, description="Link to the tournament's external bracket page.")
    rules_url: Optional[str] = Field(None, description="Link to the tournament's rules.")
    tournament_format: Optional[str] = Field(None, description="Short free-text format label, such as \"Double elimination\".")
    triforce_access_message: Optional[str] = Field(
        None,
        description="Markdown shown to players who may not submit triforce texts, explaining how to get access.",
    )
    randomizer_notes: Optional[str] = Field(
        None, description="The randomizer settings, preset and build the tournament races on, as markdown.",
    )
    average_match_duration: Optional[int] = Field(
        None, description="Typical match length in minutes, used to plan the schedule and suggest start times.",
    )
    max_match_duration: Optional[int] = Field(None, description="Longest a match is expected to run, in minutes.")
    required_commentators: int = Field(
        ...,
        description=(
            "Approved commentators a streamed match needs before the coverage reports count it "
            "as covered. 0 means the tournament doesn't use the role."
        ),
    )
    required_trackers: int = Field(
        ...,
        description=(
            "Approved trackers a streamed match needs before the coverage reports count it "
            "as covered. 0 means the tournament doesn't use the role."
        ),
    )
    allow_player_match_requests: bool = Field(
        ...,
        description=(
            "Whether players may request their own matches with POST /matches/request. False once "
            "a bracket is attached, since the tournament then schedules only its own matchups."
        ),
    )
    event_start_date: Optional[date] = Field(
        None, description="First day of this tournament's event window. Null inherits the community's setting.",
    )
    event_end_date: Optional[date] = Field(
        None, description="Last day of this tournament's event window. Null inherits the community's setting.",
    )
    tournament_hours: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            'Per-day match hours as {"YYYY-MM-DD": ["HH:MM open", "HH:MM close"]}, on the '
            "community's clock. Null inherits the community's setting."
        ),
    )
    signups_open_at: Optional[datetime] = Field(
        None, description="When player self-signup opens (UTC). Null means signups are open now.",
    )
    signups_close_at: Optional[datetime] = Field(
        None, description="When player self-signup closes (UTC). Null means signups stay open.",
    )
    created_at: datetime = Field(..., description="When the tournament was created (UTC).")
    updated_at: datetime = Field(..., description="When the tournament was last changed (UTC).")
