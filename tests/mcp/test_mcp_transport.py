"""Transport-level behaviour of the /mcp endpoint.

These guard the mechanics the whole design rests on — statelessness, the
bare-path route, the OAuth-only rule, the Bearer challenge. Each of them fails
silently and expensively if it regresses: a stateful server would cross-wire
identities, a Mount would 307 every client into a wall, and a missing challenge
would leave clients unable to start the flow they need.
"""

from application.services.api_token_service import MCP_TOKEN_PREFIX
from models import Role
from tests.api_helpers import create_user_token
from tests.mcp.conftest import auth, call_tool, create_oauth_token, mcp_session, rpc


class TestAuthentication:
    async def test_no_token_is_401_with_challenge(self, db):
        async with mcp_session() as client:
            resp = await rpc(client, None, 'tools/list')
        assert resp.status_code == 401
        # The challenge is what turns a rejection into a recovery: a compliant
        # client reads it, finds the authorization server, and starts OAuth.
        assert 'resource_metadata=' in resp.headers['www-authenticate']

    async def test_garbage_token_is_401(self, db):
        async with mcp_session() as client:
            resp = await rpc(client, MCP_TOKEN_PREFIX + 'nope' * 8, 'tools/list')
        assert resp.status_code == 401
        assert 'resource_metadata=' in resp.headers['www-authenticate']

    async def test_personal_access_token_is_refused(self, db):
        """A REST PAT must not work here — and must be told where to go.

        401 rather than 403 on purpose: 403 would be accurate but leaves the
        client with nowhere to go, whereas 401 + challenge starts the flow.
        """
        _, pat = await create_user_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            resp = await rpc(client, pat, 'tools/list')
        assert resp.status_code == 401
        assert 'resource_metadata=' in resp.headers['www-authenticate']

    async def test_expired_oauth_token_is_401(self, db):
        _, raw = await create_oauth_token(expired=True)
        async with mcp_session() as client:
            resp = await rpc(client, raw, 'tools/list')
        assert resp.status_code == 401

    async def test_deactivated_user_is_403(self, db):
        _, raw = await create_oauth_token(is_active=False)
        async with mcp_session() as client:
            resp = await rpc(client, raw, 'tools/list')
        assert resp.status_code == 403

    async def test_valid_oauth_token_is_accepted(self, db):
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            resp = await rpc(client, raw, 'tools/list')
        assert resp.status_code == 200


class TestTransport:
    async def test_tools_list_works_without_initialize(self, db):
        """Proves the server is stateless.

        A stateful server rejects anything before `initialize`. Statelessness is
        what makes per-request actor binding safe (mcpserver/asgi.py), so this
        doubles as a regression guard on that setting.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            resp = await rpc(client, raw, 'tools/list')
        assert resp.status_code == 200
        names = {t['name'] for t in resp.json()['result']['tools']}
        assert 'whoami' in names

    async def test_initialize_reports_server_identity(self, db):
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            resp = await rpc(client, raw, 'initialize', {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '0'},
            })
        assert resp.status_code == 200
        result = resp.json()['result']
        assert result['serverInfo']['name'] == 'Wizzrobe'
        # The instructions are the server-level prompt; losing them would
        # silently degrade every conversation, with no error anywhere.
        assert 'whoami' in result['instructions']

    async def test_wrong_method_is_405(self, db):
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            resp = await client.put('/mcp', headers=auth(raw), json={})
        assert resp.status_code == 405

    async def test_missing_accept_header_is_406(self, db):
        _, raw = await create_oauth_token()
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {raw}'}
        async with mcp_session() as client:
            resp = await client.post(
                '/mcp', headers=headers,
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            )
        assert resp.status_code == 406

    async def test_trailing_slash_redirects_to_bare_path(self, db):
        """The endpoint is a Route, not a Mount.

        Under a Mount the redirect runs the other way — `/mcp` would 307 to
        `/mcp/` — and since clients do not follow redirects by default, every
        call would fail. Asserting the direction locks the routing choice in.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            resp = await client.post('/mcp/', headers=auth(raw), json={})
        assert resp.status_code == 307
        assert resp.headers['location'].endswith('/mcp')

    async def test_unusual_host_header_is_accepted(self, db):
        """Regression: DNS-rebinding protection would 421 every production call.

        It auto-enables when the configured host is loopback, which is the
        default — so this fails closed in exactly the environment that running
        locally cannot reveal.
        """
        _, raw = await create_oauth_token()
        headers = dict(auth(raw))
        headers['Host'] = 'wizzrobe.example.com'
        async with mcp_session() as client:
            resp = await client.post(
                '/mcp', headers=headers,
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            )
        assert resp.status_code == 200


class TestDiscovery:
    async def test_protected_resource_metadata(self, db):
        async with mcp_session() as client:
            for path in (
                '/.well-known/oauth-protected-resource/mcp',
                '/.well-known/oauth-protected-resource',
            ):
                resp = await client.get(path)
                assert resp.status_code == 200, path
                body = resp.json()
                assert body['resource'].endswith('/mcp')
                # Without this a client cannot find the authorization server.
                assert body['authorization_servers']
                assert body['bearer_methods_supported'] == ['header']

    async def test_metadata_needs_no_authentication(self, db):
        """Discovery must work *before* the client holds any credential."""
        async with mcp_session() as client:
            resp = await client.get('/.well-known/oauth-protected-resource')
        assert resp.status_code == 200


class TestRateLimit:
    async def test_over_limit_is_429_with_retry_after(self, db, monkeypatch):
        monkeypatch.setenv('API_RATE_LIMIT_PER_MIN', '3')
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            statuses = []
            for _ in range(5):
                resp = await rpc(client, raw, 'tools/list')
                statuses.append(resp.status_code)
            last = await rpc(client, raw, 'tools/list')
        assert 429 in statuses
        assert last.status_code == 429
        assert 'retry-after' in last.headers


class TestOrientationTools:
    async def test_whoami_reports_identity(self, db):
        user, raw = await create_oauth_token(username='alice', roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(client, raw, 'whoami')
        assert not is_error, payload
        assert payload['user_id'] == user.id
        assert payload['username'] == 'alice'
        assert [t['slug'] for t in payload['tenants']] == ['default']
        assert Role.STAFF.value in payload['tenants'][0]['roles']

    async def test_list_tenants_hides_communities_without_a_role(self, db):
        """A role-less user must not learn which communities exist."""
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            is_error, payload = await call_tool(client, raw, 'list_tenants')
        assert not is_error, payload
        assert payload['result'] == []
