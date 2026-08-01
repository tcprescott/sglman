"""Schemas for equipment lending endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import EquipmentStatus


class LoanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    borrower_id: Optional[int] = None
    borrower_name: Optional[str] = None
    checked_out_at: Optional[datetime] = None
    checked_out_by_name: Optional[str] = None
    checked_in_at: Optional[datetime] = None
    checked_in_by_name: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: int
    asset_number: int
    name: str
    status: str
    description: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    borrower_name: Optional[str] = Field(
        default=None, description="Who currently holds it, when it is checked out."
    )
    private_notes: Optional[str] = Field(
        default=None,
        description=(
            "Staff-only notes. Returned only to a caller who can manage "
            "equipment; omitted for everyone else."
        ),
    )
    created_at: datetime
    updated_at: datetime


class EquipmentDetailResponse(EquipmentResponse):
    current_loan: Optional[LoanResponse] = None


class EquipmentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    private_notes: Optional[str] = None
    owner_user_id: Optional[int] = None


class EquipmentBulkCreateRequest(EquipmentCreateRequest):
    count: int = Field(ge=1, le=200, description="How many identical assets to create.")


class EquipmentUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    private_notes: Optional[str] = None
    owner_user_id: Optional[int] = None
    status: Optional[EquipmentStatus] = Field(
        default=None,
        description=(
            "New status. Cannot move an asset into or out of `checked_out` — "
            "use the checkout/check-in endpoints for that."
        ),
    )


class EquipmentCheckoutRequest(BaseModel):
    borrower_id: Optional[int] = Field(
        default=None,
        description=(
            "Who is borrowing it. Only an equipment manager may name someone "
            "else; anyone else checks out to themselves whatever this says."
        ),
    )


class MyCheckoutResponse(BaseModel):
    """One asset the caller currently holds."""

    loan_id: int
    equipment_id: int
    asset_number: int
    name: str
    checked_out_at: Optional[datetime] = None


EquipmentListResponse = List[EquipmentResponse]
