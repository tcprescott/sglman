"""The OAuth 2.1 authorization-server flow.

Drives register → authorize → approve → token → refresh → revoke against the
real routes and provider, with the consent screen's browser step replaced by a
direct service call (the page itself is NiceGUI and covered by the UI loop).

The security-relevant assertions here are the ones about *reuse*: a code that
works twice, a refresh token that survives rotation, or an MCP token accepted by
the REST API each turn a single leak into standing access.
"""

import base64
import hashlib
import secrets

from application.services import McpAuthService
from application.services.api_token_service import MCP_TOKEN_PREFIX
from models import User
from tests.api_helpers import build_api_app, client_for
from tests.mcp.conftest import auth, mcp_session, rpc


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return verifier, challenge


async def register(client, redirect_uri='http://localhost:9999/callback') -> str:
    resp = await client.post('/register', json={
        'client_name': 'Test Client',
        'redirect_uris': [redirect_uri],
        'grant_types': ['authorization_code', 'refresh_token'],
        'response_types': ['code'],
        'token_endpoint_auth_method': 'none',
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()['client_id']


async def authorize_and_approve(client, client_id, challenge, user, redirect_uri, state='xyz'):
    """Run /authorize, then approve as the signed-in user would."""
    resp = await client.get('/authorize', params={
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'state': state,
    })
    assert resp.status_code in (302, 307), resp.text
    location = resp.headers['location']
    assert '/oauth/mcp/consent' in location, location
    txn = location.split('txn=')[1].split('&')[0]
    code, _, returned_state = await McpAuthService().approve(txn, user)
    assert returned_state == state
    return code


async def exchange(client, client_id, code, verifier, redirect_uri):
    return await client.post('/token', data={
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'code': code,
        'code_verifier': verifier,
        'redirect_uri': redirect_uri,
    })


class TestDiscoveryMetadata:
    async def test_authorization_server_metadata(self, db):
        async with mcp_session() as client:
            resp = await client.get('/.well-known/oauth-authorization-server')
        assert resp.status_code == 200
        body = resp.json()
        # A client that cannot find these three cannot complete the flow.
        for key in ('issuer', 'authorization_endpoint', 'token_endpoint',
                    'registration_endpoint'):
            assert body.get(key), key
        assert 'S256' in body['code_challenge_methods_supported']


class TestFullFlow:
    async def test_register_authorize_exchange_and_call(self, db):
        """The whole grant, ending in a real authenticated tool call."""
        user = await User.create(discord_id=555001, username='oauth-user')
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            resp = await exchange(client, client_id, code, verifier, redirect_uri)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body['token_type'].lower() == 'bearer'
            assert body['access_token'].startswith(MCP_TOKEN_PREFIX)
            assert body['refresh_token']
            assert body['expires_in'] > 0

            # The issued token must actually work against the endpoint it was
            # minted for — the flow succeeding is not the same as it being useful.
            call = await rpc(client, body['access_token'], 'tools/list')
            assert call.status_code == 200

    async def test_authorization_code_is_single_use(self, db):
        user = await User.create(discord_id=555002, username='oauth-replay')
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            first = await exchange(client, client_id, code, verifier, redirect_uri)
            assert first.status_code == 200
            replay = await exchange(client, client_id, code, verifier, redirect_uri)
        assert replay.status_code == 400
        assert replay.json()['error'] == 'invalid_grant'

    async def test_wrong_pkce_verifier_is_rejected(self, db):
        """Without this, a stolen code alone would be enough."""
        user = await User.create(discord_id=555003, username='oauth-pkce')
        redirect_uri = 'http://localhost:9999/callback'
        _, challenge = pkce()
        other_verifier, _ = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            resp = await exchange(client, client_id, code, other_verifier, redirect_uri)
        assert resp.status_code == 400
        assert resp.json()['error'] == 'invalid_grant'

    async def test_refresh_rotates_both_halves(self, db):
        """A refresh must invalidate the refresh token it consumed.

        Otherwise a leaked refresh token grants indefinite parallel access that
        nothing ever surfaces.
        """
        user = await User.create(discord_id=555004, username='oauth-refresh')
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            first = (await exchange(client, client_id, code, verifier, redirect_uri)).json()

            refreshed = await client.post('/token', data={
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'refresh_token': first['refresh_token'],
            })
            assert refreshed.status_code == 200, refreshed.text
            second = refreshed.json()
            assert second['access_token'] != first['access_token']
            assert second['refresh_token'] != first['refresh_token']

            # The old refresh token is dead...
            replay = await client.post('/token', data={
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'refresh_token': first['refresh_token'],
            })
            assert replay.status_code == 400

            # ...and the old access token with it, since rotation re-keys the row.
            stale = await rpc(client, first['access_token'], 'tools/list')
            assert stale.status_code == 401
            fresh = await rpc(client, second['access_token'], 'tools/list')
            assert fresh.status_code == 200

    async def test_revocation_stops_access(self, db):
        user = await User.create(discord_id=555005, username='oauth-revoke')
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            tokens = (await exchange(client, client_id, code, verifier, redirect_uri)).json()
            assert (await rpc(client, tokens['access_token'], 'tools/list')).status_code == 200

            # client_secret must be *present* even for a public client: the
            # SDK's RevocationRequest types it `str | None` with no default, so
            # pydantic requires the key. Empty is what a public client sends.
            revoke = await client.post('/revoke', data={
                'client_id': client_id,
                'client_secret': '',
                'token': tokens['access_token'],
            })
            assert revoke.status_code == 200, revoke.text
            after = await rpc(client, tokens['access_token'], 'tools/list')
        assert after.status_code == 401

    async def test_unknown_redirect_uri_is_refused(self, db):
        """An attacker-chosen redirect must never reach a consent screen."""
        async with mcp_session() as client:
            client_id = await register(client, 'http://localhost:9999/callback')
            _, challenge = pkce()
            resp = await client.get('/authorize', params={
                'client_id': client_id,
                'redirect_uri': 'http://evil.example.com/steal',
                'response_type': 'code',
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            })
        assert resp.status_code == 400
        assert 'evil.example.com' not in resp.headers.get('location', '')


class TestSurfaceSeparation:
    async def test_oauth_token_is_refused_by_the_rest_api(self, db):
        """A credential minted for /mcp must not be replayable against /api."""
        user = await User.create(discord_id=555006, username='oauth-rest')
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            tokens = (await exchange(client, client_id, code, verifier, redirect_uri)).json()

        api_app = build_api_app()
        async with client_for(api_app, tokens['access_token']) as api:
            resp = await api.get('/api/tournaments')
        assert resp.status_code == 401


class TestConsentPage:
    async def test_expired_transaction_cannot_be_approved(self, db):
        """A consent link that outlived its request must mint nothing."""
        user = await User.create(discord_id=555007, username='oauth-expired')
        service = McpAuthService()
        try:
            await service.approve('not-a-real-transaction', user)
        except Exception as exc:
            assert 'expired' in str(exc).lower()
        else:
            raise AssertionError('approve() accepted an unknown transaction')

    async def test_approval_is_single_use(self, db):
        """Re-submitting the consent form must not mint a second code."""
        user = await User.create(discord_id=555008, username='oauth-double')
        redirect_uri = 'http://localhost:9999/callback'
        _, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            resp = await client.get('/authorize', params={
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            })
            txn = resp.headers['location'].split('txn=')[1].split('&')[0]
            service = McpAuthService()
            await service.approve(txn, user)
            try:
                await service.approve(txn, user)
            except Exception as exc:
                assert 'expired' in str(exc).lower()
            else:
                raise AssertionError('approve() ran twice for one request')


class TestRoleIndependence:
    async def test_grant_does_not_confer_roles(self, db):
        """Connecting a client must not widen what the user can see.

        The token acts as the user; a user with no roles gets a working
        connection and an empty world, not an error and not extra reach.
        """
        user = await User.create(discord_id=555009, username='oauth-noroles')
        assert not await user.roles.all()
        redirect_uri = 'http://localhost:9999/callback'
        verifier, challenge = pkce()
        async with mcp_session() as client:
            client_id = await register(client, redirect_uri)
            code = await authorize_and_approve(
                client, client_id, challenge, user, redirect_uri
            )
            tokens = (await exchange(client, client_id, code, verifier, redirect_uri)).json()
            resp = await client.post(
                '/mcp', headers=auth(tokens['access_token']),
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                      'params': {'name': 'list_tenants', 'arguments': {}}},
            )
        assert resp.status_code == 200
        result = resp.json()['result']
        assert not result.get('isError'), result
        assert result['structuredContent']['result'] == []
