import pytest


@pytest.fixture(autouse=True)
def stub_discord_queue(monkeypatch):
    """Capture coroutines handed to discord_queue.enqueue without running them.

    Discord notifications/DMs are fire-and-forget via the queue worker, so
    services only enqueue the coroutine — they never await it. Capturing and
    closing the coroutines lets tests assert the call happened while avoiding
    'coroutine was never awaited' warnings.
    """
    captured = []
    monkeypatch.setattr(
        'application.services.discord_queue.enqueue', captured.append
    )
    yield captured
    for coro in captured:
        coro.close()
