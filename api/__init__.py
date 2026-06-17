"""SGL On Site REST API package.

Exposes a single ``router`` (aggregating every domain sub-router) that
``main.py`` mounts under ``/api``. Every endpoint is authenticated with a
personal bearer token; see :mod:`api.dependencies`.
"""

from fastapi import APIRouter, Depends

from api.rate_limit import rate_limit
from api.routers import (
    audit,
    crew,
    discord_role_mappings,
    match_actions,
    matches,
    notifications,
    player_availability,
    stream_room_actions,
    stream_rooms,
    system_config,
    tokens,
    tournament_actions,
    tournaments,
    triforce,
    users,
    volunteers,
)

router = APIRouter(dependencies=[Depends(rate_limit)])
router.include_router(matches.router)
router.include_router(match_actions.router)
router.include_router(crew.router)
router.include_router(tournaments.router)
router.include_router(tournament_actions.router)
router.include_router(stream_rooms.router)
router.include_router(stream_room_actions.router)
router.include_router(users.router)
router.include_router(player_availability.router)
router.include_router(triforce.router)
router.include_router(notifications.router)
router.include_router(audit.router)
router.include_router(system_config.router)
router.include_router(tokens.router)
router.include_router(volunteers.router)
router.include_router(discord_role_mappings.router)

__all__ = ['router']
