"""Discord events endpoints: per-tournament opt-in + on-demand reconcile.

All routes delegate to :class:`DiscordEventSyncService`, which gates every
operation on ``AuthService.can_manage_sync`` (STAFF / super-admin / ``SYNC_ADMIN``)
and audits mutations. Reads take any token (``require_api_actor``); writes reject
read-only tokens (``require_write_actor``). Tenancy comes from the token.
"""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.discord_events import (
    DiscordEventTournamentResponse,
    DiscordEventTournamentUpdateRequest,
    DiscordScheduledEventResponse,
    ReconcileResultResponse,
)
from application.services import DiscordEventSyncService
from models import User

router = APIRouter(prefix="/discord-events", tags=["Discord events"], route_class=ServiceErrorRoute)


@router.get(
    "/tournaments",
    response_model=List[DiscordEventTournamentResponse],
    summary="List tournaments with their Discord-events settings",
)
async def list_tournaments(actor: User = Depends(require_api_actor)):
    return await DiscordEventSyncService().list_tournaments(actor)


@router.get(
    "/events",
    response_model=List[DiscordScheduledEventResponse],
    summary="List mirrored Discord Scheduled Event links",
)
async def list_events(actor: User = Depends(require_api_actor)):
    return await DiscordEventSyncService().list_events(actor)


@router.patch(
    "/tournaments/{tournament_id}",
    response_model=DiscordEventTournamentResponse,
    summary="Update a tournament's Discord-events settings",
)
async def update_tournament_settings(
    tournament_id: int,
    body: DiscordEventTournamentUpdateRequest,
    actor: User = Depends(require_write_actor),
):
    return await DiscordEventSyncService().update_settings(
        actor, tournament_id, **body.model_dump(exclude_unset=True)
    )


@router.post(
    "/reconcile",
    response_model=ReconcileResultResponse,
    summary="Reconcile the tenant's Discord events now",
)
async def reconcile_now(actor: User = Depends(require_write_actor)):
    result = await DiscordEventSyncService().reconcile_now(actor)
    return result.as_dict()
