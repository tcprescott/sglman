"""A plain member reaches their community over MCP, and only theirs.

Membership is the web app's bar for a community, but the MCP floor used to ask
for a role instead, so a player with no role saw an empty `list_tenants` and
"No community is available" for their own community.
"""

from models import MembershipSource, Tenant, TenantMembership
from tests.mcp.conftest import call_tool, create_oauth_token, mcp_session


async def test_member_without_role_sees_and_reads_their_community(db):
    user, raw = await create_oauth_token(username='plain-member')
    await TenantMembership.create(user=user, tenant_id=1, source=MembershipSource.STAFF)
    await Tenant.create(name='Elsewhere', slug='elsewhere')

    async with mcp_session() as client:
        error, tenants = await call_tool(client, raw, 'list_tenants')
        assert not error
        assert [t['slug'] for t in tenants['result']] == ['default']
        assert tenants['result'][0]['roles'] == []

        error, _ = await call_tool(client, raw, 'list_tournaments', tenant='default')
        assert not error

        error, text = await call_tool(client, raw, 'list_tournaments', tenant='elsewhere')
        assert error and 'No community' in text

        # Members only get member tools: staff gates still apply.
        error, text = await call_tool(client, raw, 'list_users', tenant='default')
        assert error and 'forbidden:' in text



async def test_get_user_returns_own_record(db):
    user, raw = await create_oauth_token(username='self-reader')
    await TenantMembership.create(user=user, tenant_id=1, source=MembershipSource.STAFF)
    async with mcp_session() as client:
        error, detail = await call_tool(client, raw, 'get_user', tenant='default', user_id=user.id)
    assert not error, detail
    assert detail['id'] == user.id
    assert detail['roles'] == []
