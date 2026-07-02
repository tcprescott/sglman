"""Volunteer scheduling endpoints."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.volunteers import (
    AssignRequest,
    AssignResponse,
    CoverageRow,
    OptInRequest,
    SetAvailabilityRequest,
    VolunteerAssignmentResponse,
    VolunteerAvailabilityResponse,
    VolunteerPositionCreate,
    VolunteerPositionResponse,
    VolunteerPositionUpdate,
    VolunteerProfileResponse,
    VolunteerShiftCreate,
    VolunteerShiftResponse,
)
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_position_service import VolunteerPositionService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer_schedule_service import VolunteerScheduleService
from models import User, VolunteerShift

router = APIRouter(
    prefix="/volunteers",
    tags=["Volunteers"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_api_actor)],
)


# --- response builders ----------------------------------------------------

def _assignment_resp(a) -> VolunteerAssignmentResponse:
    user = a.user if a.user_id and hasattr(a, 'user') else None
    return VolunteerAssignmentResponse(
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


def _shift_resp(s: VolunteerShift) -> VolunteerShiftResponse:
    assignments = list(s.assignments) if hasattr(s, 'assignments') else []
    return VolunteerShiftResponse(
        id=s.id,
        position_id=s.position_id,
        position_name=(s.position.name if s.position else None),
        starts_at=s.starts_at,
        ends_at=s.ends_at,
        label=s.label,
        slots_needed=s.slots_needed,
        notes=s.notes,
        filled=len(assignments),
        assignments=[_assignment_resp(a) for a in assignments],
    )


# --- Positions ------------------------------------------------------------

@router.get("/positions", response_model=List[VolunteerPositionResponse], summary="List volunteer positions")
async def list_positions(active_only: bool = Query(False)):
    service = VolunteerPositionService()
    positions = await (service.list_active() if active_only else service.list_all())
    return positions


@router.post("/positions", response_model=VolunteerPositionResponse, status_code=status.HTTP_201_CREATED, summary="Create a position")
async def create_position(payload: VolunteerPositionCreate, actor: User = Depends(require_write_actor)):
    return await VolunteerPositionService().create(actor, **payload.model_dump())


@router.patch("/positions/{position_id}", response_model=VolunteerPositionResponse, summary="Update a position")
async def update_position(position_id: int, payload: VolunteerPositionUpdate, actor: User = Depends(require_write_actor)):
    service = VolunteerPositionService()
    position = await service.get(position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return position
    return await service.update(actor, position, **fields)


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a position")
async def delete_position(position_id: int, actor: User = Depends(require_write_actor)):
    service = VolunteerPositionService()
    position = await service.get(position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    await service.delete(actor, position)


# --- Shifts ---------------------------------------------------------------

@router.get("/shifts", response_model=List[VolunteerShiftResponse], summary="List shifts in a window")
async def list_shifts(
    start: datetime = Query(..., description="Window start (UTC ISO 8601)"),
    end: datetime = Query(..., description="Window end (UTC ISO 8601)"),
):
    shifts = await VolunteerScheduleService().list_shifts_for_window(start, end)
    return [_shift_resp(s) for s in shifts]


@router.get("/shifts/{shift_id}", response_model=VolunteerShiftResponse, summary="Get a shift")
async def get_shift(shift_id: int):
    shift = await VolunteerScheduleService().get_shift(shift_id)
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    return _shift_resp(shift)


@router.post("/shifts", response_model=VolunteerShiftResponse, status_code=status.HTTP_201_CREATED, summary="Create a shift")
async def create_shift(payload: VolunteerShiftCreate, actor: User = Depends(require_write_actor)):
    service = VolunteerScheduleService()
    await service.create_shift(actor, **payload.model_dump())
    # Re-fetch with relations for a complete response.
    shifts = await service.list_shifts_for_window(payload.starts_at, payload.ends_at)
    created = next((s for s in shifts if s.position_id == payload.position_id
                    and s.starts_at == payload.starts_at), None)
    return _shift_resp(created) if created else _shift_resp(shifts[-1])


@router.delete("/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a shift")
async def delete_shift(shift_id: int, actor: User = Depends(require_write_actor)):
    service = VolunteerScheduleService()
    shift = await service.get_shift(shift_id)
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    await service.delete_shift(actor, shift)


# --- Assignments ----------------------------------------------------------

@router.post("/shifts/{shift_id}/assignments", response_model=AssignResponse, summary="Assign a volunteer to a shift")
async def assign(shift_id: int, payload: AssignRequest, actor: User = Depends(require_write_actor)):
    service = VolunteerScheduleService()
    shift = await service.get_shift(shift_id)
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    target = await User.get_or_none(id=payload.user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    assignment, warnings = await service.assign(actor, shift, target)
    assignment.user = target  # for the response name
    return AssignResponse(assignment=_assignment_resp(assignment), warnings=warnings)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove an assignment")
async def unassign(assignment_id: int, actor: User = Depends(require_write_actor)):
    service = VolunteerScheduleService()
    assignment = await service.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    await service.unassign(actor, assignment)


@router.post("/assignments/{assignment_id}/acknowledge", response_model=VolunteerAssignmentResponse, summary="Acknowledge your assignment")
async def acknowledge(assignment_id: int, actor: User = Depends(require_write_actor)):
    assignment = await VolunteerScheduleService().acknowledge(assignment_id, actor)
    return _assignment_resp(assignment)


# --- Coverage -------------------------------------------------------------

@router.get("/coverage", response_model=List[CoverageRow], summary="Per-shift coverage in a window")
async def coverage(
    start: datetime = Query(..., description="Window start (UTC ISO 8601)"),
    end: datetime = Query(..., description="Window end (UTC ISO 8601)"),
):
    return await VolunteerScheduleService().coverage(start, end)


# --- Self-service: profile, availability, assignments ---------------------

def _profile_resp(actor: User, profile) -> VolunteerProfileResponse:
    return VolunteerProfileResponse(
        user_id=actor.id,
        opted_in=profile.opted_in_at is not None,
        opted_in_at=profile.opted_in_at,
        note=profile.note,
    )


@router.get("/me/profile", response_model=VolunteerProfileResponse, summary="Get your volunteer profile")
async def my_profile(actor: User = Depends(require_api_actor)):
    profile = await VolunteerProfileService().get_or_create(actor)
    return _profile_resp(actor, profile)


@router.post("/me/opt-in", response_model=VolunteerProfileResponse, summary="Opt in to volunteering")
async def opt_in(payload: OptInRequest, actor: User = Depends(require_write_actor)):
    profile = await VolunteerProfileService().opt_in(actor, note=payload.note)
    return _profile_resp(actor, profile)


@router.post("/me/opt-out", response_model=VolunteerProfileResponse, summary="Opt out of volunteering")
async def opt_out(actor: User = Depends(require_write_actor)):
    profile = await VolunteerProfileService().opt_out(actor)
    return _profile_resp(actor, profile)


@router.get("/me/availability", response_model=List[VolunteerAvailabilityResponse], summary="List your availability windows")
async def my_availability(actor: User = Depends(require_api_actor)):
    return await VolunteerAvailabilityService().availability_for(actor)


@router.put("/me/availability", response_model=List[VolunteerAvailabilityResponse], summary="Replace your availability windows")
async def set_my_availability(payload: SetAvailabilityRequest, actor: User = Depends(require_write_actor)):
    windows = [(w.starts_at, w.ends_at, w.status, w.note) for w in payload.windows]
    return await VolunteerAvailabilityService().set_windows(actor, windows)


@router.get("/me/assignments", response_model=List[VolunteerAssignmentResponse], summary="List your upcoming shift assignments")
async def my_assignments(
    upcoming_only: bool = Query(True),
    actor: User = Depends(require_api_actor),
):
    after = datetime.now(timezone.utc) if upcoming_only else None
    assignments = await VolunteerScheduleService().assignments_for_user(actor, upcoming_after=after)
    return [_assignment_resp(a) for a in assignments]
