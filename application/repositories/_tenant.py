"""Tenant-scoping helpers for the repository layer.

In a logically-multitenant database every scoped query must be constrained to
the current tenant and every scoped insert stamped with it. These helpers keep
each repo method a one-liner change:

    return await scoped(Match.filter(is_active=True)).order_by('scheduled_at')  # read
    return await Match.create(tenant_id=current_tenant_id(), **kwargs)          # write

``current_tenant_id()`` reads the ambient tenant (the request contextvar, the
NiceGUI client stash, or an explicit ``tenant_scope``) and **raises** if none is
set — the safety net that turns a forgotten scope into a loud error instead of a
silent cross-tenant leak. A few repository methods are deliberately cross-tenant
(token lookup by hash, guild→tenant routing, the volunteer-reminder scan, global
identity by discord_id); those never call these helpers and say so in a comment.

Importing ``application.tenant_context`` here is allowed: it is a peer of
``application/services`` (like ``application/events``), not a service, so it does
not cross the repository layer boundary enforced by ``enforce_architecture.py``.
"""

from typing import Optional

from tortoise.queryset import QuerySet

from application.tenant_context import require_tenant_id


def current_tenant_id() -> int:
    """The tenant to scope/stamp by, or raise if there is no tenant in context."""
    return require_tenant_id()


def scoped(qs: QuerySet, tenant_id: Optional[int] = None) -> QuerySet:
    """Constrain a queryset to a tenant.

    ``tenant_id`` defaults to the ambient tenant; pass it explicitly only for a
    deliberate cross-tenant query (e.g. the ``/platform`` super-admin surface
    operating on a chosen tenant).
    """
    tid = tenant_id if tenant_id is not None else require_tenant_id()
    return qs.filter(tenant_id=tid)
