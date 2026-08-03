"""Equipment lending endpoints — inventory, checkout, and loan history.

Gated by the ``EQUIPMENT`` feature flag at the router (the whole group 404s for
a community that has not enabled it) and again inside ``EquipmentService``.

**Reads take any token.** The gate of record is the home **Equipment** tab,
which is ungated by role — every member of a community with the feature on can
see the inventory and who currently holds each item. The one thing that is not
world-readable is ``private_notes``, which the web shows only to a caller who
passes ``can_manage_equipment``; this router applies the same rule per field
rather than hiding the whole asset.

**Writes reject read-only tokens here and are re-gated in the service**
(``can_manage_equipment`` for asset management, ``can_checkout_equipment`` /
``can_checkin_equipment`` for the lending workflow). Checkout deliberately stays
at the coarse HTTP gate: any member may check an asset out to themselves and only
a manager may name a ``borrower_id``, and the service is what knows that.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.equipment import (
    EquipmentBulkCreateRequest,
    EquipmentCheckoutRequest,
    EquipmentCreateRequest,
    EquipmentDetailResponse,
    EquipmentResponse,
    EquipmentUpdateRequest,
    LoanResponse,
    MyCheckoutResponse,
)
from application.errors import require_found
from application.services import AuthService, EquipmentService
from models import Equipment, EquipmentLoan, EquipmentStatus, User

router = APIRouter(prefix="/equipment", tags=["Equipment"], route_class=ServiceErrorRoute)

# Loan rows carried in a response are capped so a long-lived asset cannot return
# an unbounded history; the caller pages with ?limit=.
MAX_LOAN_ROWS = 200


def _name(user: Optional[User]) -> Optional[str]:
    return user.preferred_name if user else None


def _serialize_loan(loan: EquipmentLoan) -> LoanResponse:
    return LoanResponse(
        id=loan.id,
        equipment_id=loan.equipment_id,  # type: ignore[attr-defined]
        borrower_id=loan.borrower_id,  # type: ignore[attr-defined]
        borrower_name=_name(getattr(loan, 'borrower', None)),
        checked_out_at=loan.checked_out_at,
        checked_out_by_name=_name(getattr(loan, 'checked_out_by', None)),
        checked_in_at=loan.checked_in_at,
        checked_in_by_name=_name(getattr(loan, 'checked_in_by', None)),
    )


def _serialize_asset(
    asset: Equipment,
    *,
    can_manage: bool,
    borrower: Optional[User] = None,
) -> EquipmentResponse:
    return EquipmentResponse(
        id=asset.id,
        asset_number=asset.asset_number,
        name=asset.name,
        status=getattr(asset.status, 'value', asset.status),
        description=asset.description,
        owner_user_id=asset.owner_user_id,  # type: ignore[attr-defined]
        owner_name=_name(getattr(asset, 'owner_user', None)),
        borrower_name=_name(borrower),
        private_notes=asset.private_notes if can_manage else None,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


async def _load_asset(equipment_id: int) -> Equipment:
    return require_found(await EquipmentService().get_asset(equipment_id), "Asset")


# --- Reads ----------------------------------------------------------------
# Literal single-segment routes are declared before parameterized ones.

@router.get("", response_model=List[EquipmentResponse], summary="List the equipment inventory")
async def list_equipment(
    status_filter: Optional[EquipmentStatus] = Query(
        None, alias="status", description="Filter to one asset status."
    ),
    actor: User = Depends(require_api_actor),
):
    service = EquipmentService()
    assets = await service.list_assets()
    open_loans = await service.open_loans_by_equipment_id()
    can_manage = await AuthService.can_manage_equipment(actor)
    return [
        _serialize_asset(
            asset,
            can_manage=can_manage,
            borrower=getattr(open_loans.get(asset.id), 'borrower', None),
        )
        for asset in assets
        if status_filter is None
        or getattr(asset.status, 'value', asset.status) == status_filter.value
    ]


@router.get(
    "/me/checkouts",
    response_model=List[MyCheckoutResponse],
    summary="List the assets you currently hold",
)
async def my_checkouts(actor: User = Depends(require_api_actor)):
    return [
        MyCheckoutResponse(
            loan_id=loan.id,
            equipment_id=loan.equipment_id,
            asset_number=loan.equipment.asset_number,
            name=loan.equipment.name,
            checked_out_at=loan.checked_out_at,
        )
        for loan in await EquipmentService().my_checkouts(actor)
    ]


@router.get("/{equipment_id}", response_model=EquipmentDetailResponse, summary="Get one asset")
async def get_equipment(equipment_id: int, actor: User = Depends(require_api_actor)):
    service = EquipmentService()
    asset = await _load_asset(equipment_id)
    # The newest loan, read through the history so all three of its users are
    # fetched; it is the *current* one only while it is still open.
    newest = await service.loan_history(asset, limit=1)
    loan = newest[0] if newest and newest[0].checked_in_at is None else None
    base = _serialize_asset(
        asset,
        can_manage=await AuthService.can_manage_equipment(actor),
        borrower=getattr(loan, 'borrower', None),
    )
    return EquipmentDetailResponse(
        **base.model_dump(),
        current_loan=_serialize_loan(loan) if loan else None,
    )


@router.get(
    "/{equipment_id}/loans",
    response_model=List[LoanResponse],
    summary="List an asset's checkout history",
)
async def list_loans(
    equipment_id: int,
    limit: int = Query(50, ge=1, le=MAX_LOAN_ROWS, description="Maximum loans to return."),
    actor: User = Depends(require_api_actor),
):
    service = EquipmentService()
    asset = await _load_asset(equipment_id)
    loans = await service.loan_history(asset, limit=limit)
    return [_serialize_loan(loan) for loan in loans]


# --- Asset management -----------------------------------------------------

@router.post(
    "",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an asset",
)
async def create_equipment(
    body: EquipmentCreateRequest, actor: User = Depends(require_write_actor)
):
    asset = await EquipmentService().create_asset(
        actor,
        name=body.name,
        description=body.description,
        private_notes=body.private_notes,
        owner_user_id=body.owner_user_id,
    )
    return _serialize_asset(asset, can_manage=True)


@router.post(
    "/bulk",
    response_model=List[EquipmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create several identical assets at once",
)
async def bulk_create_equipment(
    body: EquipmentBulkCreateRequest, actor: User = Depends(require_write_actor)
):
    service = EquipmentService()
    assets = await service.bulk_create_assets(
        actor,
        name=body.name,
        count=body.count,
        description=body.description,
        private_notes=body.private_notes,
        owner_user_id=body.owner_user_id,
    )
    # ``bulk_create`` does not reliably populate primary keys on every backend,
    # so the response is built from a read-back rather than the in-memory rows.
    numbers = {asset.asset_number for asset in assets}
    return [
        _serialize_asset(asset, can_manage=True)
        for asset in await service.list_assets()
        if asset.asset_number in numbers
    ]


@router.put(
    "/{equipment_id}",
    response_model=EquipmentResponse,
    summary="Replace an asset's details",
    description=(
        "A full replace, not a partial edit: `description`, `private_notes` and "
        "`owner_user_id` are cleared when omitted. `status` is the exception — "
        "omit it to leave the status alone."
    ),
)
async def update_equipment(
    equipment_id: int,
    body: EquipmentUpdateRequest,
    actor: User = Depends(require_write_actor),
):
    asset = await EquipmentService().update_asset(
        actor,
        equipment_id,
        name=body.name,
        description=body.description,
        private_notes=body.private_notes,
        owner_user_id=body.owner_user_id,
        status=body.status,
    )
    return _serialize_asset(asset, can_manage=True)


@router.delete(
    "/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an asset",
)
async def delete_equipment(equipment_id: int, actor: User = Depends(require_write_actor)):
    await EquipmentService().delete_asset(actor, equipment_id)


# --- Lending --------------------------------------------------------------

@router.post(
    "/{equipment_id}/checkout",
    response_model=LoanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check an asset out",
)
async def checkout_equipment(
    equipment_id: int,
    body: Optional[EquipmentCheckoutRequest] = None,
    actor: User = Depends(require_write_actor),
):
    service = EquipmentService()
    await service.checkout(
        actor, equipment_id, borrower_id=body.borrower_id if body else None,
    )
    # Read the loan back rather than serializing the freshly created row: the
    # response names three users and only a fetched row has all of them.
    asset = await _load_asset(equipment_id)
    return _serialize_loan((await service.loan_history(asset, limit=1))[0])


@router.post(
    "/{equipment_id}/checkin",
    response_model=EquipmentDetailResponse,
    summary="Check an asset back in",
)
async def checkin_equipment(equipment_id: int, actor: User = Depends(require_write_actor)):
    asset = await EquipmentService().checkin(actor, equipment_id)
    base = _serialize_asset(
        asset, can_manage=await AuthService.can_manage_equipment(actor),
    )
    return EquipmentDetailResponse(**base.model_dump(), current_loan=None)
