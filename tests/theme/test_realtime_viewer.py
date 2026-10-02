"""A match_live push is handled as the board's own viewer, not as its publisher.

The runner task inherits the publisher's contextvars, and app.storage.user reads
NiceGUI's request contextvar. Without rebinding it, a player's board refreshing
after staff approved a move read the staff member's identity, and stamped the
staff member's reschedule state onto the player's row.
"""

from types import SimpleNamespace

from nicegui.storage import request_contextvar

import theme.realtime as realtime


class _Client:
    def __init__(self, request):
        self.id = 'viewer-client'
        self.request = request

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _request(session_id):
    return SimpleNamespace(session={'id': session_id})


def _wire(monkeypatch, client):
    monkeypatch.setattr(realtime, 'context', SimpleNamespace(client=client))
    monkeypatch.setattr(realtime, '_install_disconnect_cleanup', lambda: None)
    pending, subscribed = [], []
    monkeypatch.setattr(realtime.background_tasks, 'create', pending.append)
    monkeypatch.setattr(realtime.match_live, 'subscribe',
                        lambda cb: subscribed.append(cb) or 1)
    return pending, subscribed


async def test_the_runner_reads_the_viewers_request(monkeypatch):
    viewer_request, publisher_request = _request('viewer'), _request('publisher')
    monkeypatch.setitem(realtime.app.storage._users, 'viewer', {})
    pending, subscribed = _wire(monkeypatch, _Client(viewer_request))
    seen = []

    async def on_change(match_id, change_type):
        seen.append(request_contextvar.get())

    realtime.register_view(on_change)
    token = request_contextvar.set(publisher_request)
    try:
        subscribed[0](7, 'changed')
        await pending[0]
        assert request_contextvar.get() is publisher_request
    finally:
        request_contextvar.reset(token)
    assert seen == [viewer_request]


async def test_a_client_without_a_live_session_is_skipped(monkeypatch):
    pending, subscribed = _wire(monkeypatch, _Client(_request('gone')))
    seen = []

    async def on_change(match_id, change_type):
        seen.append(match_id)

    realtime.register_view(on_change)
    subscribed[0](7, 'changed')
    await pending[0]
    assert seen == []
