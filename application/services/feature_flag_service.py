"""Feature Flag Service — two-tier per-tenant feature gating.

A feature flag exists only for a deliberately-gated feature (catalog in
``application/feature_flags.py``); flags default OFF. Governance is two-tier:

* **Super-admin** grants a flag's *availability* to a tenant on ``/platform``.
* That tenant's **STAFF** then *enable* it for their community (Admin → Features).

A feature is live only when it is BOTH available and enabled. :meth:`is_enabled`
is the single read every gated page / admin tab / service guard calls; a missing
row means off. Unknown/legacy flag keys persisted in the DB are ignored, so
retiring a flag never breaks a read.

The read helpers tolerate *no tenant in scope* (the platform surface) by
returning "off" instead of raising — gating a page that a super-admin might load
off-tenant must fail safe, not explode. The management methods are the audited,
role-gated writes.
"""

from typing import Any, Dict, List, Optional, Set

from application.feature_flags import FEATURE_FLAG_REGISTRY, all_specs, spec_for
from application.repositories.feature_flag_repository import TenantFeatureFlagRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import get_current_tenant_id
from models import FeatureFlag, Role, User


class FeatureFlagService:
    """Reads + two-tier management of per-tenant feature flags."""

    def __init__(self) -> None:
        self.repository = TenantFeatureFlagRepository()
        self.audit_service = AuditService()

    # ---- reads (hot path) -------------------------------------------------

    async def is_enabled(self, flag: FeatureFlag) -> bool:
        """Whether ``flag`` is live for the ambient tenant (available AND enabled)."""
        if get_current_tenant_id() is None:
            return False
        row = await self.repository.get_for_current_tenant(flag.value)
        return bool(row and row.available and row.enabled)

    async def enabled_flags(self) -> Set[FeatureFlag]:
        """The set of flags live for the ambient tenant, in one query.

        Prefer this over N :meth:`is_enabled` calls when a page decides several
        flags at once (e.g. building the admin tab list).
        """
        if get_current_tenant_id() is None:
            return set()
        rows = await self.repository.map_for_current_tenant()
        live: Set[FeatureFlag] = set()
        for flag in FEATURE_FLAG_REGISTRY:
            row = rows.get(flag.value)
            if row and row.available and row.enabled:
                live.add(flag)
        return live

    async def ensure_enabled(self, flag: FeatureFlag) -> None:
        """Raise ``ValueError`` if ``flag`` is not live for the ambient tenant.

        The server-side defense-in-depth companion to hiding a feature's UI: a
        gated create/entry service method calls this so the REST API and any
        other programmatic path cannot use a feature a community has not turned
        on.
        """
        if not await self.is_enabled(flag):
            raise ValueError(
                f"The {spec_for(flag).label} feature is not enabled for this community."
            )

    # ---- tenant tier: STAFF toggle ``enabled`` within availability --------

    async def list_for_tenant_admin(self, actor: Optional[User]) -> List[Dict[str, Any]]:
        """Every flag's state for the ambient tenant, for the admin Features tab."""
        await self._ensure_staff(actor)
        rows = await self.repository.map_for_current_tenant()
        return [self._project(spec, rows.get(spec.flag.value)) for spec in all_specs()]

    async def set_tenant_enabled(
        self, actor: Optional[User], flag: FeatureFlag, enabled: bool
    ) -> None:
        await self._ensure_staff(actor)
        row = await self.repository.get_for_current_tenant(flag.value)
        if not (row and row.available):
            raise ValueError(
                f"The {spec_for(flag).label} feature is not available for this "
                'community. Ask a platform administrator to enable it.'
            )
        await self.repository.set_enabled_for_current_tenant(flag.value, enabled)
        await self.audit_service.write_log(
            actor,
            AuditActions.FEATURE_FLAG_ENABLED if enabled else AuditActions.FEATURE_FLAG_DISABLED,
            {'flag': flag.value},
        )

    # ---- platform tier: super-admin grants availability per tenant --------

    async def list_for_tenant(self, actor: Optional[User], tenant_id: int) -> List[Dict[str, Any]]:
        """Every flag's state for a chosen tenant, for the /platform surface."""
        await self._ensure_super_admin(actor)
        rows = {r.flag: r for r in await self.repository.list_for_tenant(tenant_id)}
        return [self._project(spec, rows.get(spec.flag.value)) for spec in all_specs()]

    async def set_availability(
        self, actor: Optional[User], tenant_id: int, flag: FeatureFlag, available: bool
    ) -> None:
        await self._ensure_super_admin(actor)
        # Leave ``enabled`` untouched: revoking availability makes the feature
        # off (effective = available AND enabled) while preserving the tenant's
        # own choice, so re-granting restores it.
        await self.repository.set_availability_for_tenant(tenant_id, flag.value, available)
        await self.audit_service.write_log(
            actor, AuditActions.FEATURE_FLAG_AVAILABILITY_SET,
            {'tenant_id': tenant_id, 'flag': flag.value, 'available': available},
        )

    # ---- internals --------------------------------------------------------

    @staticmethod
    def _project(spec, row: Optional[Any]) -> Dict[str, Any]:
        return {
            'flag': spec.flag.value,
            'label': spec.label,
            'description': spec.description,
            'category': spec.category,
            'available': bool(row and row.available),
            'enabled': bool(row and row.enabled),
            'live': bool(row and row.available and row.enabled),
        }

    @staticmethod
    async def _ensure_super_admin(actor: Optional[User]) -> None:
        await AuthService.ensure(
            await AuthService.is_super_admin(actor),
            'Only super-admins can manage feature availability',
        )

    @staticmethod
    async def _ensure_staff(actor: Optional[User]) -> None:
        allowed = await AuthService.is_super_admin(actor) or await AuthService.has_role(
            actor, Role.STAFF
        )
        await AuthService.ensure(allowed, 'Only staff can manage community features')
