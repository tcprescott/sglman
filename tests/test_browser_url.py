"""Callback pages stop quietly when the browser never opens its socket.

Sentry SGLMAN-M/-N/-Q: ``Client.connected()`` also returns when NiceGUI deletes
a client whose socket never arrived (a crawler, an iOS link preview, Safari
parking the tab during the Discord hop). The callbacks then read ``None`` from
``window.location.href`` or timed out, and touched a user storage NiceGUI had
already pruned, so the page 500'd instead of ending.
"""

import importlib

import pytest
from nicegui import app, ui

import pages._browser_url as bu


class _Client:
    def __init__(self, *, deleted_on_connect: bool = False) -> None:
        self.is_deleted = False
        self._deleted_on_connect = deleted_on_connect

    async def connected(self) -> None:
        if self._deleted_on_connect:
            self.is_deleted = True


@pytest.fixture
def js(monkeypatch):
    calls = []

    def answer(result):
        async def run(code, *args, **kwargs):
            calls.append(code)
            if isinstance(result, BaseException):
                raise result
            return result
        monkeypatch.setattr(ui, 'run_javascript', run)

    answer.calls = calls
    return answer


@pytest.fixture
def pruned_storage(monkeypatch):
    """``app.storage.user`` as NiceGUI leaves it once the client is gone."""
    def gone(self):
        raise AssertionError('user storage should be created before accessing it')
    monkeypatch.setattr(type(app.storage), 'user', property(gone))


async def test_returns_url_when_connected(js):
    js('https://foo.gg/oauth/callback?code=x')
    assert await bu.browser_url(_Client()) == 'https://foo.gg/oauth/callback?code=x'


async def test_deleted_before_connect_skips_javascript(js):
    js('https://never')
    assert await bu.browser_url(_Client(deleted_on_connect=True)) is None
    assert js.calls == []


async def test_javascript_timeout_returns_none(js):
    js(TimeoutError('JavaScript did not respond within 1.0 s'))
    assert await bu.browser_url(_Client()) is None


async def test_javascript_none_returns_none(js):
    js(None)
    assert await bu.browser_url(_Client()) is None


def _capture_pages(monkeypatch, module):
    pages = {}

    def fake_page(path, *args, **kwargs):
        def register(fn):
            pages[path] = fn
            return fn
        return register

    monkeypatch.setattr(module.ui, 'page', fake_page)
    return pages


async def test_challonge_callback_stops_when_client_gone(monkeypatch, js, pruned_storage):
    import pages.challonge_oauth as ch

    pages = _capture_pages(monkeypatch, ch)
    monkeypatch.setattr(ch, 'register_link_handoff_provider', lambda provider: None)
    ch.create()
    js(TimeoutError('JavaScript did not respond within 1.0 s'))

    await pages['/challonge/oauth/callback'](_Client())


@pytest.mark.parametrize('path', [
    '/oauth/callback',
    '/session/claim',
    '/oauth/discord/connect/callback',
    'DISCORD_LOGIN_PATH',
])
async def test_discord_callbacks_stop_when_client_gone(monkeypatch, js, pruned_storage, path):
    monkeypatch.setenv('MOCK_DISCORD', 'true')
    monkeypatch.setenv('STORAGE_SECRET', 'x' * 40)
    auth = importlib.import_module('pages.auth')

    pages = _capture_pages(monkeypatch, auth)
    monkeypatch.setattr(auth, 'is_mock_discord', lambda: False)

    async def no_wait(*args, **kwargs):
        return None
    monkeypatch.setattr(auth, 'waiting_screen', no_wait)
    auth.create()
    js('https://never')

    path = auth.DISCORD_LOGIN_PATH if path == 'DISCORD_LOGIN_PATH' else path
    await pages[path](_Client(deleted_on_connect=True))
    assert js.calls == []


async def test_link_claim_stops_when_client_gone(monkeypatch, js, pruned_storage):
    import pages._oauth_link as ol

    pages = _capture_pages(monkeypatch, ol)
    monkeypatch.setattr(ol, 'host_oauth_handoff_enabled', lambda: True)
    ol.register_link_handoff_pages()
    js('https://never')

    await pages['/oauth/link/claim'](_Client(deleted_on_connect=True))
    assert js.calls == []
