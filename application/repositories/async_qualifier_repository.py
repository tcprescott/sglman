"""Async Qualifier repositories — data access for the AsyncQualifier* aggregate (PR 9).

All reads are tenant-scoped and all writes are tenant-stamped via
``application.repositories._tenant``. Pure data access only: draw fairness,
scoring, review authorization, and the one-active-run rule live in
``AsyncQualifierService``. The one concession is ``lock_user_for_draw`` — a
row-lock helper the draw transaction needs — which is data access (a SELECT …
FOR UPDATE), not business logic.
"""

from typing import Any, Dict, List, Optional, Set

from application.repositories._tenant import current_tenant_id, scoped
from models import (
    AsyncQualifier,
    AsyncQualifierLiveRace,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierReviewNote,
    AsyncQualifierReviewStatus,
    AsyncQualifierRun,
    AsyncQualifierRunStatus,
    User,
)

# Runs that consumed a permalink slot: everything except a voided reattempt.
# Used for draw fairness and the runs-per-pool cap.
_VOIDED = {'reattempted': True}


class AsyncQualifierRepository:
    """Data access for :class:`AsyncQualifier`."""

    async def get_by_id(self, qualifier_id: int) -> Optional[AsyncQualifier]:
        return await AsyncQualifier.get_or_none(id=qualifier_id, tenant_id=current_tenant_id())

    async def get_with_relations(self, qualifier_id: int) -> Optional[AsyncQualifier]:
        return await (
            AsyncQualifier.filter(id=qualifier_id, tenant_id=current_tenant_id())
            .prefetch_related('admins', 'pools__permalinks', 'pools__preset')
            .first()
        )

    async def list_all(self) -> List[AsyncQualifier]:
        return await scoped(AsyncQualifier.all()).order_by('-created_at')

    async def list_active(self) -> List[AsyncQualifier]:
        return await scoped(AsyncQualifier.filter(is_active=True)).order_by('-created_at')

    async def create(self, **fields: Any) -> AsyncQualifier:
        return await AsyncQualifier.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, qualifier: AsyncQualifier, **fields: Any) -> AsyncQualifier:
        for key, value in fields.items():
            setattr(qualifier, key, value)
        await qualifier.save()
        return qualifier

    async def delete(self, qualifier: AsyncQualifier) -> None:
        await qualifier.delete()


class AsyncQualifierPoolRepository:
    """Data access for :class:`AsyncQualifierPool`."""

    async def get_by_id(self, pool_id: int) -> Optional[AsyncQualifierPool]:
        return await AsyncQualifierPool.get_or_none(id=pool_id, tenant_id=current_tenant_id())

    async def get_with_permalinks(self, pool_id: int) -> Optional[AsyncQualifierPool]:
        return await (
            AsyncQualifierPool.filter(id=pool_id, tenant_id=current_tenant_id())
            .prefetch_related('permalinks', 'preset', 'qualifier')
            .first()
        )

    async def list_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierPool]:
        return await scoped(
            AsyncQualifierPool.filter(qualifier_id=qualifier_id)
        ).prefetch_related('permalinks', 'preset').order_by('name')

    async def create(self, **fields: Any) -> AsyncQualifierPool:
        return await AsyncQualifierPool.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, pool: AsyncQualifierPool, **fields: Any) -> AsyncQualifierPool:
        for key, value in fields.items():
            setattr(pool, key, value)
        await pool.save()
        return pool

    async def delete(self, pool: AsyncQualifierPool) -> None:
        await pool.delete()


class AsyncQualifierPermalinkRepository:
    """Data access for :class:`AsyncQualifierPermalink`."""

    async def get_by_id(self, permalink_id: int) -> Optional[AsyncQualifierPermalink]:
        return await AsyncQualifierPermalink.get_or_none(id=permalink_id, tenant_id=current_tenant_id())

    async def list_for_pool(self, pool_id: int) -> List[AsyncQualifierPermalink]:
        return await scoped(AsyncQualifierPermalink.filter(pool_id=pool_id)).order_by('id')

    async def create(self, **fields: Any) -> AsyncQualifierPermalink:
        return await AsyncQualifierPermalink.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, permalink: AsyncQualifierPermalink, **fields: Any) -> AsyncQualifierPermalink:
        for key, value in fields.items():
            setattr(permalink, key, value)
        await permalink.save()
        return permalink

    async def delete(self, permalink: AsyncQualifierPermalink) -> None:
        await permalink.delete()


