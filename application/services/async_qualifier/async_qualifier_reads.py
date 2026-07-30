"""Async qualifier — the player's read surface and the leaderboard.

Everything a competitor's own pages ask for: which qualifiers are open, what this
one looks like from outside the admin gate, whether they can start a run (and if
not, why not), their own runs, their reattempt allowance, and the board.

Mixed into :class:`AsyncQualifierService` — the same composition
``application/services/_bracket/`` uses — so the orchestration module stays inside
the file-length guideline. Reads only: nothing here writes or audits.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from application.services.async_qualifier import async_qualifier_access as access
from application.services.async_qualifier import async_qualifier_rules as rules
from application.services.async_qualifier.async_qualifier_scoring import (
    LeaderboardEntry,
    ScoredRun,
    build_leaderboard,
)
from application.utils.timezone import format_eastern_display
from application.feature_flags import requires_feature
from models import (
    AsyncQualifier,
    AsyncQualifierPool,
    AsyncQualifierReviewStatus,
    AsyncQualifierRun,
    AsyncQualifierRunStatus,
    FeatureFlag,
    User,
)


@dataclass(frozen=True)
class RunAvailability:
    """Whether this player can start a run, and if not, why not.

    ``pools`` is what they may draw from; ``usage`` is every pool with the
    player's spent/remaining counts, so the surface can show what is left without a
    second read.
    """

    pools: List[AsyncQualifierPool]
    usage: List[rules.PoolUsage]
    reason: Optional[rules.RunUnavailableReason]   # None <=> pools is non-empty
    message: str                                   # '' when a run can be started


class PlayerReadsMixin:
    """The competitor-facing reads. Requires the host's repositories and ``draw``."""

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_open_qualifiers(self) -> List[AsyncQualifier]:
        """Active qualifiers, newest first (the player-facing list)."""
        return await self.repository.list_active()

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_qualifier_for_player(self, qualifier_id: int) -> AsyncQualifier:
        """A qualifier's public shell (name/window) for the player pages — no
        admin gate. Pools/pars/other entrants' runs stay behind the lockdown in
        the methods that return them."""
        return await self._require_qualifier(qualifier_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_player_pools(
        self, user: Optional[User], qualifier_id: int
    ) -> List[AsyncQualifierPool]:
        """Pools a player may still draw from: within window, slots remaining,
        and at least one undrawn non-live-race permalink left.

        Raises for a shut window; kept for the REST client that relies on that.
        The web surface calls :meth:`get_run_availability`, which answers instead.
        """
        qualifier = await self._require_qualifier(qualifier_id)
        rules.ensure_window_open(qualifier)
        if user is None:
            return []
        pools, usage = await self._pool_usage(qualifier, user)
        return [p for p in pools if usage[p.id].has_candidates and usage[p.id].slots_left > 0]

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_run_availability(
        self, user: Optional[User], qualifier_id: int
    ) -> RunAvailability:
        """Whether this player can start a run, and if not, exactly why not.

        Deliberately does not raise on a shut window: "the window is closed" is
        the answer the runner needs, not an error the page has to translate. Every
        no-run case names what to do about it — wait, ask an organiser, or nothing.
        """
        qualifier = await self._require_qualifier(qualifier_id)
        window = rules.window_reason(qualifier)
        if user is None:
            reason = window or rules.RunUnavailableReason.ANONYMOUS
            return RunAvailability(pools=[], usage=[], reason=reason,
                                   message=self._describe(qualifier, reason))
        if window is not None:
            return RunAvailability(pools=[], usage=[], reason=window,
                                   message=self._describe(qualifier, window))
        pools, usage = await self._pool_usage(qualifier, user)
        # A pool a self-paced runner can never draw from is not part of their run
        # surface, so it neither shows a usage line nor votes on the reason.
        usages = [usage[p.id] for p in pools if usage[p.id].seeded]
        reason = rules.classify_availability(usages)
        eligible = [p for p in pools if usage[p.id].has_candidates and usage[p.id].slots_left > 0]
        return RunAvailability(
            pools=eligible, usage=usages, reason=reason,
            message='' if reason is None else self._describe(qualifier, reason),
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_user_runs(self, user: User, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await self.run_repository.list_for_user(qualifier_id, user.id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_active_run(self, user: User, qualifier_id: int) -> Optional[AsyncQualifierRun]:
        run = await self.run_repository.get_active_for_user(qualifier_id, user.id)
        if run is not None:
            await run.fetch_related('permalink__pool')
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_reattempt_allowance(
        self, user: User, qualifier_id: int
    ) -> rules.ReattemptAllowance:
        """How many reattempts this player has spent and may still spend."""
        qualifier = await self._require_qualifier(qualifier_id)
        return rules.ReattemptAllowance(
            spent=await self._count_reattempts(user.id, qualifier_id),
            allowed=qualifier.allowed_reattempts,
        )

    async def _pool_usage(self, qualifier: AsyncQualifier, user: User):
        """Every pool plus this player's state in it — the one eligibility loop.

        Both the pool list and the availability read derive from this, so "may I
        draw here?" is answered in one place.
        """
        pools = await self.pool_repository.list_for_qualifier(qualifier.id)
        usage = {}
        for pool in pools:
            candidates = await self.draw.draw_candidates(pool, user.id)
            used = await self.run_repository.count_valid_runs_for_user_in_pool(pool.id, user.id)
            usage[pool.id] = rules.PoolUsage(
                pool_id=pool.id, name=pool.name, used=used,
                allowed=qualifier.runs_per_pool, has_candidates=bool(candidates),
                seeded=await self.draw.async_seed_count(pool) > 0,
            )
        return pools, usage

    @staticmethod
    def _describe(qualifier: AsyncQualifier, reason) -> str:
        return rules.describe_unavailability(
            reason,
            runs_per_pool=qualifier.runs_per_pool,
            opens_display=format_eastern_display(qualifier.opens_at) if qualifier.opens_at else '',
            closes_display=format_eastern_display(qualifier.closes_at) if qualifier.closes_at else '',
        )

    def is_results_public(self, qualifier: AsyncQualifier, now: Optional[datetime] = None) -> bool:
        return rules.is_results_public(qualifier, now)

    async def get_leaderboard(
        self, actor: Optional[User], qualifier_id: int
    ) -> List[LeaderboardEntry]:
        qualifier = await self._require_qualifier(qualifier_id)
        if not self.is_results_public(qualifier):
            await access.ensure_qualifier_admin(
                actor, qualifier,
                message="The leaderboard is hidden while this qualifier is open",
            )
        pools = await self.pool_repository.list_for_qualifier(qualifier_id)
        pool_ids = [p.id for p in pools]
        runs = await self.run_repository.list_valid_for_qualifier(qualifier_id)
        scored: List[ScoredRun] = []
        for run in runs:
            if (run.status == AsyncQualifierRunStatus.FINISHED
                    and run.review_status == AsyncQualifierReviewStatus.APPROVED
                    and run.score is not None
                    and run.permalink is not None):
                scored.append(ScoredRun(
                    user_id=run.user_id,
                    username=rules.display_name(run.user),
                    pool_id=run.permalink.pool_id,
                    score=run.score,
                ))
        # Deterministic input order → stable ties (scoring keeps insertion order).
        scored.sort(key=lambda s: (s.username.lower(), s.user_id))
        return build_leaderboard(
            pool_ids=pool_ids, runs_per_pool=qualifier.runs_per_pool, scored_runs=scored
        )
