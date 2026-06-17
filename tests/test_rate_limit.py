"""Unit tests for the in-process REST API rate limiter."""

import pytest
from fastapi import HTTPException

from api.rate_limit import _hits, rate_limit


class _FakeRequest:
    def __init__(self, headers=None, host='10.0.0.1'):
        self.headers = headers or {}
        self.client = type('Client', (), {'host': host})()


async def test_requests_under_limit_pass(monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_MIN', '3')
    _hits.clear()
    req = _FakeRequest(host='10.0.0.10')
    for _ in range(3):
        await rate_limit(req)  # must not raise


async def test_request_over_limit_429(monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_MIN', '3')
    _hits.clear()
    req = _FakeRequest(host='10.0.0.11')
    for _ in range(3):
        await rate_limit(req)
    with pytest.raises(HTTPException) as exc:
        await rate_limit(req)
    assert exc.value.status_code == 429
    assert 'Retry-After' in exc.value.headers


async def test_distinct_keys_isolated(monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_MIN', '2')
    _hits.clear()
    # Different tokens are limited independently.
    a = _FakeRequest(headers={'authorization': 'Bearer aaa'})
    b = _FakeRequest(headers={'authorization': 'Bearer bbb'})
    for _ in range(2):
        await rate_limit(a)
    # 'a' is now at its limit, but 'b' is untouched.
    await rate_limit(b)
    with pytest.raises(HTTPException):
        await rate_limit(a)
