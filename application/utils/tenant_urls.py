"""Pure helpers for building and validating tenant-qualified URL paths.

Path-mode addressing prefixes every tenant route with ``/t/<slug>`` (surfaced to
request handlers as ``root_path``). These helpers keep post-login / OAuth return
targets inside the originating tenant so a shared-cookie login can't bounce a
user into a *different* community whose stale referrer is still in the session.

Pure (no NiceGUI / session / DB) so they unit-test in isolation; the presentation
layer reads the pending referrer from ``app.storage.user`` and passes it in.
"""

from typing import Any, Sequence

from application.utils.environment import get_base_url
from application.utils.hostname import scheme_for_host

# Routes that must never be used as a post-login return target (they would loop).
AUTH_ROUTES: tuple[str, ...] = ('/login', '/logout', '/oauth/callback')


def tenant_base_url(tenant: Any) -> str:
    """The tenant's canonical absolute base URL (no trailing slash).

    A tenant with a custom ``domain`` is canonically reached there
    (``https://foo.gg``); otherwise it lives under the platform host's path-mode
    prefix (``{BASE_URL}/t/<slug>``). Use this for **outbound deep links** — QR
    codes, web-push ``navigate`` targets, Discord DM links — that are consumed
    outside any request context and so must be absolute and self-contained.
    """
    domain = getattr(tenant, 'domain', None)
    if domain:
        return f'{scheme_for_host(domain)}://{domain}'
    return f'{get_base_url()}/t/{tenant.slug}'


def tenant_url(tenant: Any, path: str) -> str:
    """:func:`tenant_base_url` joined to an absolute in-app ``path`` (leading ``/``)."""
    return f'{tenant_base_url(tenant)}{path}'


def tenant_home(root_path: str) -> str:
    """The current tenant's home path — ``/t/<slug>/`` in path mode, ``/`` bare."""
    return f'{root_path}/'


def sanitize_return_path(
    root_path: str,
    referrer: Any,
    *,
    auth_routes: Sequence[str] = AUTH_ROUTES,
) -> str:
    """Where to send a user after login for the tenant at ``root_path``.

    Honors ``referrer`` only if it is a string that belongs to this tenant (shares
    its ``root_path`` prefix) and is not itself an auth route; otherwise returns
    the tenant home. ``root_path`` is ``''`` on the bare platform host.
    """
    home = tenant_home(root_path)
    if not isinstance(referrer, str) or not referrer:
        return home
    if root_path:
        if not (referrer == root_path or referrer.startswith(root_path + '/')):
            return home
        local = referrer[len(root_path):] or '/'
    else:
        local = referrer
    if local.split('?', 1)[0] in auth_routes:
        return home
    return referrer
