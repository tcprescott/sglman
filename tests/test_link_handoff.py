"""Cross-host secondary-provider link handoff (racetime / Twitch / Challonge).

The custom-domain counterpart of the Discord-login handoff: the provider OAuth
runs on the platform host, then the verified **public** provider identity is
handed back to the custom domain (where the user's session and tenant live)
through the same single-use, host-bound, browser-bound token. These tests cover
the generic payload token, the handoff-URL builders, and the provider registry;
the security invariants of the token itself live in ``test_oauth_handoff.py``.
"""

import hashlib
import importlib

import pytest

from application.services import oauth_handoff_service as h
from application.utils.tenant_urls import safe_next


@pytest.fixture(autouse=True)
def _secret_and_reset(monkeypatch):
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    h.reset()
    yield
    h.reset()


# --- generic payload token (mint_data) ----------------------------------------

def test_mint_data_roundtrips_arbitrary_payload():
    token = h.mint_data(
        data={'key': 'racetime', 'user_id': 'rt-1', 'name': 'Speedy'},
        target_host='foo.gg', next_path='/home/profile', bind_commit='c' * 64,
    )
    payload = h.claim(token, 'foo.gg')
    assert payload is not None
    assert payload['data'] == {'key': 'racetime', 'user_id': 'rt-1', 'name': 'Speedy'}
    assert payload['next'] == '/home/profile'
    assert payload['bind_commit'] == 'c' * 64


def test_mint_data_is_single_use():
    token = h.mint_data(data={'key': 'twitch'}, target_host='foo.gg', next_path='/')
    assert h.claim(token, 'foo.gg') is not None
    assert h.claim(token, 'foo.gg') is None


def test_mint_data_is_host_bound():
    token = h.mint_data(data={'key': 'twitch'}, target_host='foo.gg', next_path='/')
    # A token minted for foo.gg is useless on bar.gg, and the attempt still
    # consumes the nonce so it can't be retried on the right host.
    assert h.claim(token, 'bar.gg') is None
    assert h.claim(token, 'foo.gg') is None


def test_mint_data_rejects_unnormalizable_host():
    assert h.mint_data(data={'key': 'x'}, target_host='not a host', next_path='/') is None


def test_login_mint_keeps_flat_identity_shape():
    # The Discord-login mint is unchanged: its identity stays top-level (no 'data'
    # wrapper), so the login callback keeps reading payload['discord_id'].
    token = h.mint(discord_id=1, username='u', avatar=None, target_host='foo.gg', next_path='/')
    payload = h.claim(token, 'foo.gg')
    assert payload['discord_id'] == 1
    assert 'data' not in payload


# --- auth-layer helpers -------------------------------------------------------

@pytest.fixture
def link(monkeypatch):
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    return importlib.import_module('pages._oauth_link')


