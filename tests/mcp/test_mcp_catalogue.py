"""Mechanical guardrails over the served tool catalogue.

The point of these is that they fail when someone adds a tool the *wrong* way.
``registry.register`` is the only path that attaches a gate, so a tool added via
``@mcp.tool()`` would serve data with no authorization at all and nothing else
in the suite would notice — its own happy-path test would pass.
"""

from mcpserver.auth import Gate
from mcpserver.registry import TOOL_SPECS
from tests.mcp.conftest import create_oauth_token, list_tools, mcp_session

# Tools that legitimately take no community, because they are how a caller
# discovers which communities exist.
GLOBAL_TOOLS = {'whoami', 'list_tenants'}

# A snapshot, so adding or renaming a tool is a deliberate diff rather than an
# invisible change to a published contract.
READ_TOOLS = {
    'activity_trends',
    'capacity_forecast',
    'crew_coverage_report',
    'crew_participation_trends',
    'get_async_qualifier',
    'get_async_qualifier_leaderboard',
    'get_bracket',
    'get_bracket_standings',
    'get_equipment',
    'get_match',
    'get_player_availability',
    'get_preset',
    'get_race_room',
    'get_schedule',
    'get_stream_room',
    'get_system_config',
    'get_tournament',
    'get_user',
    'list_async_qualifier_live_races',
    'list_async_qualifiers',
    'list_audit_log',
    'list_bracket_entrants',
    'list_bracket_matches',
    'list_brackets',
    'list_equipment',
    'list_feedback',
    'list_match_crew',
    'list_matches',
    'list_presets',
    'list_randomizers',
    'list_race_room_profiles',
    'list_race_rooms',
    'list_service_health',
    'list_speedgaming_episodes',
    'list_speedgaming_links',
    'list_stream_rooms',
    'list_tenants',
    'list_tournaments',
    'list_triforce_texts',
    'list_users',
    'list_volunteer_positions',
    'list_volunteer_shifts',
    'list_webhook_deliveries',
    'list_webhooks',
    'match_operations_report',
    'matches_active_at',
    'stream_room_utilization',
    'suggest_match_time',
    'telemetry_summary',
    'telemetry_top',
    'tournament_health',
    'volunteer_coverage',
    'volunteer_hour_trends',
    'whoami',
}

# The tools that change data. Served only to a connection whose consent screen
# was approved with the write box ticked, so they are snapshotted separately —
# a write tool that drifted into the read set would be one every read-only
# client is suddenly offered.
WRITE_TOOLS = {
    'acknowledge_match',
    'assign_match_stations',
    'assign_match_stream_room',
    'confirm_match',
    'create_match',
    'delete_match',
    'finish_match',
    'generate_match_seed',
    'record_match_result',
    'seat_match',
    'set_match_review',
    'set_match_stream_candidate',
    'signup_as_crew',
    'start_match',
    'submit_match_request',
    'unwatch_match',
    'update_match',
    'watch_match',
    'withdraw_crew_signup',
}

EXPECTED_TOOLS = READ_TOOLS | WRITE_TOOLS

# Writes that remove something rather than adding or amending it. Clients use
# the distinction to decide how hard to ask before proceeding.
DESTRUCTIVE_TOOLS = {'delete_match', 'withdraw_crew_signup'}


class TestCatalogue:
    async def test_a_writing_connection_is_served_every_tool(self, db):
        _, raw = await create_oauth_token(write=True)
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        assert {t['name'] for t in tools} == EXPECTED_TOOLS

    async def test_a_read_only_connection_is_served_no_write_tools(self, db):
        """The default grant must not advertise what it cannot call.

        Every write is refused at the gate regardless — this is about not
        spending a read-only client's context on nineteen tools it will never
        be allowed to use, and not letting the model plan a write it cannot do.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        assert {t['name'] for t in tools} == READ_TOOLS

    async def test_every_served_tool_is_gated(self, db):
        """The load-bearing one: nothing reached the server bypassing register()."""
        _, raw = await create_oauth_token(write=True)
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        ungated = [t['name'] for t in tools if t['name'] not in TOOL_SPECS]
        assert not ungated, f'tools served without a gate: {ungated}'

    async def test_every_tool_is_described_and_typed(self, db):
        """An undescribed tool is one the model will misuse or ignore."""
        _, raw = await create_oauth_token(write=True)
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        for tool in tools:
            assert tool.get('description', '').strip(), tool['name']
            schema = tool.get('inputSchema') or {}
            assert schema.get('type') == 'object', tool['name']

    async def test_every_tool_declares_an_output_schema(self, db):
        """Without one, the SDK returns the payload as a text blob.

        A bare ``-> dict`` annotation produces no output schema, so the client
        gets JSON-in-a-string with no declared shape while a ``Dict[str, Any]``
        one right beside it returns proper ``structuredContent``. The difference
        is invisible in the tool source and only shows up at the client, which
        is exactly why it is asserted here.
        """
        _, raw = await create_oauth_token(write=True)
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        missing = [t['name'] for t in tools if not t.get('outputSchema')]
        assert not missing, f'tools returning unstructured text: {missing}'

    async def test_the_read_only_hint_matches_the_declared_kind(self, db):
        """Clients skip the confirmation prompt on a readOnlyHint tool.

        So a write mis-annotated as a read is a change the user is never asked
        about, and a read mis-annotated as a write is a prompt on every lookup.
        """
        _, raw = await create_oauth_token(write=True)
        async with mcp_session() as client:
            tools = await list_tools(client, raw)
        for tool in tools:
            annotations = tool.get('annotations') or {}
            expected = tool['name'] not in WRITE_TOOLS
            assert annotations.get('readOnlyHint') is expected, tool['name']
            assert annotations.get('destructiveHint') is (
                tool['name'] in DESTRUCTIVE_TOOLS
            ), tool['name']

    async def test_community_scoped_tools_declare_a_tenant_argument(self, db):
        """A tool without `tenant` cannot be scoped, so it must be a GLOBAL one.

        Catches the reverse mistake too: a genuinely global tool that grew a
        tenant argument nobody honours.
        """
        _, raw = await create_oauth_token(write=True)
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
            name for name, spec in TOOL_SPECS.items() if spec.gate is Gate.GLOBAL
        }
        assert declared_global == GLOBAL_TOOLS

    def test_gate_registry_agrees_with_the_write_snapshot(self):
        """``write=True`` is what hides a tool and refuses a read-only token.

        A tool that changes data but was registered without it would be served
        to every connection and refuse none of them, which no other assertion
        here would catch.
        """
        declared_write = {name for name, spec in TOOL_SPECS.items() if spec.write}
        assert declared_write == WRITE_TOOLS
