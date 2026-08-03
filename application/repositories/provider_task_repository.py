"""Data access for :class:`ProviderTask` — long-running upstream provider calls."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import ProviderTask, ProviderTaskStatus

# Statuses a poller may still pick up. Kept here rather than derived per call so
# the scan's shape is one thing to read.
_ACTIVE = (ProviderTaskStatus.QUEUED, ProviderTaskStatus.RUNNING)


class ProviderTaskRepository(TenantScopedRepository[ProviderTask]):
    model = ProviderTask

    @classmethod
    async def get_with_relations(cls, task_id: int) -> Optional[ProviderTask]:
        """One task with everything a completion needs, scoped to this tenant."""
        return await scoped(
            ProviderTask.filter(id=task_id)
        ).prefetch_related('match', 'preset', 'requested_by').first()

    @classmethod
    async def active_for_match(cls, match_id: int) -> Optional[ProviderTask]:
        """The unfinished task for a match, if one is already in flight.

        What stops a second Generate click from queueing a second upstream
        generation. Each one consumes a real, publicly-numbered seed, so this is
        about not wasting them as much as it is about correctness.
        """
        return await scoped(
            ProviderTask.filter(match_id=match_id, status__in=_ACTIVE)
        ).order_by('-created_at').first()

    @classmethod
    async def latest_for_matches(cls, match_ids: List[int]) -> dict[int, ProviderTask]:
        """Newest active task per match, for rendering many rows in one query.

        The match table asks "is this row rolling?" for every row it draws; one
        query for the page beats one per row.
        """
        if not match_ids:
            return {}
        tasks = await scoped(
            ProviderTask.filter(match_id__in=match_ids, status__in=_ACTIVE)
        ).order_by('created_at')
        return {task.match_id: task for task in tasks}  # type: ignore[attr-defined]

    @classmethod
    async def create_queued(cls, **fields) -> ProviderTask:
        return await ProviderTask.create(
            tenant_id=current_tenant_id(),
            status=ProviderTaskStatus.QUEUED,
            **fields,
        )

    # ------------------------------------------------------------------
    # Poller-facing queries — deliberately cross-tenant
    # ------------------------------------------------------------------

    @classmethod
    async def due_for_poll(cls, limit: int = 50) -> List[ProviderTask]:
        """Every unfinished task across **all tenants**, oldest first.

        Deliberately unscoped: the worker runs outside any request and owns the
        whole queue, then re-enters each task's own ``tenant_scope`` to act on
        it. Oldest first so a backlog drains in the order people asked.
        """
        return await ProviderTask.filter(
            status__in=_ACTIVE
        ).order_by('created_at').limit(limit).prefetch_related(
            'match', 'preset', 'requested_by'
        )

    @classmethod
    async def claim(cls, task: ProviderTask, status: ProviderTaskStatus) -> bool:
        """Move a task to a terminal (or running) state, once.

        The guard against double completion: the update is conditional on the
        row still holding the status we read, so a duplicate tick loses the race
        and returns ``False`` instead of writing a second ``GeneratedSeeds`` and
        sending a second round of DMs. Unscoped by the same reasoning as
        :meth:`due_for_poll` — the caller is the worker, holding a task it just
        read from the global queue.
        """
        completed = (
            datetime.now(timezone.utc) if status in ProviderTaskStatus.terminal() else None
        )
        updated = await ProviderTask.filter(
            id=task.id, status=task.status
        ).update(status=status, completed_at=completed)
        if updated:
            task.status = status
            task.completed_at = completed
        return bool(updated)

    @classmethod
    async def stale(cls, older_than: timedelta) -> List[ProviderTask]:
        """Unfinished tasks that have outlived their budget.

        Cross-tenant for the same reason as :meth:`due_for_poll`: the worker
        sweeps the whole queue, then acts on each task inside its own tenant.
        """
        cutoff = datetime.now(timezone.utc) - older_than
        return await ProviderTask.filter(
            status__in=_ACTIVE, created_at__lt=cutoff
        ).order_by('created_at')
