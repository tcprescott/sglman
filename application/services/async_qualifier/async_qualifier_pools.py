"""Async qualifier — the pool and permalink management surface.

What a qualifier admin does before anyone runs: name the pools, decide which
preset each rolls from, and fill them with permalinks (pasted, or rolled from the
preset). Every method here is admin-gated through the qualifier that owns the
pool, so the gate is one hop away from the row being edited rather than passed in.

Mixed into :class:`AsyncQualifierService` — the same composition
``application/services/_bracket/`` uses — so the orchestration module keeps room
for the run lifecycle and review, which is where its rules actually live.
"""

from typing import List, Optional, Sequence

from application.errors import NotFoundError, require_found
from application.feature_flags import requires_feature
from application.services.async_qualifier import async_qualifier_access as access
from application.services.audit_service import AuditActions
from application.services.seedgen_service import SeedGenerationService
from application.tenant_context import require_tenant_id
from models import (
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    FeatureFlag,
    GeneratedSeeds,
    User,
)

# A single roll takes on the order of a minute per seed against a live generator,
# so a batch is bounded to something an admin can wait out in one page load.
MAX_ROLL_COUNT = 25


class PoolManagementMixin:
    """Pool + permalink CRUD. Requires the host's repositories and audit service."""

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
        if count < 1 or count > MAX_ROLL_COUNT:
            raise ValueError(f"Roll count must be between 1 and {MAX_ROLL_COUNT}")
        # Task-queue backends are not wired into this batch yet. Each roll would
        # take minutes and complete independently, which breaks the "abort with
        # nothing half-written" property below — a pool would sit part-filled
        # with no way to tell a slow roll from a lost one. Refused here rather
        # than only in the preset picker, because a pool created before DK64
        # became asynchronous can already point at one.
        if pool.preset.randomizer in SeedGenerationService.ASYNC_RANDOMIZERS:
            raise ValueError(
                f"'{pool.preset.randomizer}' rolls seeds asynchronously and cannot "
                "fill a qualifier pool yet. Pick a preset for another randomizer."
            )
        # A keyed randomizer raises on the first roll when this community has not
        # configured its credential — before any permalink row is created, so the
        # batch aborts with nothing half-written.
        seedgen = SeedGenerationService()
        created: List[AsyncQualifierPermalink] = []
        for _ in range(count):
            call = await seedgen.generate_seed_call(
                pool.preset.randomizer, pool.preset, surface='qualifier',
            )
            # Same provenance record a match seed gets: the pool records which
            # preset it rolls from, but only the snapshot records what that preset
            # *said* at the moment this permalink was made.
            seed = await GeneratedSeeds.create(
                tenant_id=require_tenant_id(),
                seed_url=call.value.url,
                seed_info=f"Rolled for qualifier pool {pool_id}",
                randomizer=pool.preset.randomizer,
                preset_id=pool.preset_id,  # type: ignore[attr-defined]
                settings_snapshot=call.value.settings,
                rolled_by_id=actor.id if actor is not None else None,
                provider_meta=call.as_meta(),
            )
            created.append(await self.permalink_repository.create(
                pool_id=pool_id, url=call.value.url, generated_seed_id=seed.id,
            ))
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

    # --------------------------------------------------------------- gateways

    async def _require_pool(self, pool_id: int) -> AsyncQualifierPool:
        return await access.require_pool(self.pool_repository, pool_id)

    async def _require_permalink(self, permalink_id: int) -> AsyncQualifierPermalink:
        return await access.require_permalink(self.permalink_repository, permalink_id)

    async def _ensure_pool_admin(self, actor: Optional[User], pool: AsyncQualifierPool) -> None:
        qualifier = await self._require_qualifier(pool.qualifier_id)
        await access.ensure_qualifier_admin(actor, qualifier)

    async def _ensure_permalink_admin(
        self, actor: Optional[User], permalink: AsyncQualifierPermalink
    ) -> None:
        pool = await self._require_pool(permalink.pool_id)
        await self._ensure_pool_admin(actor, pool)
