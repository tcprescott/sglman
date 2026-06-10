"""Schemas for volunteer scheduling endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

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
    created_at: datetime
    updated_at: datetime


class VolunteerPositionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: int = 0
    is_active: bool = True


class VolunteerPositionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# --- Assignments ----------------------------------------------------------

class VolunteerAssignmentResponse(BaseModel):
    id: int
    shift_id: int
    user_id: int
    user_name: Optional[str] = None
    auto_generated: bool
    acknowledged_at: Optional[datetime] = None
    reminder_sent_at: Optional[datetime] = None
    created_at: datetime


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


class AvailabilityWindowInput(BaseModel):
    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus = VolunteerAvailabilityStatus.AVAILABLE
    note: Optional[str] = None


class SetAvailabilityRequest(BaseModel):
    windows: List[AvailabilityWindowInput] = Field(default_factory=list)


# --- Profile / coverage ---------------------------------------------------

class OptInRequest(BaseModel):
    note: Optional[str] = None


class VolunteerProfileResponse(BaseModel):
    user_id: int
    opted_in: bool
    opted_in_at: Optional[datetime] = None
    note: Optional[str] = None


class CoverageRow(BaseModel):
    shift_id: int
    position: str
    label: str
    starts_at: datetime
    ends_at: datetime
    filled: int
    needed: int
    understaffed: bool
