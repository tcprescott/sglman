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
  :mod:`application.services.async_qualifier.async_qualifier_scoring`; the board obeys the
  **active-window information lockdown** (pool/par/other entrants' runs are
  staff-only until the qualifier closes).

Raises :class:`ValueError` for user errors and :class:`PermissionError` for authz
(both surfaced by the UI); audits every state change and mirrors run
submitted/reviewed onto the event bus. Discord DMs (window-open, run-reviewed) are
best-effort and never block a state change.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from tortoise.transactions import in_transaction

from application.errors import NotFoundError, require_found
from application.events import Event, EventType, event_bus
from application.repositories import (
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierReviewNoteRepository,
    AsyncQualifierRunRepository,
    PresetRepository,
)
from application.services.async_qualifier import async_qualifier_access as access
from application.services.async_qualifier import async_qualifier_notifications as notifications
from application.services.async_qualifier import async_qualifier_rules as rules
from application.services.async_qualifier.async_qualifier_config import validate_async_qualifier_config
from application.services.async_qualifier.async_qualifier_draw import AsyncQualifierDraw
from application.services.async_qualifier.async_qualifier_scoring import (
    LeaderboardEntry,
    ScoredRun,
    build_leaderboard,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.seedgen_service import SeedGenerationService
from application.feature_flags import requires_feature
from models import (
    FeatureFlag,
    AsyncQualifier,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierReviewStatus,
    AsyncQualifierRun,
    AsyncQualifierRunStatus,
    User,
)

logger = logging.getLogger(__name__)

# Upper bound on a submitted finish time (7 days). The finish time is free text
# the runner types, so without a ceiling a typo ("100:00:00" → 360,000s is fine,
# but "1000000:00:00" is not) reaches the column as an out-of-range integer. Any
# real qualifier run is orders of magnitude under this.
MAX_RUN_SECONDS = 7 * 24 * 60 * 60

# Terminal run states a finished/forfeit/DQ run can be in (used for slot counting).
_TERMINAL = {
    AsyncQualifierRunStatus.FINISHED,
    AsyncQualifierRunStatus.FORFEIT,
    AsyncQualifierRunStatus.DISQUALIFIED,
}


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
        self.draw = AsyncQualifierDraw(
            repository=self.repository,
            pool_repository=self.pool_repository,
            permalink_repository=self.permalink_repository,
            run_repository=self.run_repository,
        )

    # ============================================================ management

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_qualifiers(self, actor: Optional[User]) -> List[AsyncQualifier]:
        await access.ensure_qualifier_admin(actor, message="Cannot administer qualifiers")
        return await self.repository.list_all()

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_qualifier(self, actor: Optional[User], qualifier_id: int) -> AsyncQualifier:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        return qualifier

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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
        await access.ensure_qualifier_admin(actor, message="Cannot administer qualifiers")
        name = (name or '').strip()
        if not name:
            raise ValueError("Qualifier name is required")
        runs_per_pool, allowed_reattempts = rules.validate_counts(runs_per_pool, allowed_reattempts)
        rules.validate_window(opens_at, closes_at)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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
        await access.ensure_qualifier_admin(actor, qualifier)
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
            rules.validate_window(new_opens, new_closes)
            changes['opens_at'] = new_opens
            changes['closes_at'] = new_closes
        new_rpp = qualifier.runs_per_pool if runs_per_pool is None else runs_per_pool
        new_ar = qualifier.allowed_reattempts if allowed_reattempts is None else allowed_reattempts
        if runs_per_pool is not None or allowed_reattempts is not None:
            new_rpp, new_ar = rules.validate_counts(new_rpp, new_ar)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def delete_qualifier(self, actor: Optional[User], qualifier_id: int) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_DELETED,
            {'qualifier_id': qualifier.id, 'name': qualifier.name},
        )
        await self.repository.delete(qualifier)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def add_admin(self, actor: Optional[User], qualifier_id: int, target: User) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        await qualifier.admins.add(target)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_ADMIN_GRANTED,
            {'qualifier_id': qualifier.id, 'target_user_id': target.id},
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def remove_admin(self, actor: Optional[User], qualifier_id: int, target: User) -> None:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        await qualifier.admins.remove(target)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_ADMIN_REVOKED,
            {'qualifier_id': qualifier.id, 'target_user_id': target.id},
        )

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_admins(self, actor: Optional[User], qualifier_id: int) -> List[User]:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        return await qualifier.admins.all()

    # ------------------------------------------------------------------ pools

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_pools(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierPool]:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        return await self.pool_repository.list_for_qualifier(qualifier_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def create_pool(
        self,
        actor: Optional[User],
        qualifier_id: int,
        *,
        name: str,
        preset_id: Optional[int] = None,
    ) -> AsyncQualifierPool:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)
        name = (name or '').strip()
        if not name:
            raise ValueError("Pool name is required")
        if preset_id is not None and await self.preset_repository.get_by_id(preset_id) is None:
            raise NotFoundError("Preset not found")
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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
                raise NotFoundError("Preset not found")
            changes['preset_id'] = preset_id
        pool = await self.pool_repository.update(pool, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_POOL_UPDATED,
            {'pool_id': pool.id, 'fields': sorted(changes.keys())},
        )
        return pool

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def delete_pool(self, actor: Optional[User], pool_id: int) -> None:
        pool = await self._require_pool(pool_id)
        await self._ensure_pool_admin(actor, pool)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_POOL_DELETED,
            {'pool_id': pool.id, 'qualifier_id': pool.qualifier_id},
        )
        await self.pool_repository.delete(pool)

    # ------------------------------------------------------------- permalinks

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def roll_permalinks(
        self, actor: Optional[User], pool_id: int, *, count: int
    ) -> List[AsyncQualifierPermalink]:
        """Roll ``count`` fresh seeds from the pool's preset into permalinks."""
        pool = require_found(await self.pool_repository.get_with_permalinks(pool_id), "Pool")
        await self._ensure_pool_admin(actor, pool)
        if pool.preset is None:
            raise ValueError("Pool has no preset to roll from")
        if count < 1 or count > 25:
            raise ValueError("Roll count must be between 1 and 25")
        # A keyed randomizer raises on the first roll when this community has not
        # configured its credential — before any permalink row is created, so the
        # batch aborts with nothing half-written.
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def delete_permalink(self, actor: Optional[User], permalink_id: int) -> None:
        permalink = await self._require_permalink(permalink_id)
        await self._ensure_permalink_admin(actor, permalink)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_PERMALINK_DELETED,
            {'permalink_id': permalink.id, 'pool_id': permalink.pool_id},
        )
        await self.permalink_repository.delete(permalink)

    # =============================================================== player

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
        and at least one undrawn non-live-race permalink left."""
        qualifier = await self._require_qualifier(qualifier_id)
        rules.ensure_window_open(qualifier)
        if user is None:
            return []
        pools = await self.pool_repository.list_for_qualifier(qualifier_id)
        eligible: List[AsyncQualifierPool] = []
        for pool in pools:
            candidates = await self.draw.draw_candidates(pool, user.id)
            used = await self.run_repository.count_valid_runs_for_user_in_pool(pool.id, user.id)
            if candidates and used < qualifier.runs_per_pool:
                eligible.append(pool)
        return eligible

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
    async def start_run(self, user: User, qualifier_id: int, pool_id: int) -> AsyncQualifierRun:
        """Atomically draw a permalink and open a run (reveal == start).

        Row-locks the player so concurrent clicks serialize, enforces one active
        run + the per-pool cap + no-repeat inside the transaction, then picks a
        permalink by imbalance-forcing fairness.
        """
        if user is None:
            raise ValueError("You must be logged in to start a run")
        qualifier = await self._require_qualifier(qualifier_id)
        rules.ensure_window_open(qualifier)
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
            permalink = await self.draw.pick_permalink(qualifier, pool, user.id)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def submit_run(
        self, user: User, run_id: int, *, elapsed_seconds: int, runner_vod_url: Optional[str] = None
    ) -> AsyncQualifierRun:
        run = await self._require_own_active_run(user, run_id)
        if elapsed_seconds is None or elapsed_seconds <= 0:
            raise ValueError("Finish time must be a positive number of seconds")
        if elapsed_seconds > MAX_RUN_SECONDS:
            raise ValueError("Finish time is longer than a week — check the value you entered.")
        # Both bounds above come before the clock is read: a nonsense value is
        # refused as nonsense, not as a discrepancy.
        measured = rules.measure_elapsed(run.started_at)
        if rules.classify_claim(elapsed_seconds, measured) is rules.ClaimVerdict.IMPOSSIBLE:
            raise ValueError(rules.describe_claim(elapsed_seconds, measured))
        run = await self.run_repository.update(
            run,
            status=AsyncQualifierRunStatus.FINISHED,
            finished_at=datetime.now(timezone.utc),
            elapsed_seconds=elapsed_seconds,
            measured_seconds=measured,
            runner_vod_url=(runner_vod_url or '').strip() or None,
            review_status=AsyncQualifierReviewStatus.PENDING,
        )
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_SUBMITTED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id, 'elapsed_seconds': elapsed_seconds,
             'measured_seconds': measured},
        )
        event_bus.publish(Event.create(EventType.ASYNC_QUALIFIER_RUN_SUBMITTED, {
            'run_id': run.id, 'qualifier_id': run.qualifier_id, 'user_id': user.id,
        }, user))
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
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

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def reattempt_run(self, user: User, run_id: int, *, reason: str) -> AsyncQualifierRun:
        """Void a prior terminal run so its pool slot frees up for a fresh draw.

        Requires a reason, is limited by ``allowed_reattempts``, and never touches
        an in-progress run (finish or forfeit it first).
        """
        run = await self.run_repository.get_by_id(run_id)
        if run is None or run.user_id != user.id:
            raise NotFoundError("Run not found")
        reason = (reason or '').strip()
        if not reason:
            raise ValueError("A reattempt reason is required")
        if run.reattempted:
            raise ValueError("This run was already reattempted")
        if run.status not in _TERMINAL:
            raise ValueError("Only a finished or forfeited run can be reattempted")
        qualifier = await self._require_qualifier(run.qualifier_id)
        allowance = rules.ReattemptAllowance(
            spent=await self._count_reattempts(user.id, run.qualifier_id),
            allowed=qualifier.allowed_reattempts,
        )
        if allowance.remaining < 1:
            raise ValueError("No reattempts remaining")
        run = await self._void_run(run, reason=reason)
        await self.audit_service.write_log(
            user, AuditActions.ASYNC_QUALIFIER_RUN_REATTEMPTED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id},
        )
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def grant_reattempt(
        self, actor: Optional[User], run_id: int, *, reason: str
    ) -> AsyncQualifierRun:
        """Void a runner's terminal run on their behalf, ignoring their allowance.

        The reviewer's override for a mis-clicked forfeit or a bad seed. Requires
        qualifier-admin and a reason; unlike :meth:`reattempt_run` it does not
        consume ``allowed_reattempts``, because the run being voided is not the
        runner's mistake. Deliberately does not check the window either — a
        reviewer may need to void a run after the qualifier closes.
        """
        run, qualifier = await self._require_reviewable(
            actor, run_id, message="Cannot grant a reattempt in this qualifier",
        )
        reason = (reason or '').strip()
        if not reason:
            raise ValueError("A reattempt reason is required — the runner is told what you write here.")
        if run.reattempted:
            raise ValueError("This run was already reattempted")
        if run.status not in _TERMINAL:
            raise ValueError("Only a finished or forfeited run can be reattempted")
        run = await self._void_run(run, reason=reason, granted_by=actor)
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_REATTEMPT_GRANTED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id,
             'target_user_id': run.user_id, 'reason': reason},
        )
        await notifications.notify_reattempt_granted(run, reason)
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

    # =============================================================== review

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_review_queue(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierRun]:
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier, message="Cannot review this qualifier")
        return await self.run_repository.list_pending_review(qualifier_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_runs(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierRun]:
        """Every run in the qualifier, for the reviewer's runs list.

        The review queue only returns finished+pending runs, so a forfeit — which
        is written straight to approved/score 0 — is unreachable from it. This is
        the read that lets a reviewer find one and grant a reattempt on it.
        """
        qualifier = await self._require_qualifier(qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier, message="Cannot review this qualifier")
        return await self.run_repository.list_for_qualifier(qualifier_id)

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def claim_run(self, actor: Optional[User], run_id: int) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        if run.review_claimed_by_id and run.review_claimed_by_id != actor.id:
            raise ValueError("Another reviewer has already claimed this run")
        run = await self.run_repository.update(
            run, review_claimed_by_id=actor.id, review_claimed_at=datetime.now(timezone.utc)
        )
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def release_claim(self, actor: Optional[User], run_id: int) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        run = await self.run_repository.update(
            run, review_claimed_by_id=None, review_claimed_at=None
        )
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def review_run(
        self, actor: Optional[User], run_id: int, *, approved: bool, note: Optional[str] = None
    ) -> AsyncQualifierRun:
        run, qualifier = await self._require_reviewable(actor, run_id)
        if run.user_id == actor.id:
            raise ValueError("You cannot review your own run")
        if run.status != AsyncQualifierRunStatus.FINISHED:
            raise ValueError("Only a finished run can be reviewed")
        note = (note or '').strip()
        # Above the note write and the status update, so a reasonless rejection
        # changes nothing at all.
        if not approved and not note:
            raise ValueError("A rejection needs a reason — the runner is told what you write here.")
        new_status = (
            AsyncQualifierReviewStatus.APPROVED if approved else AsyncQualifierReviewStatus.REJECTED
        )
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
            await self.draw.recompute_par_and_scores(run.permalink_id)
            run = await self.run_repository.get_by_id(run.id) or run
        await self.audit_service.write_log(
            actor, AuditActions.ASYNC_QUALIFIER_RUN_REVIEWED,
            {'run_id': run.id, 'qualifier_id': run.qualifier_id, 'approved': approved},
        )
        event_bus.publish(Event.create(EventType.ASYNC_QUALIFIER_RUN_REVIEWED, {
            'run_id': run.id, 'qualifier_id': run.qualifier_id,
            'user_id': run.user_id, 'approved': approved,
        }, actor))
        await notifications.notify_run_reviewed(run, approved, reason=note)
        return run

    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_run_notes(self, actor: Optional[User], run_id: int):
        run = await access.require_run(self.run_repository, run_id)
        qualifier = await self._require_qualifier(run.qualifier_id)
        # A reviewer sees any run's notes; a runner sees their own.
        if not (await AuthService.can_admin_qualifier(actor, qualifier)
                or (actor is not None and run.user_id == actor.id)):
            raise PermissionError("Cannot view these review notes")
        return await self.note_repository.list_for_run(run_id)

    # =========================================================== leaderboard

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

    # ============================================================= internals

    async def _require_qualifier(self, qualifier_id: int) -> AsyncQualifier:
        return await access.require_qualifier(self.repository, qualifier_id)

    async def _require_pool(self, pool_id: int) -> AsyncQualifierPool:
        return await access.require_pool(self.pool_repository, pool_id)

    async def _require_permalink(self, permalink_id: int) -> AsyncQualifierPermalink:
        return await access.require_permalink(self.permalink_repository, permalink_id)

    async def _ensure_pool_admin(self, actor: Optional[User], pool: AsyncQualifierPool) -> None:
        qualifier = await self._require_qualifier(pool.qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)

    async def _ensure_permalink_admin(self, actor: Optional[User], permalink: AsyncQualifierPermalink) -> None:
        pool = await self._require_pool(permalink.pool_id)
        await self._ensure_pool_admin(actor, pool)

    async def _require_own_active_run(self, user: User, run_id: int) -> AsyncQualifierRun:
        run = await self.run_repository.get_by_id(run_id)
        if run is None or run.user_id != user.id:
            raise NotFoundError("Run not found")
        if run.status != AsyncQualifierRunStatus.IN_PROGRESS:
            raise ValueError("This run is no longer in progress")
        return run

    async def _require_reviewable(
        self, actor: Optional[User], run_id: int, *, message: str = "Cannot review this qualifier"
    ):
        if actor is None:
            raise PermissionError("Cannot review this run")
        run = await access.require_run(self.run_repository, run_id)
        qualifier = await self._require_qualifier(run.qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier, message=message)
        return run, qualifier

    async def _count_reattempts(self, user_id: int, qualifier_id: int) -> int:
        """Reattempts this player spent themselves — a reviewer's grant is not theirs."""
        runs = await self.run_repository.list_for_user(qualifier_id, user_id)
        return sum(1 for r in runs if r.reattempted and r.reattempt_granted_by_id is None)

    async def recompute_par_and_scores(self, permalink_id: int) -> None:
        """Public entry for sibling services (the live-race capture path) that add
        approved runs on a permalink and need its par + scores refreshed."""
        await self.draw.recompute_par_and_scores(permalink_id)

    async def _void_run(
        self, run: AsyncQualifierRun, *, reason: str, granted_by: Optional[User] = None
    ) -> AsyncQualifierRun:
        """Mark a terminal run reattempted, freeing its pool slot, and refresh par.

        Shared by the runner's own reattempt and a reviewer's grant so neither can
        forget the par refresh — a voided run left in the scoring inputs silently
        skews every score on its permalink.
        """
        run = await self.run_repository.update(
            run, reattempted=True, reattempt_reason=reason,
            reattempt_granted_by_id=granted_by.id if granted_by is not None else None,
        )
        if run.permalink_id is not None:
            await self.draw.recompute_par_and_scores(run.permalink_id)
        return run
