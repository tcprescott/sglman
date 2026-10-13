"""Schemas for volunteer scheduling endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Re-exported for callers that import the availability schemas from this module.
from api.schemas.common import AvailabilityWindowInput as AvailabilityWindowInput
from api.schemas.common import SetAvailabilityRequest as SetAvailabilityRequest
from models import VolunteerAvailabilityStatus

# --- Positions ------------------------------------------------------------

class VolunteerPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: int
    is_active: bool
    shift_length_minutes: Optional[int] = None
    stagger_minutes: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class VolunteerPositionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: int = 0
    is_active: bool = True
    shift_length_minutes: Optional[int] = None
    stagger_minutes: Optional[int] = None


class VolunteerPositionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    shift_length_minutes: Optional[int] = None
    stagger_minutes: Optional[int] = None


# --- Assignments ----------------------------------------------------------

class VolunteerAssignmentResponse(BaseModel):
    id: int
    shift_id: int
    user_id: int
    user_name: Optional[str] = None
    auto_generated: bool
    acknowledged_at: Optional[datetime] = None
    reminder_sent_at: Optional[datetime] = None
    checked_in_at: Optional[datetime] = None
    checked_in_by_id: Optional[int] = None
    created_at: datetime

    @classmethod
    def from_row(cls, a) -> 'VolunteerAssignmentResponse':
        """Shared by the REST router and the MCP ``check_in_volunteer`` tool."""
        user = a.user if a.user_id and hasattr(a, 'user') else None
        return cls(
            id=a.id,
            shift_id=a.shift_id,
            user_id=a.user_id,
            user_name=(user.preferred_name if user else None),
            auto_generated=a.auto_generated,
            acknowledged_at=a.acknowledged_at,
            reminder_sent_at=a.reminder_sent_at,
            checked_in_at=a.checked_in_at,
            checked_in_by_id=a.checked_in_by_id,
            created_at=a.created_at,
        )


class AssignRequest(BaseModel):
    user_id: int


class AssignResponse(BaseModel):
    assignment: VolunteerAssignmentResponse
    warnings: List[str] = Field(default_factory=list)


# --- Shifts ---------------------------------------------------------------

class VolunteerShiftResponse(BaseModel):
    id: int
    position_id: int
    position_name: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    label: Optional[str] = None
    slots_needed: int
    notes: Optional[str] = None
    filled: int
    assignments: List[VolunteerAssignmentResponse] = Field(default_factory=list)


class VolunteerShiftCreate(BaseModel):
    position_id: int
    starts_at: datetime
    ends_at: datetime
    label: Optional[str] = None
    slots_needed: int = 1
    notes: Optional[str] = None


# --- Availability ---------------------------------------------------------

class VolunteerAvailabilityResponse(BaseModel):
    id: int
    user_id: int
    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus
    note: Optional[str] = None


# --- Profile / coverage ---------------------------------------------------

class ReleaseAssignmentRequest(BaseModel):
    """Why you can no longer cover a shift. The coordinators see it."""

    reason: Optional[str] = None


class CoverageRow(BaseModel):
    shift_id: int
    position: str
    label: str
    starts_at: datetime
    ends_at: datetime
    filled: int
    needed: int
    understaffed: bool


class VolunteerHoursResponse(BaseModel):
    """Hours served against the community's comp tiers.

    ``hours`` counts published assignments once across overlaps, over the
    event window unless ``start``/``end`` narrow it.
    """

    user_id: int
    user_name: str
    hours: float
    tier_cleared: Optional[float] = None
    next_tier: Optional[float] = None
    hours_to_next: Optional[float] = None
