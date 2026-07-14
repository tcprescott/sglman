"""Async Qualifier Service — Business Logic Layer (PR 9).

The self-paced permalink-pool qualifier: a peer aggregate of ``Tournament`` with
its own state machine (window opens → draw → run → review → scored leaderboard →
close). This service owns every rule the repositories deliberately don't:

- **Management** (create/edit qualifier, pools, permalinks, admins) gated by
  :meth:`AuthService.can_admin_qualifier`; ``admins`` doubles as the reviewer set.
- **Draw** — an atomic, row-locked transaction: one active run per player, a
  permalink revealed only at start, no-repeat, ``runs_per_pool`` cap, and
  imbalance-forcing fairness so sampling stays even.
- **Run lifecycle** — submit (→ review), forfeit (irreversible, scores zero), and
  reattempt (voids the prior run, frees the slot, requires a reason, is limited).
- **Review** — reviewers = the qualifier's ``admins``; **self-review blocked**;
  claim-locking; approve/reject recomputes the permalink's par and rescores.
- **Scoring / leaderboard** — par + score math in
  :mod:`application.services.async_qualifier_scoring`; the board obeys the
  **active-window information lockdown** (pool/par/other entrants' runs are
  staff-only until the qualifier closes).

Raises :class:`ValueError` for user errors and :class:`PermissionError` for authz
(both surfaced by the UI); audits every state change and mirrors run
submitted/reviewed onto the event bus. Discord DMs (window-open, run-reviewed) are
best-effort and never block a state change.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from tortoise.transactions import in_transaction

from application.events import Event, EventType, event_bus
from application.repositories import (
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierReviewNoteRepository,
    AsyncQualifierRunRepository,
    PresetRepository,
)
from application.services.async_qualifier_config import validate_async_qualifier_config
from application.services.async_qualifier_scoring import (
    DEFAULT_PAR_SAMPLE_SIZE,
    LeaderboardEntry,
    ScoredRun,
    build_leaderboard,
    compute_par,
    compute_score,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.seedgen_service import SeedGenerationService
from models import (
    AsyncQualifier,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierReviewStatus,
    AsyncQualifierRun,
    AsyncQualifierRunStatus,
    User,
)

logger = logging.getLogger(__name__)

# Terminal run states a finished/forfeit/DQ run can be in (used for slot counting).
_TERMINAL = {
    AsyncQualifierRunStatus.FINISHED,
    AsyncQualifierRunStatus.FORFEIT,
    AsyncQualifierRunStatus.DISQUALIFIED,
}
_DEFAULT_IMBALANCE_THRESHOLD = 2


class AsyncQualifierService:
    """CRUD + run execution + review + scoring for async qualifiers."""

    def __init__(self) -> None:
        self.repository = AsyncQualifierRepository()
        self.pool_repository = AsyncQualifierPoolRepository()
        self.permalink_repository = AsyncQualifierPermalinkRepository()
        self.run_repository = AsyncQualifierRunRepository()
        self.note_repository = AsyncQualifierReviewNoteRepository()
        self.preset_repository = PresetRepository()
        self.audit_service = AuditService()

    # ============================================================ management

    async def list_qualifiers(self, actor: Optional[User]) -> List[AsyncQualifier]:
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor), "Cannot administer qualifiers"
        )
        return await self.repository.list_all()

    async def get_qualifier(self, actor: Optional[User], qualifier_id: int) -> AsyncQualifier:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        return qualifier

    async def create_qualifier(
        self,
        actor: Optional[User],
        *,
        name: str,
        description: Optional[str] = None,
        event_name: Optional[str] = None,
        opens_at: Optional[datetime] = None,
        closes_at: Optional[datetime] = None,
        runs_per_pool: int = 1,
        allowed_reattempts: int = 0,
        config: Optional[dict] = None,
    ) -> AsyncQualifier:
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor), "Cannot administer qualifiers"
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Qualifier name is required")
        runs_per_pool, allowed_reattempts = self._validate_counts(runs_per_pool, allowed_reattempts)
        self._validate_window(opens_at, closes_at)
        config = validate_async_qualifier_config(config)
        qualifier = await self.repository.create(
            name=name,
            description=(description or '').strip() or None,
            event_name=(event_name or '').strip() or None,
            opens_at=opens_at,
            closes_at=closes_at,
            runs_per_pool=runs_per_pool,
            allowed_reattempts=allowed_reattempts,
            config=config,
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_CREATED,
            {'qualifier_id': qualifier.id, 'name': name},
        )
        return qualifier

    async def update_qualifier(
        self,
        actor: Optional[User],
        qualifier_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        event_name: Optional[str] = None,
        opens_at: Optional[datetime] = None,
        closes_at: Optional[datetime] = None,
        runs_per_pool: Optional[int] = None,
        allowed_reattempts: Optional[int] = None,
        is_active: Optional[bool] = None,
        config: Optional[dict] = None,
        clear_window: bool = False,
    ) -> AsyncQualifier:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        changes: dict = {}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Qualifier name is required")
            changes['name'] = name
        if description is not None:
            changes['description'] = description.strip() or None
        if event_name is not None:
            changes['event_name'] = event_name.strip() or None
        new_opens = opens_at if opens_at is not None or clear_window else qualifier.opens_at
        new_closes = closes_at if closes_at is not None or clear_window else qualifier.closes_at
        if opens_at is not None or closes_at is not None or clear_window:
            self._validate_window(new_opens, new_closes)
            changes['opens_at'] = new_opens
            changes['closes_at'] = new_closes
        new_rpp = qualifier.runs_per_pool if runs_per_pool is None else runs_per_pool
        new_ar = qualifier.allowed_reattempts if allowed_reattempts is None else allowed_reattempts
        if runs_per_pool is not None or allowed_reattempts is not None:
            new_rpp, new_ar = self._validate_counts(new_rpp, new_ar)
            changes['runs_per_pool'] = new_rpp
            changes['allowed_reattempts'] = new_ar
        if is_active is not None:
            changes['is_active'] = is_active
        if config is not None:
            changes['config'] = validate_async_qualifier_config(config)
        qualifier = await self.repository.update(qualifier, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_UPDATED,
            {'qualifier_id': qualifier.id, 'fields': sorted(changes.keys())},
        )
        return qualifier

    async def delete_qualifier(self, actor: Optional[User], qualifier_id: int) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_DELETED,
            {'qualifier_id': qualifier.id, 'name': qualifier.name},
        )
        await self.repository.delete(qualifier)

    async def add_admin(self, actor: Optional[User], qualifier_id: int, target: User) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        await qualifier.admins.add(target)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_ADMIN_GRANTED,
            {'qualifier_id': qualifier.id, 'target_user_id': target.id},
        )

    async def remove_admin(self, actor: Optional[User], qualifier_id: int, target: User) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        await qualifier.admins.remove(target)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_ADMIN_REVOKED,
            {'qualifier_id': qualifier.id, 'target_user_id': target.id},
        )

    async def list_admins(self, actor: Optional[User], qualifier_id: int) -> List[User]:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        return await qualifier.admins.all()

    # ------------------------------------------------------------------ pools

    async def list_pools(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierPool]:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        return await self.pool_repository.list_for_qualifier(qualifier_id)

    async def create_pool(
        self,
        actor: Optional[User],
        qualifier_id: int,
        *,
        name: str,
        preset_id: Optional[int] = None,
    ) -> AsyncQualifierPool:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Pool name is required")
        if preset_id is not None and await self.preset_repository.get_by_id(preset_id) is None:
            raise ValueError("Preset not found")
        existing = await self.pool_repository.list_for_qualifier(qualifier_id)
        if any(p.name.lower() == name.lower() for p in existing):
            raise ValueError(f"A pool named '{name}' already exists")
        pool = await self.pool_repository.create(
            qualifier_id=qualifier_id, name=name, preset_id=preset_id
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_POOL_CREATED,
            {'qualifier_id': qualifier_id, 'pool_id': pool.id, 'name': name},
        )
        return pool

    async def update_pool(
        self,
        actor: Optional[User],
        pool_id: int,
        *,
        name: Optional[str] = None,
        preset_id: Optional[int] = None,
        clear_preset: bool = False,
    ) -> AsyncQualifierPool:
        pool = await self._require_pool(pool_id)
        await self._ensure_pool_admin(actor, pool)
        changes: dict = {}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Pool name is required")
            changes['name'] = name
        if clear_preset:
            changes['preset_id'] = None
        elif preset_id is not None:
            if await self.preset_repository.get_by_id(preset_id) is None:
                raise ValueError("Preset not found")
            changes['preset_id'] = preset_id
        pool = await self.pool_repository.update(pool, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_POOL_UPDATED,
            {'pool_id': pool.id, 'fields': sorted(changes.keys())},
        )
        return pool

    async def delete_pool(self, actor: Optional[User], pool_id: int) -> None:
        pool = await self._require_pool(pool_id)
        await self._ensure_pool_admin(actor, pool)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_POOL_DELETED,
            {'pool_id': pool.id, 'qualifier_id': pool.qualifier_id},
        )
        await self.pool_repository.delete(pool)

    # ------------------------------------------------------------- permalinks

    async def add_permalink(
        self,
        actor: Optional[User],
        pool_id: int,
        *,
        url: str,
        notes: Optional[str] = None,
        live_race: bool = False,
    ) -> AsyncQualifierPermalink:
        pool = await self._require_pool(pool_id)
        await self._ensure_pool_admin(actor, pool)
        url = (url or '').strip()
        if not url:
            raise ValueError("Permalink URL is required")
        permalink = await self.permalink_repository.create(
            pool_id=pool_id, url=url, notes=(notes or '').strip() or None, live_race=live_race
        )
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_ADDED,
            {'pool_id': pool_id, 'permalink_id': permalink.id},
        )
        return permalink

    async def add_permalinks_bulk(
        self, actor: Optional[User], pool_id: int, *, urls: Sequence[str]
    ) -> List[AsyncQualifierPermalink]:
        """Paste-many: add one permalink per non-blank line."""
        pool = await self._require_pool(pool_id)
        await self._ensure_pool_admin(actor, pool)
        created: List[AsyncQualifierPermalink] = []
        for raw in urls:
            url = (raw or '').strip()
            if not url:
                continue
            created.append(await self.permalink_repository.create(pool_id=pool_id, url=url))
        if created:
            await self.audit_service.write_log(
                actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_ADDED,
                {'pool_id': pool_id, 'count': len(created)},
            )
        return created

    async def roll_permalinks(
        self, actor: Optional[User], pool_id: int, *, count: int
    ) -> List[AsyncQualifierPermalink]:
        """Roll ``count`` fresh seeds from the pool's preset into permalinks."""
        pool = await self.pool_repository.get_with_permalinks(pool_id)
        if pool is None:
            raise ValueError("Pool not found")
        await self._ensure_pool_admin(actor, pool)
        if pool.preset is None:
            raise ValueError("Pool has no preset to roll from")
        if count < 1 or count > 25:
            raise ValueError("Roll count must be between 1 and 25")
        seedgen = SeedGenerationService()
        created: List[AsyncQualifierPermalink] = []
        for _ in range(count):
            url = await seedgen.generate_seed(pool.preset.randomizer, pool.preset)
            created.append(await self.permalink_repository.create(pool_id=pool_id, url=url))
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_ADDED,
            {'pool_id': pool_id, 'count': len(created), 'rolled': True},
        )
        return created

    async def update_permalink(
        self,
        actor: Optional[User],
        permalink_id: int,
        *,
        url: Optional[str] = None,
        notes: Optional[str] = None,
        live_race: Optional[bool] = None,
    ) -> AsyncQualifierPermalink:
        permalink = await self._require_permalink(permalink_id)
        await self._ensure_permalink_admin(actor, permalink)
        changes: dict = {}
        if url is not None:
            url = url.strip()
            if not url:
                raise ValueError("Permalink URL is required")
            changes['url'] = url
        if notes is not None:
            changes['notes'] = notes.strip() or None
        if live_race is not None:
            changes['live_race'] = live_race
        permalink = await self.permalink_repository.update(permalink, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_UPDATED,
            {'permalink_id': permalink.id, 'fields': sorted(changes.keys())},
        )
        return permalink

    async def delete_permalink(self, actor: Optional[User], permalink_id: int) -> None:
        permalink = await self._require_permalink(permalink_id)
        await self._ensure_permalink_admin(actor, permalink)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_DELETED,
            {'permalink_id': permalink.id, 'pool_id': permalink.pool_id},
        )
        await self.permalink_repository.delete(permalink)

    # =============================================================== player

    async def list_open_qualifiers(self) -> List[AsyncQualifier]:
        """Active qualifiers, newest first (the player-facing list)."""
        return await self.repository.list_active()

    async def get_qualifier_for_player(self, qualifier_id: int) -> AsyncQualifier:
        """A qualifier's public shell (name/window) for the player pages — no
        admin gate. Pools/pars/other entrants' runs stay behind the lockdown in
        the methods that return them."""
        return await self._require_qualifier(qualifier_id)

    async def get_player_pools(
        self, user: Optional[User], qualifier_id: int
    ) -> List[AsyncQualifierPool]:
        """Pools a player may still draw from: within window, slots remaining,
        and at least one undrawn non-live-race permalink left."""
        qualifier = await self._require_qualifier(qualifier_id)
        self._ensure_window_open(qualifier)
        if user is None:
            return []
        pools = await self.pool_repository.list_for_qualifier(qualifier_id)
        eligible: List[AsyncQualifierPool] = []
        for pool in pools:
            candidates = await self._draw_candidates(pool, user.id)
            used = await self.run_repository.count_valid_runs_for_user_in_pool(pool.id, user.id)
            if candidates and used < qualifier.runs_per_pool:
                eligible.append(pool)
        return eligible

    async def list_user_runs(self, user: User, qualifier_id: int) -> List[AsyncQualifierRun]:
        return await self.run_repository.list_for_user(qualifier_id, user.id)

    async def get_active_run(self, user: User, qualifier_id: int) -> Optional[AsyncQualifierRun]:
        run = await self.run_repository.get_active_for_user(qualifier_id, user.id)
        if run is not None:
            await run.fetch_related('permalink__pool')
        return run

    async def start_run(self, user: User, qualifier_id: int, pool_id: int) -> AsyncQualifierRun:
        """Atomically draw a permalink and open a run (reveal == start).

        Row-locks the player so concurrent clicks serialize, enforces one active
        run + the per-pool cap + no-repeat inside the transaction, then picks a
        permalink by imbalance-forcing fairness.
        """
        if user is None:
            raise ValueError("You must be logged in to start a run")
        qualifier = await self._require_qualifier(qualifier_id)
        self._ensure_window_open(qualifier)
        pool = await self._require_pool(pool_id)
        if pool.qualifier_id != qualifier_id:
            raise ValueError("Pool does not belong to this qualifier")

        async with in_transaction():
            await self.run_repository.lock_user_for_draw(user.id)
            active = await self.run_repository.get_active_for_user(qualifier_id, user.id)
            if active is not None:
                raise ValueError("You already have a run in progress")
            used = await self.run_repository.count_valid_runs_for_user_in_pool(pool_id, user.id)
            if used >= qualifier.runs_per_pool:
                raise ValueError("You have used all your runs for this pool")
            permalink = await self._pick_permalink(qualifier, pool, user.id)
            if permalink is None:
                raise ValueError("No permalinks left to draw in this pool")
            run = await self.run_repository.create(
                qualifier_id=qualifier_id,
                user_id=user.id,
                permalink_id=permalink.id,
                status=AsyncQualifierRunStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
        run.permalink = permalink
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_STARTED,
            {'qualifier_id': qualifier_id, 'run_id': run.id, 'pool_id': pool_id},
        )
        return run

    async def submit_run(
        self, user: User, run_id: int, *, elapsed_seconds: int, runner_vod_url: Optional[str] = None
    ) -> AsyncQualifierRun:
        run = await self._require_own_active_run(user, run_id)
        if elapsed_seconds is None or elapsed_seconds <= 0:
            raise ValueError("Finish time must be a positive number of seconds")
        run = await self.run_repository.update(
            run,
            status=AsyncQualifierRunStatus.FINISHED,
            finished_at=datetime.now(timezone.utc),
            elapsed_seconds=elapsed_seconds,
            runner_vod_url=(runner_vod_url or '').strip() or None,
            review_status=AsyncQualifierReviewStatus.PENDING,
        )
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_SUBMITTED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id, 'elapsed_seconds': elapsed_seconds},
        )
        event_bus.publish(Event.create(EventType.ASYNC_QUALIFIER_RUN_SUBMITTED, {
            'run_id': run.id, 'qualifier_id': run.qualifier_id, 'user_id': user.id,
        }, user))
        return run

    async def forfeit_run(self, user: User, run_id: int) -> AsyncQualifierRun:
        """Forfeit is irreversible, scores zero, and blocks replay unless a
        reattempt is spent."""
        run = await self._require_own_active_run(user, run_id)
        run = await self.run_repository.update(
            run,
            status=AsyncQualifierRunStatus.FORFEIT,
            finished_at=datetime.now(timezone.utc),
            score=0.0,
            review_status=AsyncQualifierReviewStatus.APPROVED,
        )
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_FORFEITED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id},
        )
        return run

    async def reattempt_run(self, user: User, run_id: int, *, reason: str) -> AsyncQualifierRun:
        """Void a prior terminal run so its pool slot frees up for a fresh draw.

        Requires a reason, is limited by ``allowed_reattempts``, and never touches
        an in-progress run (finish or forfeit it first).
        """
        run = await self.run_repository.get_by_id(run_id)
        if run is None or run.user_id != user.id:
            raise ValueError("Run not found")
        reason = (reason or '').strip()
        if not reason:
            raise ValueError("A reattempt reason is required")
        if run.reattempted:
            raise ValueError("This run was already reattempted")
        if run.status not in _TERMINAL:
            raise ValueError("Only a finished or forfeited run can be reattempted")
        qualifier = await self._require_qualifier(run.qualifier_id)
        spent = await self._count_reattempts(user.id, run.qualifier_id)
        if spent >= qualifier.allowed_reattempts:
            raise ValueError("No reattempts remaining")
        run = await self.run_repository.update(
            run, reattempted=True, reattempt_reason=reason
        )
        # A voided run leaves the leaderboard/par inputs, so refresh the affected
        # permalink's par + sibling scores.
        if run.permalink_id is not None:
            await self._recompute_par_and_scores(run.permalink_id)
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_REATTEMPTED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id},
        )
        return run

    # =============================================================== review

    async def list_review_queue(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierRun]:
        qualifier = await self._require_qualifier(qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot review this qualifier"
        )
        return await self.run_repository.list_pending_review(qualifier_id)

    async def claim_run(self, actor: Optional[User], run_id: int) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        if run.review_claimed_by_id and run.review_claimed_by_id != actor.id:
            raise ValueError("Another reviewer has already claimed this run")
        run = await self.run_repository.update(
            run, review_claimed_by_id=actor.id, review_claimed_at=datetime.now(timezone.utc)
        )
        return run

    async def release_claim(self, actor: Optional[User], run_id: int) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        run = await self.run_repository.update(
            run, review_claimed_by_id=None, review_claimed_at=None
        )
        return run

    async def review_run(
        self, actor: Optional[User], run_id: int, *, approved: bool, note: Optional[str] = None
    ) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        if run.user_id == actor.id:
            raise ValueError("You cannot review your own run")
        if run.status != AsyncQualifierRunStatus.FINISHED:
            raise ValueError("Only a finished run can be reviewed")
        new_status = (
            AsyncQualifierReviewStatus.APPROVED if approved else AsyncQualifierReviewStatus.REJECTED
        )
        note = (note or '').strip()
        if note:
            await self.note_repository.create(run_id=run.id, author_id=actor.id, note=note)
        run = await self.run_repository.update(
            run,
            review_status=new_status,
            reviewed_by_id=actor.id,
            reviewed_at=datetime.now(timezone.utc),
        )
        # Recompute the permalink's par from the (now-updated) approved set, then
        # rescore every approved run on it — this run included.
        if run.permalink_id is not None:
            await self._recompute_par_and_scores(run.permalink_id)
            run = await self.run_repository.get_by_id(run.id) or run
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_RUN_REVIEWED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id, 'approved': approved},
        )
        event_bus.publish(Event.create(EventType.ASYNC_QUALIFIER_RUN_REVIEWED, {
            'run_id': run.id, 'qualifier_id': run.qualifier_id,
            'user_id': run.user_id, 'approved': approved,
        }, actor))
        await self._notify_run_reviewed(run, approved)
        return run

    async def get_run_notes(self, actor: Optional[User], run_id: int):
        run = await self.run_repository.get_by_id(run_id)
        if run is None:
            raise ValueError("Run not found")
        qualifier = await self._require_qualifier(run.qualifier_id)
        # A reviewer sees any run's notes; a runner sees their own.
        if not (await AuthService.can_admin_qualifier(actor, qualifier)
                or (actor is not None and run.user_id == actor.id)):
            raise PermissionError("Cannot view these review notes")
        return await self.note_repository.list_for_run(run_id)

    # =========================================================== leaderboard

    def is_results_public(self, qualifier: AsyncQualifier, now: Optional[datetime] = None) -> bool:
        """Active-window information lockdown: pool/par/other entrants' runs and
        the leaderboard go public only once the qualifier closes (inactive or
        past ``closes_at``)."""
        now = now or datetime.now(timezone.utc)
        if not qualifier.is_active:
            return True
        return qualifier.closes_at is not None and now >= qualifier.closes_at

    async def get_leaderboard(
        self, actor: Optional[User], qualifier_id: int
    ) -> List[LeaderboardEntry]:
        qualifier = await self._require_qualifier(qualifier_id)
        if not self.is_results_public(qualifier):
            await AuthService.ensure(
                await AuthService.can_admin_qualifier(actor, qualifier),
                "The leaderboard is hidden while this qualifier is open",
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
                    username=self._display_name(run.user),
                    pool_id=run.permalink.pool_id,
                    score=run.score,
                ))
        # Deterministic input order → stable ties (scoring keeps insertion order).
        scored.sort(key=lambda s: (s.username.lower(), s.user_id))
        return build_leaderboard(
            pool_ids=pool_ids, runs_per_pool=qualifier.runs_per_pool, scored_runs=scored
        )

    # ============================================================= internals

    async def _require_qualifier(self, qualifier_id: int) -> AsyncQualifier:
        qualifier = await self.repository.get_by_id(qualifier_id)
        if qualifier is None:
            raise ValueError("Qualifier not found")
        return qualifier

    async def _require_pool(self, pool_id: int) -> AsyncQualifierPool:
        pool = await self.pool_repository.get_by_id(pool_id)
        if pool is None:
            raise ValueError("Pool not found")
        return pool

    async def _require_permalink(self, permalink_id: int) -> AsyncQualifierPermalink:
        permalink = await self.permalink_repository.get_by_id(permalink_id)
        if permalink is None:
            raise ValueError("Permalink not found")
        return permalink

    async def _ensure_pool_admin(self, actor: Optional[User], pool: AsyncQualifierPool) -> None:
        qualifier = await self._require_qualifier(pool.qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot administer qualifier"
        )

    async def _ensure_permalink_admin(self, actor: Optional[User], permalink: AsyncQualifierPermalink) -> None:
        pool = await self._require_pool(permalink.pool_id)
        await self._ensure_pool_admin(actor, pool)

    async def _require_own_active_run(self, user: User, run_id: int) -> AsyncQualifierRun:
        run = await self.run_repository.get_by_id(run_id)
        if run is None or run.user_id != user.id:
            raise ValueError("Run not found")
        if run.status != AsyncQualifierRunStatus.IN_PROGRESS:
            raise ValueError("This run is no longer in progress")
        return run

    async def _require_reviewable(self, actor: Optional[User], run_id: int):
        if actor is None:
            raise PermissionError("Cannot review this run")
        run = await self.run_repository.get_by_id(run_id)
        if run is None:
            raise ValueError("Run not found")
        qualifier = await self._require_qualifier(run.qualifier_id)
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(actor, qualifier), "Cannot review this qualifier"
        )
        return run, qualifier

    async def _count_reattempts(self, user_id: int, qualifier_id: int) -> int:
        runs = await self.run_repository.list_for_user(qualifier_id, user_id)
        return sum(1 for r in runs if r.reattempted)

    async def _draw_candidates(
        self, pool: AsyncQualifierPool, user_id: int
    ) -> List[AsyncQualifierPermalink]:
        """Permalinks a player may still draw from a pool: not live-race and not
        already played by them (no-repeat)."""
        permalinks = await self.permalink_repository.list_for_pool(pool.id)
        played = await self.run_repository.played_permalink_ids_for_user_in_pool(pool.id, user_id)
        return [p for p in permalinks if not p.live_race and p.id not in played]

    async def _pick_permalink(
        self, qualifier: AsyncQualifier, pool: AsyncQualifierPool, user_id: int
    ) -> Optional[AsyncQualifierPermalink]:
        """Imbalance-forcing draw: random among candidates unless the pool's
        play-count spread crosses the threshold, then force the least-played."""
        candidates = await self._draw_candidates(pool, user_id)
        if not candidates:
            return None
        counts = await self.run_repository.valid_run_counts_by_permalink_for_pool(pool.id)
        cand_counts = {c.id: counts.get(c.id, 0) for c in candidates}
        threshold = self._imbalance_threshold(qualifier)
        spread = max(cand_counts.values()) - min(cand_counts.values())
        if spread >= threshold:
            fewest = min(cand_counts.values())
            candidates = [c for c in candidates if cand_counts[c.id] == fewest]
        return secrets.choice(candidates)

    async def recompute_par_and_scores(self, permalink_id: int) -> None:
        """Public entry to :meth:`_recompute_par_and_scores` for sibling services
        (the live-race capture path) that add approved runs on a permalink."""
        await self._recompute_par_and_scores(permalink_id)

    async def _recompute_par_and_scores(self, permalink_id: int) -> None:
        """Recompute a permalink's par from its approved finished runs and
        rescore every one of them (par shifts as runs are reviewed/voided)."""
        permalink = await self.permalink_repository.get_by_id(permalink_id)
        if permalink is None:
            return
        approved = await self.run_repository.list_approved_finished_for_permalink(permalink_id)
        elapsed = [r.elapsed_seconds for r in approved if r.elapsed_seconds]
        sample = self._par_sample_size(await self._qualifier_for_permalink(permalink))
        par = compute_par(elapsed, sample)
        await self.permalink_repository.update(
            permalink, par_time=par, par_updated_at=datetime.now(timezone.utc)
        )
        for run in approved:
            score = compute_score(run.elapsed_seconds, par)
            if score != run.score:
                await self.run_repository.update(run, score=score)

    async def _qualifier_for_permalink(self, permalink: AsyncQualifierPermalink) -> Optional[AsyncQualifier]:
        pool = await self.pool_repository.get_by_id(permalink.pool_id)
        if pool is None:
            return None
        return await self.repository.get_by_id(pool.qualifier_id)

    async def _notify_run_reviewed(self, run: AsyncQualifierRun, approved: bool) -> None:
        try:
            await run.fetch_related('user')
            discord_id = run.user.discord_id
            if not discord_id or run.user.is_placeholder:
                return
            from application.services.discord_service import DiscordService
            verb = 'approved' if approved else 'rejected'
            await DiscordService().send_dm(
                int(discord_id),
                f"Your qualifier run was {verb}.",
            )
        except Exception:
            logger.debug("Failed to DM run-reviewed notification", exc_info=True)

    def _ensure_window_open(self, qualifier: AsyncQualifier) -> None:
        if not qualifier.is_active:
            raise ValueError("This qualifier is not active")
        now = datetime.now(timezone.utc)
        if qualifier.opens_at is not None and now < qualifier.opens_at:
            raise ValueError("This qualifier has not opened yet")
        if qualifier.closes_at is not None and now >= qualifier.closes_at:
            raise ValueError("This qualifier has closed")

    @staticmethod
    def _validate_counts(runs_per_pool: int, allowed_reattempts: int):
        if runs_per_pool < 1:
            raise ValueError("Runs per pool must be at least 1")
        if allowed_reattempts < 0:
            raise ValueError("Allowed reattempts cannot be negative")
        return runs_per_pool, allowed_reattempts

    @staticmethod
    def _validate_window(opens_at: Optional[datetime], closes_at: Optional[datetime]) -> None:
        if opens_at is not None and closes_at is not None and closes_at <= opens_at:
            raise ValueError("The close time must be after the open time")

    @staticmethod
    def _par_sample_size(qualifier: Optional[AsyncQualifier]) -> int:
        if qualifier and isinstance(qualifier.config, dict):
            value = qualifier.config.get('par_sample_size')
            if isinstance(value, int) and value >= 1:
                return value
        return DEFAULT_PAR_SAMPLE_SIZE

    @staticmethod
    def _imbalance_threshold(qualifier: AsyncQualifier) -> int:
        if isinstance(qualifier.config, dict):
            value = qualifier.config.get('draw_imbalance_threshold')
            if isinstance(value, int) and value >= 1:
                return value
        return _DEFAULT_IMBALANCE_THRESHOLD

    @staticmethod
    def _display_name(user: User) -> str:
        return user.display_name or user.username or f"User {user.id}"
