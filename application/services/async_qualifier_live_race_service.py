"""Async Qualifier Live Race Service — synchronous racetime qualifier runs (PR 10).

A pool permalink can be raced **live** on racetime instead of self-paced: every
entrant runs the same seed in one room, and the racetime result is captured back
into per-entrant :class:`~models.AsyncQualifierRun` rows. This service owns that
lifecycle, **reusing the PR 4/6 racetime subsystem** rather than a second
integration:

- **Author** (``create_live_race``) — an admin schedules a race for a pool,
  optionally pinning the permalink and an SG episode. Gated by
  :meth:`AuthService.can_admin_qualifier`.
- **Open** (``open_room``) — creates a :class:`~models.RacetimeRoom` (with
  ``match=None``) using one of the tenant's authorized bots; its slug is mirrored
  onto the live race so the shared inbound-event handler routes room events here.
- **Capture** (``record_finish``) — maps each racetime entrant to a ``User``,
  records status + elapsed time into an ``AsyncQualifierRun``, then par-scores.
  **Live-race runs skip reviewer sign-off** — the racetime result is
  self-attributing — so they are written ``APPROVED`` directly. Recording is
  **refused while any entrant is still racing** ("record again later").

Raises :class:`ValueError` for user errors and :class:`PermissionError` for
authz. Audits every transition; the captured-finish emits
``async_qualifier.live_race_recorded`` on the event bus.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.repositories import (
    AsyncQualifierLiveRaceRepository,
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierRunRepository,
    RacetimeRoomRepository,
)
from application.services import async_qualifier_access as access
from application.services.async_qualifier_service import AsyncQualifierService
from application.services.audit_service import AuditActions, AuditService
from application.services.racetime_bot_service import RacetimeBotService
from application.services.user_service import UserService
from application.tenant_context import require_tenant_id
from application.utils.racetime_entrants import unmatched_handle
from models import (
    AsyncQualifier,
    AsyncQualifierLiveRace,
    AsyncQualifierLiveRaceStatus,
    AsyncQualifierPool,
    AsyncQualifierRun,
    AsyncQualifierReviewStatus,
    AsyncQualifierRunStatus,
    RaceRoomStatus,
    User,
)
from racetimebot.transport import EntrantStatus, RaceEntrant

logger = logging.getLogger(__name__)

# racetime entrant outcome → qualifier run status. IN_PROGRESS is deliberately
# absent: a still-racing entrant blocks recording entirely.
_ENTRANT_TO_RUN_STATUS = {
    EntrantStatus.DONE: AsyncQualifierRunStatus.FINISHED,
    EntrantStatus.DID_NOT_FINISH: AsyncQualifierRunStatus.FORFEIT,
    EntrantStatus.DISQUALIFIED: AsyncQualifierRunStatus.DISQUALIFIED,
}


class AsyncQualifierLiveRaceService:
    """Author, open, and capture synchronous racetime qualifier races."""

    def __init__(self) -> None:
        self.repository = AsyncQualifierLiveRaceRepository()
        self.qualifier_repository = AsyncQualifierRepository()
        self.pool_repository = AsyncQualifierPoolRepository()
        self.permalink_repository = AsyncQualifierPermalinkRepository()
        self.run_repository = AsyncQualifierRunRepository()
        self.room_repository = RacetimeRoomRepository()
        self.bot_service = RacetimeBotService()
        self.qualifier_service = AsyncQualifierService()
        self.audit_service = AuditService()

    # ============================================================ management

    async def list_live_races(
        self, actor: Optional[User], qualifier_id: int
    ) -> List[AsyncQualifierLiveRace]:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        return await self.repository.list_for_qualifier(qualifier_id)

    async def get_live_race(self, actor: Optional[User], live_race_id: int) -> AsyncQualifierLiveRace:
        live_race, qualifier = await self._require_live_race_admin(actor, live_race_id)
        return live_race

    async def list_runs(self, actor: Optional[User], live_race_id: int) -> List[AsyncQualifierRun]:
        await self._require_live_race_admin(actor, live_race_id)
        return await self.run_repository.list_for_live_race(live_race_id)

    async def create_live_race(
        self,
        actor: Optional[User],
        pool_id: int,
        *,
        match_title: str,
        permalink_id: Optional[int] = None,
        episode_id: Optional[int] = None,
    ) -> AsyncQualifierLiveRace:
        pool = await self._require_pool(pool_id)
        qualifier = await self._require_qualifier(pool.qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        match_title = (match_title or '').strip()
        if not match_title:
            raise ValueError("A race title is required")
        if permalink_id is not None:
            permalink = await self.permalink_repository.get_by_id(permalink_id)
            if permalink is None or permalink.pool_id != pool_id:
                raise ValueError("Permalink does not belong to this pool")
        live_race = await self.repository.create(
            pool_id=pool_id,
            permalink_id=permalink_id,
            match_title=match_title,
            episode_id=episode_id,
            status=AsyncQualifierLiveRaceStatus.SCHEDULED,
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_LIVE_RACE_CREATED,
            {'live_race_id': live_race.id, 'pool_id': pool_id, 'qualifier_id': qualifier.id},
        )
        return live_race

    async def open_room(self, actor: Optional[User], live_race_id: int) -> AsyncQualifierLiveRace:
        """Open a racetime room for the live race, reusing the shared subsystem.

        Creates a :class:`~models.RacetimeRoom` (``match=None``) named by one of
        the tenant's authorized bots and mirrors its slug onto the live race so
        inbound room events route back here. Idempotent — a race that already has
        a slug is returned unchanged.
        """
        live_race, qualifier = await self._require_live_race_admin(actor, live_race_id)
        if live_race.racetime_slug:
            return live_race
        bots = await self.bot_service.list_authorized_for_tenant(require_tenant_id())
        if not bots:
            raise ValueError("No racetime bot is authorized for this community")
        bot = bots[0]
        slug = f'{bot.category}/qualifier-live-{live_race.id}'
        await self.room_repository.create(
            bot_id=bot.id,
            slug=slug,
            category=bot.category,
            room_name=live_race.match_title,
            status=RaceRoomStatus.OPEN,
            match_id=None,
            opened_at=datetime.now(timezone.utc),
        )
        live_race = await self.repository.update(
            live_race, racetime_slug=slug, status=AsyncQualifierLiveRaceStatus.PENDING
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_LIVE_RACE_OPENED,
            {'live_race_id': live_race.id, 'slug': slug, 'category': bot.category},
        )
        return live_race

    async def cancel_live_race(self, actor: Optional[User], live_race_id: int) -> None:
        live_race, qualifier = await self._require_live_race_admin(actor, live_race_id)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_LIVE_RACE_CANCELLED,
            {'live_race_id': live_race.id, 'qualifier_id': qualifier.id},
        )
        await self.repository.delete(live_race)

    # =============================================================== capture

    async def mark_in_progress(self, live_race: AsyncQualifierLiveRace) -> AsyncQualifierLiveRace:
        """Move a live race to IN_PROGRESS (driven by the room's start event)."""
        if live_race.status == AsyncQualifierLiveRaceStatus.FINISHED:
            return live_race
        return await self.repository.update(
            live_race, status=AsyncQualifierLiveRaceStatus.IN_PROGRESS
        )

    async def record_finish(
        self,
        live_race: AsyncQualifierLiveRace,
        entrants: List[RaceEntrant],
        *,
        actor: Optional[User] = None,
    ) -> List[AsyncQualifierRun]:
        """Capture a finished live race's entrants into runs, then par-score.

        Maps each racetime entrant to a ``User`` (by ``racetime_user_id``),
        records the outcome (done→finished, dnf→forfeit, dq→disqualified) with the
        reported elapsed time, and writes the run ``APPROVED`` (live-race runs skip
        review). Refuses to record while any entrant is still racing so a partial
        room never scores. Entrants with no linked ``User`` are surfaced in the
        audit detail for staff reconcile.
        """
        if any(e.status == EntrantStatus.IN_PROGRESS for e in entrants):
            raise ValueError("An entrant is still racing — record again once the race finishes")
        actor = actor or await UserService().get_system_user()
        qualifier = await self._require_qualifier(await self._qualifier_id_of(live_race))
        now = datetime.now(timezone.utc)

        existing = {r.user_id: r for r in await self.run_repository.list_for_live_race(live_race.id)}
        by_rtid = await self._users_by_racetime_id(entrants)
        captured: List[AsyncQualifierRun] = []
        unmatched: List[str] = []
        for entrant in entrants:
            user = by_rtid.get(entrant.user_id)
            if user is None:
                unmatched.append(unmatched_handle(entrant))
                continue
            run_status = _ENTRANT_TO_RUN_STATUS.get(entrant.status)
            if run_status is None:
                continue
            elapsed = entrant.finish_time if run_status == AsyncQualifierRunStatus.FINISHED else None
            # A non-finisher (forfeit/DQ) scores zero immediately; a finisher is
            # scored by the par recompute below.
            score = None if run_status == AsyncQualifierRunStatus.FINISHED else 0.0
            fields = dict(
                status=run_status,
                review_status=AsyncQualifierReviewStatus.APPROVED,
                finished_at=now,
                elapsed_seconds=elapsed,
                score=score,
                reviewed_by_id=actor.id,
                reviewed_at=now,
            )
            run = existing.get(user.id)
            if run is not None:
                run = await self.run_repository.update(run, **fields)
            else:
                run = await self.run_repository.create(
                    qualifier_id=qualifier.id,
                    user_id=user.id,
                    permalink_id=live_race.permalink_id,
                    live_race_id=live_race.id,
                    started_at=now,
                    **fields,
                )
            captured.append(run)

        if live_race.permalink_id is not None:
            await self.qualifier_service.recompute_par_and_scores(live_race.permalink_id)
            # Recompute scores sibling run instances, so reload the captured runs
            # to return their post-score state.
            captured = await self.run_repository.list_for_live_race(live_race.id)

        live_race = await self.repository.update(
            live_race, status=AsyncQualifierLiveRaceStatus.FINISHED
        )
        detail = {
            'live_race_id': live_race.id,
            'qualifier_id': qualifier.id,
            'captured': len(captured),
            'unmatched_handles': unmatched,
        }
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_LIVE_RACE_RECORDED, detail,
        )
        event_bus.publish(Event.create(EventType.ASYNC_QUALIFIER_LIVE_RACE_RECORDED, detail, actor))
        return captured

    # ============================================================= internals

    async def _users_by_racetime_id(self, entrants: List[RaceEntrant]) -> dict:
        ids = {e.user_id for e in entrants if e.user_id}
        by_rtid: dict = {}
        for user in await User.filter(racetime_user_id__in=list(ids)):
            if user.racetime_user_id:
                by_rtid[user.racetime_user_id] = user
        return by_rtid

    async def _qualifier_id_of(self, live_race: AsyncQualifierLiveRace) -> int:
        pool = getattr(live_race, 'pool', None)
        if isinstance(pool, AsyncQualifierPool):
            return pool.qualifier_id
        loaded = require_found(
            await self.pool_repository.get_by_id(live_race.pool_id), "Live race pool"
        )
        return loaded.qualifier_id

    async def _require_qualifier(self, qualifier_id: int) -> AsyncQualifier:
        return await access.require_qualifier(self.qualifier_repository, qualifier_id)

    async def _require_pool(self, pool_id: int) -> AsyncQualifierPool:
        return await access.require_pool(self.pool_repository, pool_id)

    async def _require_live_race_admin(self, actor: Optional[User], live_race_id: int):
        live_race = require_found(await self.repository.get_by_id(live_race_id), "Live race")
        qualifier = await self._require_qualifier(await self._qualifier_id_of(live_race))
        await access.ensure_qualifier_admin(actor, qualifier)
        return live_race, qualifier
