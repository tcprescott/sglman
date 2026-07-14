"""Service health endpoints.

The full board is SUPER_ADMIN-only; a tenant's STAFF get a read-only subset
scoped to the services their tenant depends on. The HTTP dependency is the
authorization gate here — the service methods do not re-gate.
"""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import (
    ServiceErrorRoute,
    require_staff,
    require_super_admin,
    require_super_admin_write,
)
from api.schemas.service_health import ProbeResultResponse
from application.services import ServiceHealthService
from application.tenant_context import require_tenant_id
from models import User

router = APIRouter(prefix="/service-health", tags=["Service health"], route_class=ServiceErrorRoute)


@router.get("", response_model=List[ProbeResultResponse], summary="Health subset for your tenant")
async def tenant_health(actor: User = Depends(require_staff)):
    results = await ServiceHealthService().tenant_subset(require_tenant_id())
    return [r.as_dict() for r in results]


@router.get("/board", response_model=List[ProbeResultResponse], summary="Full platform health board")
async def health_board(actor: User = Depends(require_super_admin)):
    results = ServiceHealthService().snapshot()
    return [r.as_dict() for r in results]


@router.post("/refresh", response_model=List[ProbeResultResponse], summary="Force a probe refresh")
async def refresh_health(actor: User = Depends(require_super_admin_write)):
    results = await ServiceHealthService().refresh(alert=False)
    return [r.as_dict() for r in results]
