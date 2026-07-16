"""Auto-open worker for scheduled racetime rooms (PR 6).

A lightweight background loop (modeled on ``volunteer_reminder``) that opens a
racetime room ahead of each eligible scheduled match. Opt-in per tournament
(``racetime_auto_create_rooms`` + ``room_open_minutes_before``); a match is
eligible only when **all** its entrants have a linked racetime identity. The
worker is idempotent (one ``RacetimeRoom`` per match — creation returns the
existing room), tenant-safe (each match's work runs inside ``tenant_scope``), and
crash-resilient (a per-match failure is logged and retried next tick).

Rescheduling a match with an already-open room keeps the room — the worker never
creates a second one, and it does not touch an existing room's time.
"""

import logging
from datetime import datetime, timedelta, timezone

from application.utils.background_loop import for_each_tenant_scoped, run_worker_loop

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

# Wide cross-tenant scan window; each match is re-checked against ITS tournament's
# room_open_minutes_before lead before a room is opened. A small grace on the
# lower bound lets a brief worker outage still catch a just-passed start.
MAX_LEAD_MINUTES = 7 * 24 * 60
GRACE_MINUTES = 15


async def _tick() -> None:
    from application.repositories import RacetimeRoomRepository
    from application.services.feature_flag_service import FeatureFlagService
    from application.services.race_room_service import RaceRoomService
    from application.services.user_service import UserService
    from models import FeatureFlag

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=GRACE_MINUTES)
    window_end = now + timedelta(minutes=MAX_LEAD_MINUTES)

    repo = RacetimeRoomRepository()
    candidates = await repo.matches_due_for_auto_open(window_start, window_end)
    if not candidates:
        return

    service = RaceRoomService()
    system_user = await UserService().get_system_user()

    async def _open(match) -> None:
        if not await FeatureFlagService().is_enabled(FeatureFlag.RACETIME_ROOMS):
            return  # tenant has racetime rooms disabled
        lead = match.tournament.room_open_minutes_before or 30
        if match.scheduled_at is None or match.scheduled_at > now + timedelta(minutes=lead):
            return  # not yet within this tournament's lead window
        if await repo.get_by_match(match) is not None:
            return  # idempotent: a room already exists
        bot = await match.tournament.racetime_bot
        if bot is None:
            return  # no authorized bot to host the room
        players = list(match.players)
        if not players or not all(
            getattr(p.user, 'racetime_user_id', None) for p in players
        ):
            # Eligibility gate: every entrant must have linked racetime.
            logger.info(
                'auto-open skipped for match %s: not all entrants have '
                'linked racetime', match.id,
            )
            return
        await service.create_room_for_match(match, actor=system_user)
        logger.info('auto-opened racetime room for match %s', match.id)

    await for_each_tenant_scoped(
        candidates,
        _open,
        tenant_id_of=lambda match: match.tenant_id,
        logger=logger,
        describe=lambda match: f'match {getattr(match, "id", None)}',
    )


_loop = run_worker_loop(_tick, TICK_SECONDS, 'race room auto-open', logger)


def start() -> None:
    _loop.start()


async def stop() -> None:
    await _loop.stop()
