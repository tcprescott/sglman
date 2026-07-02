"""Liveness/readiness probe.

Unauthenticated so orchestrators and the container HEALTHCHECK can poll it. A
trivial DB round-trip proves the app can actually reach Postgres, not merely
that the process is up.
"""

from fastapi import APIRouter, HTTPException, status
from tortoise import connections

router = APIRouter(tags=['health'])


@router.get('/health')
async def health() -> dict:
    try:
        await connections.get('default').execute_query('SELECT 1')
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='database unavailable',
        )
    return {'status': 'ok'}
