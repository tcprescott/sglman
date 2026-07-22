"""Host-mode OAuth + domain-validation tests (Design A).

Covers the make-or-break invariant: the Discord ``redirect_uri`` is built from a
resolved tenant's **stored** domain, https-forced, so the ``/login`` and callback
legs produce a byte-identical string and nothing reflected can be injected —
plus the ``Tenant.domain`` normalization contract and the secondary-provider
custom-domain detour.
"""

import importlib
from types import SimpleNamespace

import pytest

from application.tenant_context import (
    reset_host_mode,
    reset_tenant_id,
    set_host_mode,
    set_tenant_id,
)


@pytest.fixture
def auth(monkeypatch):
    """``pages.auth`` imported under MOCK_DISCORD (its live client rejects a null token)."""
    monkeypatch.setenv('MOCK_DISCORD', 'true')
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    return importlib.import_module('pages.auth')


# --- redirect_uri builder (Design A) ------------------------------------------

def test_redirect_uri_https_for_real_domain(auth):
    tenant = SimpleNamespace(domain='foo.gg')
    assert auth._redirect_uri_for_tenant(tenant) == 'https://foo.gg/oauth/callback'


def test_redirect_uri_http_only_for_localhost_dev(auth):
    tenant = SimpleNamespace(domain='second.localhost:8000')
    assert auth._redirect_uri_for_tenant(tenant) == 'http://second.localhost:8000/oauth/callback'


def test_redirect_uri_forces_https_even_behind_http_base_url(auth, monkeypatch):
    # The original outage: deriving scheme from the request behind a TLS proxy
    # yields http:// and Discord rejects it. Building from the stored domain with
    # forced https avoids that regardless of BASE_URL's scheme.
    monkeypatch.setenv('BASE_URL', 'http://main.gg')
    tenant = SimpleNamespace(domain='foo.gg')
    assert auth._redirect_uri_for_tenant(tenant).startswith('https://')


def test_redirect_uri_platform_when_no_tenant(auth, monkeypatch):
    # PLATFORM_HOST unset -> platform host derives from BASE_URL's netloc, so the
    # common single-host deployment builds the callback on that host as before.
    monkeypatch.setenv('BASE_URL', 'https://main.gg')
    monkeypatch.delenv('PLATFORM_HOST', raising=False)
    monkeypatch.delenv('REDIRECT_URL', raising=False)
    assert auth._redirect_uri_for_tenant(None) == 'https://main.gg/oauth/callback'


def test_redirect_uri_platform_uses_platform_host_not_base_url(auth, monkeypatch):
    # Regression: PLATFORM_HOST set independently of BASE_URL (e.g. a legacy
    # single-tenant domain still lingering in BASE_URL). The platform callback
    # must land on the host that actually serves it — the platform host — not on
    # BASE_URL's stale host, or Discord round-trips a platform login to the wrong
    # host.
    monkeypatch.setenv('BASE_URL', 'https://onsite.legacy.example')
    monkeypatch.setenv('PLATFORM_HOST', 'platform.example')
    monkeypatch.delenv('REDIRECT_URL', raising=False)
    assert auth._redirect_uri_for_tenant(None) == 'https://platform.example/oauth/callback'


def test_redirect_uri_platform_redirect_url_override_wins(auth, monkeypatch):
    # REDIRECT_URL stays an explicit escape hatch, ahead of the platform host.
    monkeypatch.setenv('PLATFORM_HOST', 'platform.example')
    monkeypatch.setenv('REDIRECT_URL', 'https://custom.example/oauth/callback')
    assert auth._redirect_uri_for_tenant(None) == 'https://custom.example/oauth/callback'


def test_redirect_uri_platform_http_only_for_localhost_dev(auth, monkeypatch):
    # A *.localhost / localhost dev platform host keeps http (no TLS locally).
    monkeypatch.setenv('PLATFORM_HOST', 'localhost:8000')
    monkeypatch.delenv('REDIRECT_URL', raising=False)
    assert auth._redirect_uri_for_tenant(None) == 'http://localhost:8000/oauth/callback'


def test_both_legs_match_by_construction(auth):
    # /login builds from the resolved tenant; the callback rebuilds from the same
    # tenant — same stored domain, so the two strings are identical.
    tenant = SimpleNamespace(domain='foo.gg')
    login_leg = auth._redirect_uri_for_tenant(tenant)
    callback_leg = auth._redirect_uri_for_tenant(tenant)
    assert login_leg == callback_leg == 'https://foo.gg/oauth/callback'


# --- Tenant.domain normalization contract -------------------------------------

async def test_validate_domain_normalizes(db, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    from application.services.tenant_service import TenantService
    assert await TenantService._validate_domain('https://Foo.GG/x') == 'foo.gg'
    assert await TenantService._validate_domain('foo.gg:443') == 'foo.gg'
    assert await TenantService._validate_domain('bar.localhost:8000') == 'bar.localhost:8000'
    assert await TenantService._validate_domain('  ') is None


async def test_validate_domain_rejects_platform_host(db, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    from application.services.tenant_service import TenantService
    with pytest.raises(ValueError):
        await TenantService._validate_domain('main.gg')


async def test_validate_domain_rejects_malformed(db, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    from application.services.tenant_service import TenantService
    with pytest.raises(ValueError):
        await TenantService._validate_domain('has space.gg')


# --- secondary-provider detour off a custom domain ----------------------------

async def test_platform_link_redirect_in_host_mode(db, monkeypatch):
    monkeypatch.setenv('BASE_URL', 'https://main.gg')
    from pages._oauth_link import platform_link_redirect
    tenant_token = set_tenant_id(1)   # the db fixture's default tenant (slug 'default')
    host_token = set_host_mode(True)
    try:
        url = await platform_link_redirect('/home/profile')
    finally:
        reset_host_mode(host_token)
        reset_tenant_id(tenant_token)
    assert url == 'https://main.gg/t/default/home/profile'


async def test_platform_link_redirect_none_in_path_mode(db):
    from pages._oauth_link import platform_link_redirect
    # No host mode -> the flow runs in place, so no detour.
    assert await platform_link_redirect('/home/profile') is None
