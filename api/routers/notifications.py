"""Tournament notification preference endpoints."""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.notifications import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from application.services import TournamentNotificationService
from models import User

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    route_class=ServiceErrorRoute,
)


@router.get(
    "/preferences",
    response_model=List[NotificationPreferenceResponse],
    summary="List your tournament notification preferences",
)
async def list_preferences(actor: User = Depends(require_api_actor)):
    return await TournamentNotificationService().get_user_preferences(actor)


@router.put(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Set your notification preference for a tournament",
)
async def upsert_preference(
    body: NotificationPreferenceUpdate, actor: User = Depends(require_write_actor),
):
    return await TournamentNotificationService().upsert_preference(
        user=actor,
        tournament_id=body.tournament_id,
        match_notifications=body.match_notifications,
    )
