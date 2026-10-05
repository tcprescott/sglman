"""The shared Challonge OAuth callback completes inside the originating tenant.

``/challonge/oauth/callback`` is served on the bare platform host, so the request
carries no tenant. Every ``ChallongeService`` entry point is
``@requires_feature(CHALLONGE)`` and the connection row is tenant-scoped, so the
callback must re-enter the community the flow started in — otherwise the real
(non-mock) flow always ends in "feature is not enabled for this community".
"""

import pytest
from nicegui import app

import pages.challonge_oauth as ch
from application.tenant_context import get_current_tenant_id, tenant_scope


class _FakeStorage(dict):
    pass


class _FakeClient:
    async def connected(self) -> None:
        return None


@pytest.fixture
def storage(monkeypatch):
    store = _FakeStorage()
    monkeypatch.setattr(type(app.storage), 'user', property(lambda self: store))
    return store


@pytest.fixture
def callback(monkeypatch, storage):
    pages = {}

    def fake_page(path, *args, **kwargs):
        def register(fn):
            pages[path] = fn
            return fn
        return register

    monkeypatch.setattr(ch.ui, 'page', fake_page)
    monkeypatch.setattr(ch, 'register_link_handoff_provider', lambda provider: None)

    async def no_handoff(url):
        return False

    async def a_user(discord_id):
        return object()

    monkeypatch.setattr(ch, 'handle_link_handoff_callback', no_handoff)
    monkeypatch.setattr(ch, 'get_user_from_discord_id', a_user)
    ch.create()

    async def run(url: str) -> None:
        async def js(_):
            return url
        monkeypatch.setattr(ch.ui, 'run_javascript', js)
        # The bare platform host: the tenant middleware sets no tenant.
        with tenant_scope(None):
            await pages['/challonge/oauth/callback'](_FakeClient())
            assert get_current_tenant_id() is None

    return run


@pytest.fixture
def seen(monkeypatch):
    calls = []

    async def finish_service(user, code, return_path):
        calls.append(('service', code, get_current_tenant_id()))

    async def finish_player(user, code, return_path):
        calls.append(('player', code, get_current_tenant_id()))

    monkeypatch.setattr(ch, '_finish_service_connect', finish_service)
    monkeypatch.setattr(ch, '_finish_player_link', finish_player)
    return calls


async def test_service_connect_finishes_in_the_initiating_tenant(callback, storage, seen):
    storage.update({
        'challonge_service_state': 'st',
        'challonge_service_return': '/t/demo/admin/challonge',
        'challonge_service_tenant': 7,
    })
    await callback('https://wizzrobe.test/challonge/oauth/callback?code=abc&state=st')
    assert seen == [('service', 'abc', 7)]
    assert 'challonge_service_tenant' not in storage


async def test_player_link_finishes_in_the_initiating_tenant(callback, storage, seen):
    storage.update({
        'challonge_player_state': 'ps',
        'challonge_player_return': '/t/demo/home/profile',
        'challonge_player_tenant': 3,
    })
    await callback('https://wizzrobe.test/challonge/oauth/callback?code=xyz&state=ps')
    assert seen == [('player', 'xyz', 3)]
    assert 'challonge_player_tenant' not in storage


async def test_a_failed_service_redirect_still_reports_in_its_tenant(callback, storage, seen):
    storage.update({'challonge_service_state': 'st', 'challonge_service_tenant': 7})
    await callback('https://wizzrobe.test/challonge/oauth/callback?error=access_denied')
    assert seen == [('service', None, 7)]
