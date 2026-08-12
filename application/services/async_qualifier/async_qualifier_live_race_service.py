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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from application.errors import require_found
from application.events import EventType
from application.feature_flags import requires_feature
from application.repositories import (
    AsyncQualifierLiveRaceRepository,
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierRunRepository,
    RacetimeRoomRepository,
)
from application.services.async_qualifier import async_qualifier_access as access
from application.services.async_qualifier.async_qualifier_service import (
    MAX_RUN_SECONDS,
    AsyncQualifierService,
)
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
    AsyncQualifierReviewStatus,
    AsyncQualifierRun,
    AsyncQualifierRunStatus,
    FeatureFlag,
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

# What a human may assert about a racer — the same three outcomes racetime reports.
# In-progress is not one of them: a race being recorded by hand is over.
_MANUAL_STATUSES = frozenset(_ENTRANT_TO_RUN_STATUS.values())


@dataclass(frozen=True)
class ManualResult:
    """One racer's outcome as staff typed it, for :meth:`record_manual_finish`."""

    user_id: int
    status: AsyncQualifierRunStatus
    elapsed_seconds: Optional[int] = None


@dataclass(frozen=True)
class CapturedResult:
    """One racer's outcome with their ``User`` already resolved.

    The shape both capture paths converge on, so the racetime event and the manual
    control cannot end up applying different rules to the same result.
    """

    user: User
    status: AsyncQualifierRunStatus
    elapsed_seconds: Optional[int]


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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_live_races(
        self, actor: Optional[User], qualifier_id: int
    ) -> List[AsyncQualifierLiveRace]:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        return await self.repository.list_for_qualifier(qualifier_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_live_race(self, actor: Optional[User], live_race_id: int) -> AsyncQualifierLiveRace:
        live_race, qualifier = await self._require_live_race_admin(actor, live_race_id)
        return live_race

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_runs(self, actor: Optional[User], live_race_id: int) -> List[AsyncQualifierRun]:
        await self._require_live_race_admin(actor, live_race_id)
        return await self.run_repository.list_for_live_race(live_race_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def cancel_live_race(self, actor: Optional[User], live_race_id: int) -> None:
        live_race, qualifier = await self._require_live_race_admin(actor, live_race_id)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_LIVE_RACE_CANCELLED,
            {'live_race_id': live_race.id, 'qualifier_id': qualifier.id},
        )
        await self.repository.delete(live_race)

    # =============================================================== capture

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def mark_in_progress(self, live_race: AsyncQualifierLiveRace) -> AsyncQualifierLiveRace:
        """Move a live race to IN_PROGRESS (driven by the room's start event)."""
        if live_race.status == AsyncQualifierLiveRaceStatus.FINISHED:
            return live_race
        return await self.repository.update(
            live_race, status=AsyncQualifierLiveRaceStatus.IN_PROGRESS
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def mark_cancelled(self, live_race: AsyncQualifierLiveRace) -> AsyncQualifierLiveRace:
        """Move a live race to CANCELLED (driven by the room's cancellation event).

        The inbound handler used to update only the ``RacetimeRoom``, leaving the race
        at scheduled or in-progress forever — indistinguishable from one still to
        come, and with no admin control to resolve it. A race whose results were
        already captured is left alone: cancelling the room afterwards does not
        un-score the runs.
        """
        if live_race.status == AsyncQualifierLiveRaceStatus.FINISHED:
            return live_race
        return await self.repository.update(
            live_race, status=AsyncQualifierLiveRaceStatus.CANCELLED
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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
        room never scores. Entrants with no linked ``User`` are recorded on the race
        as ``unmatched_handles`` for staff to reconcile.
        """
        if any(e.status == EntrantStatus.IN_PROGRESS for e in entrants):
            raise ValueError("An entrant is still racing — record again once the race finishes")
        by_rtid = await self._users_by_racetime_id(entrants)
        resolved: List[CapturedResult] = []
        unmatched: List[str] = []
        for entrant in entrants:
            user = by_rtid.get(entrant.user_id)
            if user is None:
                unmatched.append(unmatched_handle(entrant))
                continue
            run_status = _ENTRANT_TO_RUN_STATUS.get(entrant.status)
            if run_status is None:
                continue
            resolved.append(CapturedResult(
                user=user,
                status=run_status,
                elapsed_seconds=(entrant.finish_time
                                 if run_status == AsyncQualifierRunStatus.FINISHED else None),
            ))
        return await self._capture(
            live_race, resolved, actor=actor, unmatched=unmatched, manual=False,
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def record_manual_finish(
        self,
        actor: Optional[User],
        live_race_id: int,
        results: Sequence['ManualResult'],
    ) -> List[AsyncQualifierRun]:
        """Record a live race's results by hand, for when the room's event never came.

        ``record_finish`` is reachable only from the inbound racetime FINISHED event,
        so a dropped connection, a bot restart mid-race or a room closed by hand left
        the race stuck and its entrants unscored with **no remedy anywhere** — not in
        the admin page and not over REST. This is that remedy: staff assert the
        results and everything downstream behaves identically, because it funnels
        through the same capture (the permalink requirement, the pool cap, the
        par recompute, the FINISHED transition).

        Audited under its own action, the same reasoning as a review override: a
        human asserting a result is a more contestable act than racetime reporting
        one, and "who typed this" is the question an appeal asks. Subscribers get the
        usual recorded event with ``manual: True``, since to them it is the same fact.
        """
        live_race, _ = await self._require_live_race_admin(actor, live_race_id)
        if not results:
            raise ValueError("Add at least one racer's result")
        resolved: List[CapturedResult] = []
        seen: set = set()
        for result in results:
            if result.user_id in seen:
                raise ValueError("A racer can only appear once in one race")
            seen.add(result.user_id)
            if result.status not in _MANUAL_STATUSES:
                raise ValueError("A result must be finished, forfeit or disqualified")
            elapsed = result.elapsed_seconds
            if result.status == AsyncQualifierRunStatus.FINISHED:
                if not elapsed or elapsed <= 0:
                    raise ValueError("A finisher needs a finish time")
                if elapsed > MAX_RUN_SECONDS:
                    raise ValueError("That finish time is longer than a week — check the value")
            else:
                # A forfeit or DQ has no time to record, and keeping one entered by
                # mistake would put a scoreable-looking number on a zero run.
                elapsed = None
            user = require_found(await UserService().get_user_by_id(result.user_id), "Racer")
            resolved.append(CapturedResult(
                user=user, status=result.status, elapsed_seconds=elapsed,
            ))
        return await self._capture(
            live_race, resolved, actor=actor, unmatched=[], manual=True,
        )

    async def _capture(
        self,
        live_race: AsyncQualifierLiveRace,
        resolved: List['CapturedResult'],
        *,
        actor: Optional[User],
        unmatched: List[str],
        manual: bool,
    ) -> List[AsyncQualifierRun]:
        """Write resolved results as approved runs, par-score, and record the capture.

        Shared by the racetime event and the manual control so the two cannot drift:
        whichever way a result arrives, the same rules decide whether it scores.
        """
        if live_race.permalink_id is None:
            # Recording without one produced runs with permalink_id NULL: no par to
            # score against, the recompute skipped, and the entrants invisible on the
            # board forever with nothing saying why. The dialog offers "(assign
            # later)", so later is now.
            raise ValueError(
                "This race has no permalink assigned, so its results cannot be scored. "
                "Assign one to the race, then record again."
            )
        actor = actor or await UserService().get_system_user()
        qualifier = await self._require_qualifier(await self._qualifier_id_of(live_race))
        now = datetime.now(timezone.utc)
        # Everyone in a race starts at the same instant, and the old code stamped
        # ``now`` as every run's start — so each one read Started == Finished with a
        # blank Timed column, and no live-race run had a duration on any screen. The
        # slowest finisher can only just have finished, so the race began at least
        # their elapsed time ago.
        times = [r.elapsed_seconds for r in resolved if r.elapsed_seconds]
        started_at = now - timedelta(seconds=max(times)) if times else now

        existing = {r.user_id: r for r in await self.run_repository.list_for_live_race(live_race.id)}
        over_cap = await self._over_pool_cap(
            live_race, qualifier, [r.user for r in resolved], existing,
        )
        voided: List[int] = []
        for result in resolved:
            user, run_status, elapsed = result.user, result.status, result.elapsed_seconds
            # A non-finisher (forfeit/DQ) scores zero immediately; a finisher is
            # scored by the par recompute below.
            score = None if run_status == AsyncQualifierRunStatus.FINISHED else 0.0
            fields = dict(
                status=run_status,
                review_status=AsyncQualifierReviewStatus.APPROVED,
                # A finisher's own finish is their start plus their time; a
                # non-finisher's is when the race was recorded.
                finished_at=started_at + timedelta(seconds=elapsed) if elapsed else now,
                elapsed_seconds=elapsed,
                # The racetime clock *is* the measurement here — there is no runner's
                # claim to hold it against, which is what it means elsewhere — so the
                # Timed column shows the raced time rather than a dash.
                measured_seconds=elapsed,
                score=score,
                reviewed_by_id=actor.id,
                reviewed_at=now,
            )
            if user.id in over_cap:
                # Recorded, but voided: the result is in the racer's history and on
                # their own table, and never reaches par or the board. Scoring it
                # would give a live racer more attempts than a self-paced one.
                fields.update(
                    reattempted=True,
                    reattempt_reason=(
                        f'Recorded for history only: this racer had already used all '
                        f'{qualifier.runs_per_pool} of their runs in this pool.'
                    ),
                    score=None,
                )
                voided.append(user.id)
            run = existing.get(user.id)
            if run is not None:
                await self.run_repository.update(run, started_at=started_at, **fields)
            else:
                await self.run_repository.create(
                    qualifier_id=qualifier.id,
                    user_id=user.id,
                    permalink_id=live_race.permalink_id,
                    live_race_id=live_race.id,
                    started_at=started_at,
                    **fields,
                )

        await self.qualifier_service.recompute_par_and_scores(live_race.permalink_id)
        # Recompute scores sibling run instances, so reload the captured runs
        # to return their post-score state.
        captured = await self.run_repository.list_for_live_race(live_race.id)

        live_race = await self.repository.update(
            live_race,
            status=AsyncQualifierLiveRaceStatus.FINISHED,
            # Cleared when nobody is left unmatched, so the card's to-do disappears
            # once the accounts are linked and the race is recorded again.
            unmatched_handles=unmatched or None,
        )
        detail = {
            'live_race_id': live_race.id,
            'qualifier_id': qualifier.id,
            'captured': len(captured),
            'unmatched_handles': unmatched,
            'voided_over_pool_cap': voided,
        }
        await self.audit_service.write_and_publish(
            actor,
            (AuditActions.ASYNC_QUALIFIER_LIVE_RACE_RECORDED_MANUALLY if manual
             else AuditActions.ASYNC_QUALIFIER_LIVE_RACE_RECORDED),
            detail,
            EventType.ASYNC_QUALIFIER_LIVE_RACE_RECORDED,
            event_extra={'manual': manual},
        )
        return captured

    # ============================================================= internals

    async def _over_pool_cap(
        self,
        live_race: AsyncQualifierLiveRace,
        qualifier: AsyncQualifier,
        users: Iterable[User],
        existing: dict,
    ) -> set:
        """Which racers' runs in this race would exceed the pool's ``runs_per_pool``.

        ``runs_per_pool`` is enforced in ``start_run``, which a live race never goes
        through — so a racer entering two races in a one-run pool ended up holding two
        counting runs, with the surplus dropped silently at scoring time.

        Idempotent with re-recording: this racer's own run from *this* race is already
        in the pool count, so it is discounted before comparing.
        """
        cap = max(1, qualifier.runs_per_pool)
        over = set()
        for user in users:
            used = await self.run_repository.count_valid_runs_for_user_in_pool(
                live_race.pool_id, user.id,  # type: ignore[attr-defined]
            )
            prior = existing.get(user.id)
            if prior is not None and not prior.reattempted:
                used -= 1
            if used >= cap:
                over.add(user.id)
        return over

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