def test_link_handoff_start_url(link, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    url = link._link_handoff_start_url('racetime', 'foo.gg', '/home/profile', 'abc')
    assert url == 'https://main.gg/oauth/link/start?p=racetime&host=foo.gg&next=%2Fhome%2Fprofile&b=abc'


def test_link_claim_url(link):
    assert link._link_claim_url('foo.gg', 'tok en') == 'https://foo.gg/oauth/link/claim?token=tok%20en'


def test_link_handoff_urls_use_http_for_localhost_dev(link, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'localhost:8000')
    assert link._link_handoff_start_url('twitch', 's.localhost:8000', '/', 'b').startswith('http://localhost:8000/')
    assert link._link_claim_url('s.localhost:8000', 't').startswith('http://s.localhost:8000/')


def test_bind_commit_is_deterministic_sha256(link):
    assert link._bind_commit('secret') == hashlib.sha256(b'secret').hexdigest()
    assert link._bind_commit('other') != link._bind_commit('secret')


# --- provider registry --------------------------------------------------------

def test_identity_flows_carry_provider_key():
    import pages.racetime_oauth as rt
    import pages.twitch_oauth as tw
    assert rt._FLOW.provider_key == 'racetime'
    assert tw._FLOW.provider_key == 'twitch'


def test_register_link_handoff_provider(link):
    provider = link.LinkHandoffProvider(
        key='demo', label='Demo', profile_return='/home/profile',
        authorize_url=lambda s: f'https://x/y?state={s}',
        exchange=None, record=None,
        is_mock=lambda: False, callback_route='/demo/oauth/callback',
    )
    link.register_link_handoff_provider(provider)
    assert link._HANDOFF_PROVIDERS['demo'] is provider


def test_link_handoff_provider_requires_its_mock_exit(link):
    # The start leg needs both fields to reach a mocked provider's own callback;
    # a provider registered without them would dead-end at an authorize URL that
    # cannot answer under MOCK_*. No defaults, so a fourth provider cannot omit
    # them silently.
    import dataclasses
    required = {
        f.name for f in dataclasses.fields(link.LinkHandoffProvider)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    assert {'is_mock', 'callback_route'} <= required


# --- the mock exit on the start leg (dev-drivable handoff) --------------------

def test_mock_callback_url_targets_the_providers_own_callback(link, monkeypatch):
    monkeypatch.setenv('PLATFORM_HOST', 'main.gg')
    provider = link.LinkHandoffProvider(
        key='demo', label='Demo', profile_return='/home/profile',
        authorize_url=lambda s: 'https://provider.example/authorize',
        exchange=None, record=None,
        is_mock=lambda: True, callback_route='/demo/oauth/callback',
    )
    assert link._mock_callback_url(provider, 'st8') == (
        'https://main.gg/demo/oauth/callback?code=mock&state=st8'
    )


def test_link_start_never_self_redirects_in_production(monkeypatch):
    # The branch is reachable only through a provider's is_mock(), and every one
    # of those raises rather than returning True under ENVIRONMENT=production —
    # so the mock exit cannot be taken there. Assert it instead of trusting it.
    from application.utils.mocks.mock_challonge import is_mock_challonge
    from application.utils.mocks.mock_racetime import is_mock_racetime
    from application.utils.mocks.mock_twitch import is_mock_twitch
    monkeypatch.setenv('ENVIRONMENT', 'production')
    for is_mock in (is_mock_challonge, is_mock_racetime, is_mock_twitch):
        monkeypatch.setenv(f'MOCK_{is_mock.__name__.removeprefix("is_mock_").upper()}', 'true')
        with pytest.raises(RuntimeError):
            is_mock()


async def test_maybe_start_link_handoff_is_none_in_path_mode(link, monkeypatch):
    # The reorder in each /<provider>/link page puts this call ahead of the mock
    # short-circuit, so "returns None in path mode" is what keeps path-mode dev
    # and every handoff-off deployment on exactly the path they were on before.
    monkeypatch.setenv('HOST_OAUTH_MODE', 'handoff')
    monkeypatch.setattr(link, 'is_host_mode', lambda: False)
    assert await link.maybe_start_link_handoff('racetime', '/home/profile') is None


async def test_maybe_start_link_handoff_is_none_with_handoff_off(link, monkeypatch):
    monkeypatch.delenv('HOST_OAUTH_MODE', raising=False)
    monkeypatch.setattr(link, 'is_host_mode', lambda: True)
    assert await link.maybe_start_link_handoff('racetime', '/home/profile') is None


def test_link_page_prefers_handoff_over_mock(link):
    # Source-level, because the ordering *is* the fix: maybe_start_link_handoff
    # has to be reached before the is_mock() short-circuit returns, or the whole
    # handoff stays unreachable in the one environment that can drive it.
    import inspect

    import pages.challonge_oauth as ch
    for module, mock_call in ((link, 'flow.is_mock()'), (ch, 'is_mock_challonge()')):
        src = inspect.getsource(module)
        handoff = src.index('maybe_start_link_handoff(')
        # The *link page's* mock branch, i.e. the last occurrence — challonge's
        # /connect page has its own earlier one that is not part of this flow.
        assert src.rindex(mock_call) > handoff, module.__name__


# --- browser-binding guard (link-CSRF / forced-link) --------------------------

def test_bind_matches_accepts_the_committing_browser(link):
    secret = 'a-browser-secret'
    assert link._bind_matches(link._bind_commit(secret), secret) is True


def test_bind_matches_rejects_a_different_browser(link):
    # A token minted for one browser (committed to secret A) claimed by another
    # browser (holding secret B) is rejected.
    assert link._bind_matches(link._bind_commit('secret-A'), 'secret-B') is False


@pytest.mark.parametrize('expected_commit,browser_secret', [
    (None, 'anything'),         # token carried no commitment
    ('', 'anything'),           # blank commitment
    ('deadbeef' * 8, None),     # browser presents no secret
    ('deadbeef' * 8, 123),      # non-string secret
])
def test_bind_matches_fails_closed(link, expected_commit, browser_secret):
    assert link._bind_matches(expected_commit, browser_secret) is False


# --- shared open-redirect guard -----------------------------------------------

@pytest.mark.parametrize('raw,expected', [
    ('/home/profile', '/home/profile'),
    ('/home/profile?tab=1', '/home/profile?tab=1'),
    ('//evil.com', '/'),
    ('/\\evil.com', '/'),
    ('/a\r\nSet-Cookie: x', '/'),
    ('/a b', '/'),
    ('https://evil.com', '/'),
    ('/login', '/'),
    ('', '/'),
    (None, '/'),
])
def test_safe_next_guards_cross_host_return(raw, expected):
    assert safe_next(raw) == expected
