"""Profile Nudge Repository - Data Access Layer

Per-member dismissals of a community's recommended profile items. The rules
themselves are tenant config (``Tenant.config['profile_nudges']``), read and
written through :class:`TenantRepository`.
"""

from models import ProfileNudgeDismissal

from ._tenant import current_tenant_id, scoped


class ProfileNudgeRepository:
    """Data access for :class:`ProfileNudgeDismissal`."""

    @staticmethod
    async def dismissed_checks(user_id: int) -> set[str]:
        """The checks ``user_id`` has dismissed in the current community."""
        rows = await scoped(ProfileNudgeDismissal.filter(user_id=user_id)).values_list('check', flat=True)
        return {str(r) for r in rows}

    @staticmethod
    async def dismiss(user_id: int, check: str) -> bool:
        """Record a dismissal. Idempotent; returns whether the row is new."""
        _row, created = await ProfileNudgeDismissal.get_or_create(
            tenant_id=current_tenant_id(), user_id=user_id, check=check,
        )
        return created

    @staticmethod
    async def clear_check(check: str) -> int:
        """Forget every member's dismissal of ``check`` in the current community."""
        return await scoped(ProfileNudgeDismissal.filter(check=check)).delete()
