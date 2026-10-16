"""The Challonge communities a tenant's connection covers, mixed into ``ChallongeService``.

A grant names one community (Challonge's ``community_id`` authorize parameter),
so reconnecting used to drop every community nobody retyped. The list lives in
``Tenant.config['challonge_communities']`` rather than on the connection row, so
it survives a disconnect. Any community a linked tournament lives on is added
when the list is read, so a bracket linked from a community never falls off.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from application.errors import require_found
from application.feature_flags import requires_feature
from application.repositories import ChallongeRepository, TenantRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from models import FeatureFlag, User

COMMUNITIES_CONFIG_KEY = 'challonge_communities'


def not_found_message(identifier: str) -> str:
    """Why Challonge 404s a bracket that exists: it's someone else's, outside a community."""
    return (
        f"Challonge can't find '{identifier}'. Check the URL. Challonge only lets "
        f"Wizzrobe read brackets the connected account created or that live in a "
        f"connected community; being an admin on someone else's bracket isn't "
        f"enough, so its owner needs to move it into a community."
    )


@dataclass(frozen=True)
class ChallongeCommunity:
    slug: str
    tournament_count: int

    @property
    def removable(self) -> bool:
        return self.tournament_count == 0


class ChallongeCommunitiesMixin:
    """The collaborators are set up by ``ChallongeService.__init__``."""

    repository: ChallongeRepository
    audit_service: AuditService
    normalize_community: Callable[[Optional[str]], Optional[str]]

    @staticmethod
    async def _saved_communities() -> List[str]:
        tenant = await TenantRepository.get_by_id(require_tenant_id())
        saved = (tenant.config or {}).get(COMMUNITIES_CONFIG_KEY) if tenant else None
        return [s for s in saved if isinstance(s, str)] if isinstance(saved, list) else []

    @staticmethod
    async def _write_saved_communities(slugs: List[str]) -> None:
        tenant = require_found(await TenantRepository.get_by_id(require_tenant_id()), 'Tenant')
        config = dict(tenant.config or {})
        config[COMMUNITIES_CONFIG_KEY] = slugs
        await TenantRepository.update(tenant, config=config)

    @requires_feature(FeatureFlag.CHALLONGE)
    async def remembered_communities(self) -> List[ChallongeCommunity]:
        """Saved communities in the order they were added, then any only a tournament names."""
        counts = await self.repository.linked_tournament_communities()
        slugs = await self._saved_communities()
        slugs += sorted(c for c in counts if c not in slugs)
        return [ChallongeCommunity(s, counts.get(s, 0)) for s in slugs]

    @requires_feature(FeatureFlag.CHALLONGE)
    async def communities_to_grant(self, extra: Optional[str] = None) -> List[str]:
        """Every community a reconnect should ask Challonge for, ``extra`` last.

        Raises ``ValueError`` when ``extra`` was typed but isn't a community subdomain.
        """
        slugs = [c.slug for c in await self.remembered_communities()]
        if extra and extra.strip():
            slug = self.normalize_community(extra)
            if slug is None:
                raise ValueError("That doesn't look like a Challonge community subdomain.")
            if slug not in slugs:
                slugs.append(slug)
        return slugs

    async def _remember_community(self, community: Optional[str]) -> None:
        slug = self.normalize_community(community)
        if slug is None:
            return
        saved = await self._saved_communities()
        if slug not in saved:
            await self._write_saved_communities([*saved, slug])

    @requires_feature(FeatureFlag.CHALLONGE)
    async def remove_community(self, actor: User, community: str) -> None:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            'Only staff can change the Challonge communities',
        )
        counts = await self.repository.linked_tournament_communities()
        in_use = counts.get(community, 0)
        if in_use:
            noun = 'tournament uses' if in_use == 1 else 'tournaments use'
            raise ValueError(
                f'{in_use} linked {noun} {community}. Unlink them before removing it.'
            )
        saved = await self._saved_communities()
        if community not in saved:
            return
        await self._write_saved_communities([s for s in saved if s != community])
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_COMMUNITY_REMOVED, {'community': community},
        )