class AsyncQualifierRunRepository:
    """Data access for :class:`AsyncQualifierRun`."""

    async def get_by_id(self, run_id: int) -> Optional[AsyncQualifierRun]:
        return await (
            AsyncQualifierRun.filter(id=run_id, tenant_id=current_tenant_id())
            .prefetch_related('user', 'permalink__pool', 'qualifier', 'reviewed_by', 'review_claimed_by')
            .first()
        )

    async def lock_user_for_draw(self, user_id: int) -> Optional[User]:
        """Row-lock a player before a draw so concurrent clicks serialize.

        ``FOR UPDATE`` on the player's own row funnels that player's parallel
        draws through one at a time on Postgres; on SQLite it is a harmless no-op
        (write transactions already serialize). Cross-player draws never
        contend, since each locks a different row.
        """
        return await User.filter(id=user_id).select_for_update().first()

    async def get_active_for_user(self, qualifier_id: int, user_id: int) -> Optional[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(
                qualifier_id=qualifier_id,
                user_id=user_id,
                status=AsyncQualifierRunStatus.IN_PROGRESS,
                reattempted=False,
            )
        ).first()

    async def list_for_user(self, qualifier_id: int, user_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id, user_id=user_id)
        ).prefetch_related('permalink__pool').order_by('-created_at')

    async def list_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id)
        ).prefetch_related('user', 'permalink__pool').order_by('-created_at')

    async def list_valid_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        """Runs that count toward scoring/leaderboard: not voided by a reattempt."""
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id, reattempted=False)
        ).prefetch_related('user', 'permalink__pool').order_by('created_at')

    async def list_pending_review(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(
                qualifier_id=qualifier_id,
                status=AsyncQualifierRunStatus.FINISHED,
                review_status=AsyncQualifierReviewStatus.PENDING,
                reattempted=False,
            )
        ).prefetch_related('user', 'permalink__pool', 'review_claimed_by').order_by('finished_at')

    async def list_approved_finished_for_permalink(self, permalink_id: int) -> List[AsyncQualifierRun]:
        """Approved, finished, non-voided runs on a permalink — the par inputs."""
        return await scoped(
            AsyncQualifierRun.filter(
                permalink_id=permalink_id,
                status=AsyncQualifierRunStatus.FINISHED,
                review_status=AsyncQualifierReviewStatus.APPROVED,
                reattempted=False,
            )
        ).order_by('elapsed_seconds')

    async def played_permalink_ids_for_user_in_pool(self, pool_id: int, user_id: int) -> Set[int]:
        """Permalink ids this player has already consumed in a pool (no-repeat)."""
        rows = await scoped(
            AsyncQualifierRun.filter(
                permalink__pool_id=pool_id, user_id=user_id, reattempted=False
            )
        ).values_list('permalink_id', flat=True)
        return {pid for pid in rows if pid is not None}

    async def valid_run_counts_by_permalink_for_pool(self, pool_id: int) -> Dict[int, int]:
        """Play count per permalink in a pool (all players), for draw fairness."""
        rows = await scoped(
            AsyncQualifierRun.filter(permalink__pool_id=pool_id, reattempted=False)
        ).values_list('permalink_id', flat=True)
        counts: Dict[int, int] = {}
        for pid in rows:
            if pid is not None:
                counts[pid] = counts.get(pid, 0) + 1
        return counts

    async def count_valid_runs_for_user_in_pool(self, pool_id: int, user_id: int) -> int:
        return await scoped(
            AsyncQualifierRun.filter(
                permalink__pool_id=pool_id, user_id=user_id, reattempted=False
            )
        ).count()

    async def list_for_live_race(self, live_race_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(live_race_id=live_race_id)
        ).prefetch_related('user', 'permalink__pool').order_by('created_at')

    async def create(self, **fields: Any) -> AsyncQualifierRun:
        return await AsyncQualifierRun.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, run: AsyncQualifierRun, **fields: Any) -> AsyncQualifierRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await run.save()
        return run


class AsyncQualifierLiveRaceRepository:
    """Data access for :class:`AsyncQualifierLiveRace`."""

    async def get_by_id(self, live_race_id: int) -> Optional[AsyncQualifierLiveRace]:
        return await (
            AsyncQualifierLiveRace.filter(id=live_race_id, tenant_id=current_tenant_id())
            .prefetch_related('pool__qualifier', 'permalink')
            .first()
        )

    async def get_by_racetime_slug(self, slug: str) -> Optional[AsyncQualifierLiveRace]:
        """Resolve a live race by its room slug (tenant-scoped).

        The inbound-event handler resolves the ``RacetimeRoom`` (and its tenant)
        by slug first, then re-establishes tenant scope before calling this — so
        this stays scoped, unlike ``RacetimeRoomRepository.get_by_slug``.
        """
        return await scoped(
            AsyncQualifierLiveRace.filter(racetime_slug=slug)
        ).prefetch_related('pool__qualifier', 'permalink').first()

    async def list_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierLiveRace]:
        return await scoped(
            AsyncQualifierLiveRace.filter(pool__qualifier_id=qualifier_id)
        ).prefetch_related('pool', 'permalink').order_by('-created_at')

    async def list_for_pool(self, pool_id: int) -> List[AsyncQualifierLiveRace]:
        return await scoped(
            AsyncQualifierLiveRace.filter(pool_id=pool_id)
        ).prefetch_related('pool', 'permalink').order_by('-created_at')

    async def create(self, **fields: Any) -> AsyncQualifierLiveRace:
        return await AsyncQualifierLiveRace.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, live_race: AsyncQualifierLiveRace, **fields: Any) -> AsyncQualifierLiveRace:
        for key, value in fields.items():
            setattr(live_race, key, value)
        await live_race.save()
        return live_race

    async def delete(self, live_race: AsyncQualifierLiveRace) -> None:
        await live_race.delete()


class AsyncQualifierReviewNoteRepository:
    """Data access for :class:`AsyncQualifierReviewNote`."""

    async def list_for_run(self, run_id: int) -> List[AsyncQualifierReviewNote]:
        return await scoped(
            AsyncQualifierReviewNote.filter(run_id=run_id)
        ).prefetch_related('author').order_by('created_at')

    async def create(self, **fields: Any) -> AsyncQualifierReviewNote:
        return await AsyncQualifierReviewNote.create(tenant_id=current_tenant_id(), **fields)
