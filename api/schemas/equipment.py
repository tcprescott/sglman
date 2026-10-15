"""Schemas for equipment lending endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import EquipmentStatus


class LoanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Loan ID.")
    equipment_id: int = Field(..., description="ID of the asset on loan.")
    borrower_id: Optional[int] = Field(None, description="User ID of the person holding the asset.")
    borrower_name: Optional[str] = Field(None, description="Display name of the borrower.")
    checked_out_at: Optional[datetime] = Field(None, description="When it was checked out (UTC).")
    checked_out_by_name: Optional[str] = Field(
        None, description="Display name of whoever recorded the checkout."
    )
    checked_in_at: Optional[datetime] = Field(
        None, description="When it was checked back in (UTC); null while the loan is open."
    )
    checked_in_by_name: Optional[str] = Field(
        None, description="Display name of whoever checked it back in; null while the loan is open."
    )


class EquipmentResponse(BaseModel):
    id: int = Field(..., description="Asset ID.")
    asset_number: int = Field(
        ..., description="The community's sequential number for the asset, as printed on its label."
    )
    name: str = Field(..., description="Asset name.")
    status: str = Field(
        ..., description="Current status: `available`, `checked_out` or `retired`."
    )
    description: Optional[str] = Field(None, description="Public description of the asset.")
    owner_user_id: Optional[int] = Field(
        None, description="User ID of the member who owns it; null when the community owns it."
    )
    owner_name: Optional[str] = Field(None, description="Display name of the owner, if any.")
    borrower_name: Optional[str] = Field(
        default=None, description="Who currently holds it, when it is checked out."
    )
    private_notes: Optional[str] = Field(
        default=None,
        description=(
            "Staff-only notes. Returned only to Staff and Equipment managers; "
            "null for everyone else."
        ),
    )
    created_at: datetime = Field(..., description="When the asset was added (UTC).")
    updated_at: datetime = Field(..., description="When the asset was last changed (UTC).")


class EquipmentDetailResponse(EquipmentResponse):
    current_loan: Optional[LoanResponse] = Field(
        None, description="The open loan while the asset is checked out; null otherwise."
    )


class EquipmentCreateRequest(BaseModel):
    name: str = Field(..., description="Asset name. Must not be blank.")
    description: Optional[str] = Field(None, description="Public description of the asset.")
    private_notes: Optional[str] = Field(
        None, description="Notes only Staff and Equipment managers can read."
    )
    owner_user_id: Optional[int] = Field(
        None,
        description="User ID of the member who owns it. Leave out when the community owns it.",
    )


class EquipmentBulkCreateRequest(EquipmentCreateRequest):
    count: int = Field(ge=1, le=200, description="How many identical assets to create.")


class EquipmentUpdateRequest(BaseModel):
    name: str = Field(..., description="Asset name. Must not be blank.")
    description: Optional[str] = Field(
        None, description="Public description. Cleared when omitted."
    )
    private_notes: Optional[str] = Field(
        None, description="Notes only Staff and Equipment managers can read. Cleared when omitted."
    )
    owner_user_id: Optional[int] = Field(
        None,
        description=(
            "User ID of the member who owns it. Omit to make it community-owned."
        ),
    )
    status: Optional[EquipmentStatus] = Field(
        default=None,
        description=(
            "New status: `available` or `retired`. Omit to leave it unchanged. Cannot move "
            "an asset into or out of `checked_out`; use the checkout and check-in "
            "endpoints for that."
        ),
    )


class EquipmentCheckoutRequest(BaseModel):
    borrower_id: Optional[int] = Field(
        default=None,
        description=(
            "User ID of the borrower. Leave out to check it out to yourself. Naming "
            "someone else needs Staff or Equipment manager and is refused otherwise."
        ),
    )


class MyCheckoutResponse(BaseModel):
    """One asset the caller currently holds."""

    loan_id: int = Field(..., description="ID of the open loan.")
    equipment_id: int = Field(..., description="Asset ID.")
    asset_number: int = Field(..., description="The asset's number, as printed on its label.")
    name: str = Field(..., description="Asset name.")
    checked_out_at: Optional[datetime] = Field(None, description="When you checked it out (UTC).")


EquipmentListResponse = List[EquipmentResponse]
