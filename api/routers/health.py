"""Liveness/readiness probe.

Unauthenticated so orchestrators and the container HEALTHCHECK can poll it. A
trivial DB round-trip proves the app can actually reach Postgres, not merely
that the process is up.
"""

from fastapi import APIRouter, HTTPException, status
from tortoise import connections

from api.schemas.health import HealthResponse

router = APIRouter(tags=['health'])


@router.get(
    '/health',
    response_model=HealthResponse,
    summary='Check the app is up',
    description=(
        "Reports whether the app is running and can reach its database, by running a trivial "
        "query against it. Meant for load balancers and container health checks.\n\n"
        "Fails with 503 when the database is unreachable.\n\n"
        "**Who can call this:** Anyone; no token needed."
    ),
)
async def health() -> HealthResponse:
    try:
        await connections.get('default').execute_query('SELECT 1')
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='database unavailable',
        ) from exc
    return HealthResponse(status='ok')
