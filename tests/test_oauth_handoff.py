"""Design B — cross-host login handoff: token mint/claim security tests.

Exercises the single-use, TTL-bounded, host-bound signed token that hands a
platform-host Discord login to a custom domain, plus the auth-layer helpers that
build the handoff URLs and sanitize the return path (open-redirect guard).
"""

import importlib

import pytest

from application.services import oauth_handoff_service as h


@pytest.fixture(autouse=True)
def _secret_and_reset(monkeypatch):
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    h.reset()
    yield
    h.reset()


def _mint(host='foo.gg', next_path='/admin'):
    return h.mint(
        discord_id=123, username='bob', avatar='http://a/av.png',
        target_host=host, next_path=next_path,
    )


def test_mint_then_claim_roundtrips():
    token = _mint()
    payload = h.claim(token, 'foo.gg')
    assert payload is not None
    assert payload['discord_id'] == 123
    assert payload['username'] == 'bob'
    assert payload['next'] == '/admin'


def test_claim_is_single_use():
    token = _mint()
    assert h.claim(token, 'foo.gg') is not None
    # Second presentation of the same token finds no nonce -> rejected.
    assert h.claim(token, 'foo.gg') is None


def test_claim_rejects_wrong_host():
    token = _mint(host='foo.gg')
    # A token minted for foo.gg is useless on bar.gg (host binding), and the
    # attempt still consumes the nonce so it can't be retried on the right host.
    assert h.claim(token, 'bar.gg') is None
    assert h.claim(token, 'foo.gg') is None


def test_claim_rejects_tampered_token():
    token = _mint()
    assert h.claim(token + 'x', 'foo.gg') is None


def test_claim_rejects_expired_via_store(monkeypatch):
    token = _mint()
    # Advance the service's clock past the TTL so the store-expiry check trips
    # (belt-and-braces alongside the signer's own max_age).
    real = h.time.time()
    monkeypatch.setattr(h.time, 'time', lambda: real + h._TTL_SECONDS + 5)
    assert h.claim(token, 'foo.gg') is None


def test_mint_rejects_unnormalizable_host():
    assert h.mint(discord_id=1, username='x', avatar=None,
                  target_host='not a host', next_path='/') is None


def test_host_normalization_is_consistent():
    # Minted with a port/scheme form, claimed with the browser's bare host.
    token = h.mint(discord_id=5, username='y', avatar=None,
                   target_host='https://Foo.GG/', next_path='/')
    assert h.claim(token, 'foo.gg') is not None


# --- auth-layer helpers (imported under MOCK_DISCORD; its live client rejects null token)

@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv('MOCK_DISCORD', 'true')
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    return importlib.import_module('pages.auth')


@pytest.mark.parametrize('raw,expected', [
    ('/admin', '/admin'),
    ('/home/profile?tab=1', '/home/profile?tab=1'),
    ('//evil.com', '/'),            # protocol-relative open-redirect
    ('https://evil.com', '/'),      # absolute URL
    ('/login', '/'),                # auth route would loop
    ('', '/'),
    (None, '/'),
])
def test_safe_next(auth, raw, expected):
    assert auth._safe_next(raw) == expected


def test_handoff_start_url(auth, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    url = auth._handoff_start_url('foo.gg', '/admin')
    assert url == 'https://main.gg/oauth/start?host=foo.gg&next=%2Fadmin'


def test_claim_url(auth):
    assert auth._claim_url('foo.gg', 'tok en') == 'https://foo.gg/session/claim?token=tok%20en'


def test_handoff_url_uses_http_for_localhost_dev(auth, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'localhost:8000')
    assert auth._handoff_start_url('second.localhost:8000', '/').startswith('http://localhost:8000/')
    assert auth._claim_url('second.localhost:8000', 't').startswith('http://second.localhost:8000/')
