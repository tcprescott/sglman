"""Mechanical guardrails over the served tool catalogue.

The point of these is that they fail when someone adds a tool the *wrong* way.
``registry.register`` is the only path that attaches a gate, so a tool added via
``@mcp.tool()`` would serve data with no authorization at all and nothing else
in the suite would notice — its own happy-path test would pass.
"""

from mcpserver.auth import Gate
from mcpserver.registry import TOOL_GATES
from tests.mcp.conftest import create_oauth_token, list_tools, mcp_session

# Tools that legitimately take no community, because they are how a caller
# discovers which communities exist.
GLOBAL_TOOLS = {'whoami', 'list_tenants'}

# A snapshot, so adding or renaming a tool is a deliberate diff rather than an
# invisible change to a published contract.
EXPECTED_TOOLS = {
    'crew_coverage_report',
    'get_bracket_standings',
    'get_match',
    'get_schedule',
    'get_system_config',
    'get_tournament',
    'get_user',
    'list_async_qualifiers',
    'list_audit_log',
    'list_brackets',
    'list_match_crew',
    'list_matches',
    'list_stream_rooms',
    'list_tenants',
    'list_tournaments',
    'list_users',
    'list_volunteer_shifts',
    'match_operations_report',
    'telemetry_summary',
    'telemetry_top',
    'volunteer_coverage',
    'whoami',
}


class TestCatalogue:
    async def test_served_tools_match_the_snapshot(self, db):
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        assert {t['name'] for t in tools} == EXPECTED_TOOLS

    async def test_every_served_tool_is_gated(self, db):
        """The load-bearing one: nothing reached the server bypassing register()."""
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        ungated = [t['name'] for t in tools if t['name'] not in TOOL_GATES]
        assert not ungated, f'tools served without a gate: {ungated}'

    async def test_every_tool_is_described_and_typed(self, db):
        """An undescribed tool is one the model will misuse or ignore."""
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        for tool in tools:
            assert tool.get('description', '').strip(), tool['name']
            schema = tool.get('inputSchema') or {}
            assert schema.get('type') == 'object', tool['name']

    async def test_every_tool_is_marked_read_only(self, db):
        """The whole surface is reads; clients rely on the hint to skip prompts."""
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        for tool in tools:
            annotations = tool.get('annotations') or {}
            assert annotations.get('readOnlyHint') is True, tool['name']

    async def test_community_scoped_tools_declare_a_tenant_argument(self, db):
        """A tool without `tenant` cannot be scoped, so it must be a GLOBAL one.

        Catches the reverse mistake too: a genuinely global tool that grew a
        tenant argument nobody honours.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        for tool in tools:
            properties = (tool.get('inputSchema') or {}).get('properties') or {}
            has_tenant = 'tenant' in properties
            if tool['name'] in GLOBAL_TOOLS:
                assert not has_tenant, f'{tool["name"]} should not take a tenant'
            else:
                assert has_tenant, f'{tool["name"]} is missing a tenant argument'

    def test_gate_registry_agrees_with_global_list(self):
        """The two notions of "global" must not drift apart."""
        declared_global = {
            name for name, (gate, _) in TOOL_GATES.items() if gate is Gate.GLOBAL
        }
        assert declared_global == GLOBAL_TOOLS
