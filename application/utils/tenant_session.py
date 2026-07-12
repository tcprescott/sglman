"""Per-tenant namespacing for session (``app.storage.user``) UI state.

Path-mode tenants share one session cookie on the platform host, so any
tenant-scoped UI state written flat into ``app.storage.user`` would leak across
communities: a ``tournament_filter`` holding tenant A's tournament id is
meaningless — and points at the wrong row — once the user switches to tenant B.
Namespace such state under ``app.storage.user['by_tenant'][str(tid)]`` keyed on
the current tenant.

Identity keys (``discord_id``, ``username``, ``avatar``, ``authenticated``) and
the OAuth CSRF/return keys intentionally stay flat: one login is shared across
every tenant, and the OAuth callbacks run on the bare platform host with no
tenant in scope, so they could not read a namespaced key. Genuinely global
preferences (dark mode) stay flat too.

NiceGUI is imported lazily so the module stays import-safe from every layer;
``get_current_tenant_id`` resolves via the request contextvar or the per-client
stash, so these helpers work both at page build and inside websocket handlers.
When there is no tenant in scope the helpers fall back to flat storage rather
than raising.
"""

from typing import Any, Optional

from application.tenant_context import get_current_tenant_id


def tenant_session_get(key: str, default: Optional[Any] = None) -> Any:
    """Read a tenant-scoped session value for the current tenant."""
    from nicegui import app
    tid = get_current_tenant_id()
    if tid is None:
        return app.storage.user.get(key, default)
    by_tenant = app.storage.user.get('by_tenant') or {}
    return by_tenant.get(str(tid), {}).get(key, default)


def tenant_session_set(key: str, value: Any) -> None:
    """Write a tenant-scoped session value for the current tenant.

    Reassigns the top-level ``by_tenant`` key (rather than mutating the nested
    dict in place) so NiceGUI's storage observer persists the change.
    """
    from nicegui import app
    tid = get_current_tenant_id()
    if tid is None:
        app.storage.user[key] = value
        return
    by_tenant = dict(app.storage.user.get('by_tenant') or {})
    bucket = dict(by_tenant.get(str(tid)) or {})
    bucket[key] = value
    by_tenant[str(tid)] = bucket
    app.storage.user['by_tenant'] = by_tenant
