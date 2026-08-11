"""Async Qualifier repositories — data access for the AsyncQualifier* aggregate (PR 9).

All reads are tenant-scoped and all writes are tenant-stamped via
``application.repositories._tenant``. Pure data access only: draw fairness,
scoring, review authorization, and the one-active-run rule live in
``AsyncQualifierService``. The one concession is ``lock_user_for_draw`` — a
row-lock helper the draw transaction needs — which is data access (a SELECT …
FOR UPDATE), not business logic.
"""

from datetime import datetime
from typing import Any, Collection, Dict, List, Optional, Set

from tortoise.expressions import Q

from application.repositories._base import TenantScopedRepository
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


def _enum_value(value: Any) -> str:
    """``.values()`` returns the raw column for a CharEnumField on some backends
    and the enum on others, so the tally normalises both."""
    return value.value if hasattr(value, 'value') else str(value)


class AsyncQualifierRepository(TenantScopedRepository[AsyncQualifier]):
    """Data access for :class:`AsyncQualifier`."""

    model = AsyncQualifier

    async def list_all(self) -> List[AsyncQualifier]:
        return await scoped(AsyncQualifier.all()).order_by('-created_at')

    async def list_active(self) -> List[AsyncQualifier]:
        return await scoped(AsyncQualifier.filter(is_active=True)).order_by('-created_at')


class AsyncQualifierPoolRepository(TenantScopedRepository[AsyncQualifierPool]):
    """Data access for :class:`AsyncQualifierPool`."""

    model = AsyncQualifierPool

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


class AsyncQualifierPermalinkRepository(TenantScopedRepository[AsyncQualifierPermalink]):
    """Data access for :class:`AsyncQualifierPermalink`."""

    model = AsyncQualifierPermalink

    async def list_for_pool(self, pool_id: int) -> List[AsyncQualifierPermalink]:
        return await scoped(AsyncQualifierPermalink.filter(pool_id=pool_id)).order_by('id')


