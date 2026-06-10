"""Tests for personal API tokens: the service, auth dependency, and the
self-management endpoints.

Uses the function-scoped in-memory ``db`` fixture from conftest.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import api
from application.services.api_token_service import ApiTokenService, _hash_token
from models import ApiToken, User


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(api.router, prefix='/api')
    return test_app


async def _user(discord_id: int = 1, username: str = 'u', is_active: bool = True) -> User:
    return await User.create(discord_id=discord_id, username=username, is_active=is_active)


def _client(app, raw_token: str | None = None) -> AsyncClient:
    headers = {'Authorization': f'Bearer {raw_token}'} if raw_token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://test', headers=headers)


# ---------------------------------------------------------------------------
# Service: creation, hashing, authentication
# ---------------------------------------------------------------------------


class TestApiTokenService:
    async def test_create_returns_plaintext_and_stores_only_hash(self, db):
        user = await _user()
        token, raw = await ApiTokenService().create_token(user, name='cli')
        assert raw.startswith('sglman_pat_')
        # Only the hash is persisted; the plaintext never is.
        stored = await ApiToken.get(id=token.id)
        assert stored.token_hash == _hash_token(raw)
        assert raw not in stored.token_hash
        assert stored.token_prefix == raw[:17]

    async def test_authenticate_resolves_user_and_bumps_last_used(self, db):
        user = await _user()
        _, raw = await ApiTokenService().create_token(user, name='cli')
        result = await ApiTokenService().authenticate(raw)
        assert result is not None
        resolved_user, token = result
        assert resolved_user.id == user.id
        assert token.last_used_at is not None

    async def test_authenticate_rejects_unknown_token(self, db):
        assert await ApiTokenService().authenticate('sglman_pat_nope') is None

    async def test_authenticate_rejects_revoked_token(self, db):
        user = await _user()
        token, raw = await ApiTokenService().create_token(user, name='cli')
        await ApiTokenService().revoke_token(user, token.id)
        assert await ApiTokenService().authenticate(raw) is None

    async def test_authenticate_rejects_expired_token(self, db):
        user = await _user()
        past = datetime.now(timezone.utc) - timedelta(days=1)
        # Create directly with a past expiry (service forbids past expiry on create).
        raw = 'sglman_pat_expired'
        await ApiToken.create(
            user=user, name='old', token_hash=_hash_token(raw),
            token_prefix=raw[:17], expires_at=past,
        )
        assert await ApiTokenService().authenticate(raw) is None

    async def test_revoke_requires_ownership(self, db):
        owner = await _user(discord_id=1, username='owner')
        other = await _user(discord_id=2, username='other')
        token, _ = await ApiTokenService().create_token(owner, name='cli')
        with pytest.raises(PermissionError):
            await ApiTokenService().revoke_token(other, token.id)

    async def test_create_rejects_past_expiry(self, db):
        user = await _user()
        with pytest.raises(ValueError):
            await ApiTokenService().create_token(
                user, name='x', expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )


# ---------------------------------------------------------------------------
# Endpoints + auth dependency
# ---------------------------------------------------------------------------


class TestTokenEndpoints:
    async def test_list_and_create(self, db, app):
        user = await _user()
        _, raw = await ApiTokenService().create_token(user, name='bootstrap')
        async with _client(app, raw) as c:
            created = await c.post('/api/tokens', json={'name': 'second'})
            assert created.status_code == 201
            body = created.json()
            assert body['token'].startswith('sglman_pat_')
            assert body['name'] == 'second'

            listed = await c.get('/api/tokens')
            assert listed.status_code == 200
            names = {t['name'] for t in listed.json()}
            assert {'bootstrap', 'second'} <= names
            # The secret is never returned by the list endpoint.
            assert all('token' not in t for t in listed.json())

    async def test_revoke_endpoint(self, db, app):
        user = await _user()
        token, raw = await ApiTokenService().create_token(user, name='temp')
        async with _client(app, raw) as c:
            resp = await c.delete(f'/api/tokens/{token.id}')
            assert resp.status_code == 204
        # The token no longer authenticates.
        assert await ApiTokenService().authenticate(raw) is None

    async def test_missing_token_is_401(self, db, app):
        async with _client(app) as c:
            assert (await c.get('/api/tokens')).status_code == 401

    async def test_inactive_user_is_403(self, db, app):
        user = await _user(is_active=False)
        _, raw = await ApiTokenService().create_token(user, name='cli')
        async with _client(app, raw) as c:
            assert (await c.get('/api/tokens')).status_code == 403

    async def test_read_only_token_cannot_write(self, db, app):
        user = await _user()
        _, raw = await ApiTokenService().create_token(user, name='ro', read_only=True)
        async with _client(app, raw) as c:
            # Reads are allowed.
            assert (await c.get('/api/tokens')).status_code == 200
            # Writes (creating/revoking tokens) are rejected with 403.
            blocked = await c.post('/api/tokens', json={'name': 'escalate'})
            assert blocked.status_code == 403
