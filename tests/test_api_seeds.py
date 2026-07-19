"""REST API tests for the seed-generation endpoints (api/routers/seeds.py).

Covers the randomizer catalogue read, the roll-a-seed write (mocked so no real
randomizer backend is contacted), auth gating, and cross-tenant preset scoping.
"""

import pytest

from application.services import SeedGenerationService
from application.tenant_context import tenant_scope
from models import Preset, Role, Tenant
from tests.api_helpers import client_for, create_user_token


@pytest.fixture(autouse=True)
def mock_seedgen(monkeypatch):
    monkeypatch.setenv('MOCK_SEEDGEN', '1')


# --- /randomizers ---------------------------------------------------------

async def test_list_randomizers(db, app):
    _, raw = await create_user_token(username='reader', read_only=True)
    async with client_for(app, raw) as c:
        resp = await c.get('/api/seeds/randomizers')
        assert resp.status_code == 200
        body = resp.json()
        assert {r['randomizer'] for r in body} == set(SeedGenerationService.AVAILABLE_RANDOMIZERS)
        by_name = {r['randomizer']: r['supports_triforce_texts'] for r in body}
        assert by_name['alttpr'] is True
        assert by_name['ff1r'] is False


async def test_randomizers_requires_auth(db, app):
    async with client_for(app) as c:
        resp = await c.get('/api/seeds/randomizers')
        assert resp.status_code == 401


async def test_flag_gated_randomizer_dropped_from_catalogue_when_off(db, app):
    # A fresh tenant starts with every flag off, so the flag-gated dk64r
    # randomizer is filtered out of the catalogue (mirrors the web selectors);
    # ungated randomizers stay.
    b = await Tenant.create(name='NoDK', slug='no-dk')
    with tenant_scope(b.id):
        _, token_b = await create_user_token(username='b-reader', roles=[Role.STAFF])
    async with client_for(app, token_b) as c:
        resp = await c.get('/api/seeds/randomizers')
        assert resp.status_code == 200
        names = {r['randomizer'] for r in resp.json()}
        assert 'dk64r' not in names
        assert 'alttpr' in names


# --- POST /seeds ----------------------------------------------------------

async def test_generate_seed_happy_path(db, app):
    _, raw = await create_user_token(username='roller')
    async with client_for(app, raw) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr'})
        assert resp.status_code == 200
        assert resp.json()['url'].startswith('https://mock.seedgen.local/alttpr/')


async def test_generate_seed_with_preset(db, app):
    _, raw = await create_user_token(username='roller')
    preset = await Preset.create(name='Custom', randomizer='alttpr', settings={'foo': 'bar'})
    async with client_for(app, raw) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr', 'preset_id': preset.id})
        assert resp.status_code == 200
        assert resp.json()['url'].startswith('https://mock.seedgen.local/alttpr/')


async def test_generate_seed_unknown_preset_404(db, app):
    _, raw = await create_user_token(username='roller')
    async with client_for(app, raw) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr', 'preset_id': 999999})
        assert resp.status_code == 404


async def test_generate_seed_unsupported_randomizer_400(db, app):
    _, raw = await create_user_token(username='roller')
    async with client_for(app, raw) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'nope'})
        assert resp.status_code == 400


async def test_generate_seed_flag_gated_randomizer_404_when_off(db, app):
    # dk64r is a valid randomizer but flag-gated; a tenant without the
    # DK64_RANDOMIZER flag gets a 404 (hidden), the REST mirror of the web gate.
    # The gate fires before generate_seed, so the MOCK_SEEDGEN fixture is moot.
    b = await Tenant.create(name='NoDK2', slug='no-dk2')
    with tenant_scope(b.id):
        _, token_b = await create_user_token(username='b-roller', roles=[Role.STAFF])
    async with client_for(app, token_b) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'dk64r'})
        assert resp.status_code == 404


async def test_generate_seed_requires_auth(db, app):
    async with client_for(app) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr'})
        assert resp.status_code == 401


async def test_generate_seed_rejects_read_only_token(db, app):
    _, raw = await create_user_token(username='ro', read_only=True)
    async with client_for(app, raw) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr'})
        assert resp.status_code == 403


# --- cross-tenant preset scoping -----------------------------------------

async def test_preset_is_tenant_scoped(db, app):
    a = await Tenant.get(id=1)
    b = await Tenant.create(name='Beta', slug='beta')
    with tenant_scope(a.id):
        preset_a = await Preset.create(name='A Preset', randomizer='alttpr', settings={})
    with tenant_scope(b.id):
        _, token_b = await create_user_token(username='b-roller', roles=[Role.STAFF])
    async with client_for(app, token_b) as c:
        resp = await c.post('/api/seeds', json={'randomizer': 'alttpr', 'preset_id': preset_a.id})
        assert resp.status_code == 404
