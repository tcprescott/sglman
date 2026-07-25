"""Tests for the unauthenticated /api/health probe."""

from tests.api_helpers import build_api_app, client_for


async def test_health_ok_without_auth(db):
    app = build_api_app()
    async with client_for(app) as client:
        resp = await client.get('/api/health')
    assert resp.status_code == 200
    assert resp.json() == {'status': 'ok'}
