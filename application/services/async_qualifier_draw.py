"""Async qualifier — draw & scoring engine.

The imbalance-forcing permalink draw and the par/score recompute lifted out of
:class:`AsyncQualifierService`. Holds the repositories it needs, composed by the
service the same way :class:`MatchService` composes ``MatchScheduleService``. It
performs no audit writes and publishes no events — those stay with the service
methods that call it.
"""

import secrets
from datetime import datetime, timezone
from typing import List, Optional

from application.repositories import (
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierRunRepository,
)
from application.services import async_qualifier_rules as rules
from application.services.async_qualifier_scoring import compute_par, compute_score
from models import (
    AsyncQualifier,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
)


class AsyncQualifierDraw:
    """Imbalance-forcing permalink draw + par/score recompute for a qualifier."""

    def __init__(
        self,
        *,
        repository: AsyncQualifierRepository,
        pool_repository: AsyncQualifierPoolRepository,
        permalink_repository: AsyncQualifierPermalinkRepository,
        run_repository: AsyncQualifierRunRepository,
    ) -> None:
        self.repository = repository
        self.pool_repository = pool_repository
        self.permalink_repository = permalink_repository
        self.run_repository = run_repository

    async def draw_candidates(
        self, pool: AsyncQualifierPool, user_id: int
    ) -> List[AsyncQualifierPermalink]:
        """Permalinks a player may still draw from a pool: not live-race and not
        already played by them (no-repeat)."""
        permalinks = await self.permalink_repository.list_for_pool(pool.id)
        played = await self.run_repository.played_permalink_ids_for_user_in_pool(pool.id, user_id)
        return [p for p in permalinks if not p.live_race and p.id not in played]

    async def pick_permalink(
        self, qualifier: AsyncQualifier, pool: AsyncQualifierPool, user_id: int
    ) -> Optional[AsyncQualifierPermalink]:
        """Imbalance-forcing draw: random among candidates unless the pool's
        play-count spread crosses the threshold, then force the least-played."""
        candidates = await self.draw_candidates(pool, user_id)
        if not candidates:
            return None
        counts = await self.run_repository.valid_run_counts_by_permalink_for_pool(pool.id)
        cand_counts = {c.id: counts.get(c.id, 0) for c in candidates}
        threshold = rules.imbalance_threshold(qualifier)
        spread = max(cand_counts.values()) - min(cand_counts.values())
        if spread >= threshold:
            fewest = min(cand_counts.values())
            candidates = [c for c in candidates if cand_counts[c.id] == fewest]
        return secrets.choice(candidates)

    async def recompute_par_and_scores(self, permalink_id: int) -> None:
        """Recompute a permalink's par from its approved finished runs and
        rescore every one of them (par shifts as runs are reviewed/voided)."""
        permalink = await self.permalink_repository.get_by_id(permalink_id)
        if permalink is None:
            return
        approved = await self.run_repository.list_approved_finished_for_permalink(permalink_id)
        elapsed = [r.elapsed_seconds for r in approved if r.elapsed_seconds]
        sample = rules.par_sample_size(await self._qualifier_for_permalink(permalink))
        par = compute_par(elapsed, sample)
        await self.permalink_repository.update(
            permalink, par_time=par, par_updated_at=datetime.now(timezone.utc)
        )
        for run in approved:
            score = compute_score(run.elapsed_seconds, par)
            if score != run.score:
                await self.run_repository.update(run, score=score)

    async def _qualifier_for_permalink(
        self, permalink: AsyncQualifierPermalink
    ) -> Optional[AsyncQualifier]:
        pool = await self.pool_repository.get_by_id(permalink.pool_id)
        if pool is None:
            return None
        return await self.repository.get_by_id(pool.qualifier_id)
