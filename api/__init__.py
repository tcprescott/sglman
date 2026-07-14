"""SGL On Site REST API package.

Exposes a single ``router`` (aggregating every domain sub-router) that
``main.py`` mounts under ``/api``. Every endpoint is authenticated with a
personal bearer token; see :mod:`api.dependencies`.
"""

from fastapi import APIRouter, Depends

from api.dependencies import tenant_context_scope
from api.rate_limit import rate_limit
from api.routers import (
    async_qualifier_live_races,
    async_qualifiers,
    audit,
    crew,
    discord_events,
    discord_role_mappings,
    health,
    match_actions,
    matches,
    notifications,
    player_availability,
    presets,
    race_room_profiles,
    race_rooms,
    racetime_bots,
    seeds,
    service_health,
    speedgaming,
    stream_room_actions,
    stream_rooms,
    system_config,
    tokens,
    tournament_actions,
    tournaments,
    triforce,
    users,
    volunteers,
    webhooks,
)

router = APIRouter(dependencies=[Depends(rate_limit), Depends(tenant_context_scope)])
# Unauthenticated liveness probe (no auth dependency on this router).
router.include_router(health.router)
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
router.include_router(webhooks.router)

# --- online-tournament feature routers ---
router.include_router(presets.router)
router.include_router(race_room_profiles.router)
router.include_router(racetime_bots.router)
router.include_router(race_rooms.router)
router.include_router(speedgaming.router)
router.include_router(discord_events.router)
router.include_router(service_health.router)
router.include_router(seeds.router)
# Live-races MUST be registered before the async-qualifiers router: its literal
# ``/async-qualifiers/live-races`` prefix would otherwise be shadowed by the
# ``/async-qualifiers/{qualifier_id}`` int path param (a non-int segment 422s
# rather than falling through), so the more specific router is included first.
router.include_router(async_qualifier_live_races.router)
router.include_router(async_qualifiers.router)

__all__ = ['router']