class AsyncQualifierRunRepository(TenantScopedRepository[AsyncQualifierRun]):
    """Data access for :class:`AsyncQualifierRun`."""

    model = AsyncQualifierRun

    @staticmethod
    async def list_in_progress_all() -> List[AsyncQualifierRun]:
        """Every started, still-in-progress run, **across all tenants**.

        Deliberately unscoped, like ``RacetimeRoomRepository.list_open_all``: the
        expiry worker runs off a timer with no request context, so it does one
        cross-tenant scan and then re-enters each run's own ``tenant_scope`` before
        touching it.

        Unfiltered by age on purpose. Each qualifier configures its own time
        limit, so there is no single cutoff that is correct for every tenant, and
        a wrong one silently skips runs. The set this returns is small and
        self-limiting — a player may hold one active run per qualifier — and the
        ``(status, started_at)`` index covers it.
        """
        return await AsyncQualifierRun.filter(
            status=AsyncQualifierRunStatus.IN_PROGRESS,
            started_at__isnull=False,
        ).prefetch_related('qualifier', 'user', 'tenant').order_by('started_at')

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
        ).prefetch_related('permalink__pool', 'review_notes__author').order_by('-created_at')

    async def list_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id)
        ).prefetch_related('user', 'permalink__pool', 'review_notes__author').order_by('-created_at')

    async def list_valid_for_qualifier(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        """Runs that count toward scoring/leaderboard: not voided by a reattempt."""
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id, reattempted=False)
        ).prefetch_related('user', 'permalink__pool').order_by('created_at')

    async def list_scored_for_leaderboard(self, qualifier_id: int) -> List[Dict[str, Any]]:
        """Every run that occupies a leaderboard slot, projected to scalars.

        Two kinds of row: a scored, approved finisher, and a slot the runner spent
        on an outcome that can never score — a forfeit (chosen or expired), a
        disqualification, or a rejected submission. The second kind is why the
        filter is not simply "approved and finished": those slots are consumed and
        unrefillable, so they belong on the board as realised zeros rather than
        vanishing and leaving the runner's estimate projected over ground they
        cannot make up.

        The board used to come from :meth:`list_valid_for_qualifier`, which filters
        on ``reattempted`` alone and prefetches ``user`` and ``permalink__pool`` for
        every row — so a fifth of the rows were built as full ORM objects and
        discarded by a Python status check. Pushing the filters into SQL and asking
        for values instead of models is the same board an order of magnitude
        cheaper.

        Ordered so ties on the board are stable and reproducible, which the pure
        scoring function relies on rather than re-deriving.
        """
        return await scoped(
            AsyncQualifierRun.filter(
                qualifier_id=qualifier_id,
                reattempted=False,
                permalink_id__not_isnull=True,
            ).filter(
                # A scored finisher, or a slot the runner spent on an outcome that
                # cannot score. Both fill a slot; only the first adds to the total.
                Q(status=AsyncQualifierRunStatus.FINISHED,
                  review_status=AsyncQualifierReviewStatus.APPROVED,
                  score__not_isnull=True)
                | Q(status__in=[AsyncQualifierRunStatus.FORFEIT,
                                AsyncQualifierRunStatus.DISQUALIFIED])
                | Q(status=AsyncQualifierRunStatus.FINISHED,
                    review_status=AsyncQualifierReviewStatus.REJECTED)
            )
        ).order_by('user_id').values(
            'user_id', 'score', 'status', 'review_status', 'permalink__pool_id',
            'user__display_name', 'user__username',
        )

    async def outcome_tally_for_users(
        self, qualifier_id: int, user_ids: Collection[int]
    ) -> Dict[int, Dict[str, int]]:
        """Per-user run outcome counts, for the reviewer's "other runs" context line.

        Scales with the *queue* rather than with the qualifier: the reviewer needs
        this only for the people whose runs they are looking at, so passing the
        queue's user ids reads a handful of rows on a quiet queue instead of every
        run in the tournament. Four scalars per row, no joins and no model
        hydration — the card wants counts, not runs.
        """
        if not user_ids:
            return {}
        rows = await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id, user_id__in=list(user_ids))
        ).values('id', 'user_id', 'status', 'review_status', 'reattempted')
        tally: Dict[int, Dict[str, int]] = {}
        for row in rows:
            status = _enum_value(row['status'])
            label = ('voided' if row['reattempted']
                     else _enum_value(row['review_status']) if status == 'finished'
                     else status)
            per_user = tally.setdefault(row['user_id'], {})
            per_user[label] = per_user.get(label, 0) + 1
        return tally

    async def list_pending_review(self, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await scoped(
            AsyncQualifierRun.filter(
                qualifier_id=qualifier_id,
                status=AsyncQualifierRunStatus.FINISHED,
                review_status=AsyncQualifierReviewStatus.PENDING,
                reattempted=False,
            )
        ).prefetch_related(
            'user', 'permalink__pool', 'review_claimed_by', 'review_notes__author',
        ).order_by('finished_at')

    async def settle_review(
        self,
        run_id: int,
        *,
        expect: AsyncQualifierReviewStatus,
        **changes: Any,
    ) -> int:
        """Write a verdict only if the run still carries ``expect``. Rows affected.

        A compare-and-set, because "read the row, decide, write it back" lets two
        reviewers who opened the same card both commit: the second read happens
        before the first write, so neither sees the other. Postgres re-evaluates a
        conditional ``UPDATE``'s predicate after taking the row lock, so the
        second writer's ``review_status`` no longer matches and it affects zero
        rows — a stale read that loses instead of silently overwriting.

        Zero is a normal answer, not an error; the caller decides what it means.
        """
        return await scoped(
            AsyncQualifierRun.filter(id=run_id, review_status=expect)
        ).update(**changes)

    @staticmethod
    async def list_stale_claims_all(cutoff: datetime) -> List[AsyncQualifierRun]:
        """Runs still claimed for review since before ``cutoff``, across all tenants.

        Deliberately unscoped, like :meth:`list_in_progress_all`: the worker has no
        tenant of its own, so it does one cross-tenant scan and re-enters each run's
        own ``tenant_scope`` before touching it.

        A claim is a courtesy lock on a queue card, and nothing releases it if the
        reviewer closes the tab — so without this sweep a run nobody is looking at
        reads as "someone has this" for the rest of the qualifier.
        """
        return await AsyncQualifierRun.filter(
            review_claimed_at__lt=cutoff,
            review_claimed_by_id__not_isnull=True,
        ).prefetch_related('tenant').order_by('review_claimed_at')

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


class AsyncQualifierLiveRaceRepository(TenantScopedRepository[AsyncQualifierLiveRace]):
    """Data access for :class:`AsyncQualifierLiveRace`."""

    model = AsyncQualifierLiveRace

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


class AsyncQualifierReviewNoteRepository:
    """Data access for :class:`AsyncQualifierReviewNote`."""

    async def list_for_run(self, run_id: int) -> List[AsyncQualifierReviewNote]:
        return await scoped(
            AsyncQualifierReviewNote.filter(run_id=run_id)
        ).prefetch_related('author').order_by('created_at')

    async def create(self, **fields: Any) -> AsyncQualifierReviewNote:
        return await AsyncQualifierReviewNote.create(tenant_id=current_tenant_id(), **fields)
