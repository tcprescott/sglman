"""SpeedGaming sync service (PR 7) — tenant-facing config + on-demand sync.

The management layer over the SG ETL: CRUD of :class:`SpeedGamingEventLink`
rows (which SG event slug feeds which tournament) and an on-demand "sync now"
that runs :class:`SpeedGamingETLService` for one link. All mutations are gated by
:meth:`AuthService.can_manage_sync` (STAFF / super-admin / ``SYNC_ADMIN``) and
audited. The background worker calls the ETL directly as the system user; this
service is the human-driven surface.
"""

from typing import Any, Dict, List, Optional

from application.repositories import (
    SpeedGamingEpisodeRepository,
    SpeedGamingEventLinkRepository,
    TournamentRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.speedgaming_etl_service import SpeedGamingETLService, SyncResult
from models import SpeedGamingEpisode, SpeedGamingEventLink, User


class SpeedGamingSyncService:
    """CRUD + on-demand sync for tenant SpeedGaming event links."""

    def __init__(self) -> None:
        self.repository = SpeedGamingEventLinkRepository()
        self.episode_repository = SpeedGamingEpisodeRepository()
        self.audit_service = AuditService()

    async def list_links(self, actor: Optional[User]) -> List[SpeedGamingEventLink]:
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        return await self.repository.list_all()

    async def list_episodes(
        self, actor: Optional[User], event_link_id: int
    ) -> List[SpeedGamingEpisode]:
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        return await self.episode_repository.list_for_link(event_link_id)

    async def create_link(
        self,
        actor: Optional[User],
        *,
        tournament_id: int,
        event_slug: str,
        content_type: Optional[str] = None,
        sync_interval_minutes: int = 15,
        lookahead_hours: int = 72,
        active: bool = True,
    ) -> SpeedGamingEventLink:
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        event_slug = (event_slug or '').strip()
        if not event_slug:
            raise ValueError("Event slug is required")
        tournament = await TournamentRepository.get_by_id(tournament_id)
        if tournament is None:
            raise ValueError("Tournament not found")
        if await self.repository.get_by_natural_key(tournament_id, event_slug) is not None:
            raise ValueError(f"'{event_slug}' is already linked to this tournament")
        link = await self.repository.create(
            tournament_id=tournament_id,
            event_slug=event_slug,
            content_type=(content_type or '').strip() or None,
            sync_interval_minutes=max(1, sync_interval_minutes),
            lookahead_hours=max(1, lookahead_hours),
            active=active,
        )
        await self.audit_service.write_log(
            actor, AuditActions.SG_EVENT_LINK_CREATED,
            {'event_link_id': link.id, 'tournament_id': tournament_id, 'event_slug': event_slug},
        )
        return link

    async def update_link(
        self,
        actor: Optional[User],
        link_id: int,
        *,
        event_slug: Optional[str] = None,
        content_type: Optional[str] = None,
        sync_interval_minutes: Optional[int] = None,
        lookahead_hours: Optional[int] = None,
        active: Optional[bool] = None,
    ) -> SpeedGamingEventLink:
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        link = await self._require(link_id)
        changes: Dict[str, Any] = {}
        if event_slug is not None:
            new_slug = event_slug.strip()
            if not new_slug:
                raise ValueError("Event slug is required")
            if new_slug != link.event_slug:
                existing = await self.repository.get_by_natural_key(link.tournament_id, new_slug)
                if existing is not None and existing.id != link.id:
                    raise ValueError(f"'{new_slug}' is already linked to this tournament")
            changes['event_slug'] = new_slug
        if content_type is not None:
            changes['content_type'] = content_type.strip() or None
        if sync_interval_minutes is not None:
            changes['sync_interval_minutes'] = max(1, sync_interval_minutes)
        if lookahead_hours is not None:
            changes['lookahead_hours'] = max(1, lookahead_hours)
        if active is not None:
            changes['active'] = active
        if changes:
            link = await self.repository.update(link, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.SG_EVENT_LINK_UPDATED,
            {'event_link_id': link.id, 'changes': list(changes.keys())},
        )
        return link

    async def delete_link(self, actor: Optional[User], link_id: int) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        link = await self._require(link_id)
        await self.audit_service.write_log(
            actor, AuditActions.SG_EVENT_LINK_DELETED,
            {'event_link_id': link.id, 'event_slug': link.event_slug},
        )
        await self.repository.delete(link)

    async def sync_now(self, actor: Optional[User], link_id: int) -> SyncResult:
        """Run the ETL for one link on demand.

        Gated by ``can_manage_sync``; the human actor is passed through so the
        resulting audit/event rows attribute to them (the background worker uses
        the system user instead). Assumes the caller's tenant is in scope.
        """
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor), "Cannot manage SpeedGaming sync"
        )
        link = await self._require(link_id)
        return await SpeedGamingETLService().sync_event_link(link, actor=actor)

    async def _require(self, link_id: int) -> SpeedGamingEventLink:
        link = await self.repository.get_by_id(link_id)
        if link is None:
            raise ValueError("SpeedGaming event link not found")
        return link
