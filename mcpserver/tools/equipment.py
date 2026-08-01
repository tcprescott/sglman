"""Equipment inventory reads.

Gated at **actor** behind the ``EQUIPMENT`` flag, mirroring
``api/routers/equipment.py`` and the home **Equipment** tab it shares a gate
with. That tab carries no role check at all: in a community with the feature on,
every member sees the inventory and who currently holds each item. These tools
were originally ADMIN on the belief that the *admin* equipment tab was the gate
of record; it is not, and the stricter gate only meant a member could see less
through a connected client than in their own browser. ``private_notes`` — the
one part of an asset that really is staff-only — stays out of both shapes.

``EquipmentService`` carries its own ``@requires_feature`` on every read, so the
flag is enforced twice — once at the registry gate, once in the owning service.
That is the intended shape, not redundancy: the registry hides the tool, the
service is what makes the hiding true for every other caller.
"""

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from application.errors import require_found
from application.services import EquipmentService
from mcpserver.auth import Gate
from mcpserver.registry import register
from mcpserver.schemas import EquipmentDetail, EquipmentSummary, LoanRecord, TenantArg
from models import EquipmentStatus, FeatureFlag


def _name(user) -> Optional[str]:
    return user.preferred_name if user else None


def _loan(loan) -> LoanRecord:
    return LoanRecord(
        id=loan.id,
        borrower=_name(getattr(loan, 'borrower', None)),
        checked_out_at=loan.checked_out_at,
        checked_out_by=_name(getattr(loan, 'checked_out_by', None)),
        checked_in_at=loan.checked_in_at,
        checked_in_by=_name(getattr(loan, 'checked_in_by', None)),
    )


async def list_equipment(
    tenant: TenantArg = None,
    status: Optional[str] = None,
) -> List[EquipmentSummary]:
    """List the community's equipment inventory and who currently holds each item.

    `status` filters on the asset's state: `available`, `checked_out`, or
    `retired`.
    """
    wanted: Optional[str] = None
    if status:
        try:
            wanted = EquipmentStatus(status.strip().lower()).value
        except ValueError as exc:
            valid = ', '.join(s.value for s in EquipmentStatus)
            raise ValueError(
                f"Unknown status '{status}'. Valid: {valid}"
            ) from exc

    service = EquipmentService()
    assets = await service.list_assets()
    open_loans = await service.open_loans_by_equipment_id()
    return [
        EquipmentSummary(
            id=asset.id,
            asset_number=asset.asset_number,
            name=asset.name,
            status=getattr(asset.status, 'value', asset.status),
            owner=_name(getattr(asset, 'owner_user', None)),
            borrower=_name(getattr(open_loans.get(asset.id), 'borrower', None)),
        )
        for asset in assets
        if wanted is None or getattr(asset.status, 'value', asset.status) == wanted
    ]


async def get_equipment(
    equipment_id: int,
    tenant: TenantArg = None,
) -> EquipmentDetail:
    """Get one asset with its full checkout history, most recent first."""
    service = EquipmentService()
    asset = require_found(await service.get_asset(equipment_id), 'Equipment')
    loans = await service.loan_history(asset)
    open_loan = next((loan for loan in loans if loan.checked_in_at is None), None)
    return EquipmentDetail(
        id=asset.id,
        asset_number=asset.asset_number,
        name=asset.name,
        status=getattr(asset.status, 'value', asset.status),
        owner=_name(getattr(asset, 'owner_user', None)),
        borrower=_name(getattr(open_loan, 'borrower', None)),
        description=asset.description,
        loans=[_loan(loan) for loan in loans],
    )


def register_tools(mcp: FastMCP) -> None:
    register(
        mcp, list_equipment, gate=Gate.ACTOR,
        feature=FeatureFlag.EQUIPMENT, title='List equipment',
    )
    register(
        mcp, get_equipment, gate=Gate.ACTOR,
        feature=FeatureFlag.EQUIPMENT, title='Get equipment',
    )
