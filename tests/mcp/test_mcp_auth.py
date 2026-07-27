"""Per-tool authorization, and how refusals are worded.

Two things under test that are easy to get subtly wrong:

* Each tool's gate matches its REST counterpart, so the MCP surface is not a
  quieter way to reach something the API would refuse.
* A feature the community has not enabled reports as `not_found`, never as
  `forbidden` — for *everyone*, staff included. A `forbidden` there would tell
  an unauthorized caller the feature exists, and would give staff and players
  different answers about something that is simply switched off.
"""

from application.tenant_context import tenant_scope
from models import FeatureFlag, Role, TenantFeatureFlag
from tests.mcp.conftest import call_tool, create_oauth_token, mcp_session

TENANT = 'default'

# Tool -> the minimum role that may call it, with arguments that reach the gate
# rather than failing validation first.
ADMIN_TOOLS = {
    'list_audit_log': {},
    'list_match_crew': {'match_id': 1},
    'crew_coverage_report': {'start': '2026-01-01T00:00:00', 'end': '2026-01-02T00:00:00'},
    'match_operations_report': {'start': '2026-01-01T00:00:00', 'end': '2026-01-02T00:00:00'},
}
STAFF_TOOLS = {
    'list_users': {},
    'telemetry_summary': {},
    'get_system_config': {},
}
ACTOR_TOOLS = {
    'list_tournaments': {},
    'list_matches': {},
    'list_stream_rooms': {},
}


def _forbidden(payload: str) -> bool:
    return 'forbidden:' in payload


class TestMemberFloor:
    async def test_a_user_with_no_role_cannot_reach_a_community(self, db):
        """The floor that keeps MCP's reach equal to the REST API's.

        A REST token is bound to one community and can never address another.
        An OAuth token is platform-wide, so without this a signed-in user of any
        community could read every other community's schedule.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            for name, args in ACTOR_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                assert is_error, name
                # not_found, not forbidden: existence is not disclosed.
                assert 'not_found:' in payload, (name, payload)

    async def test_a_member_can_use_actor_tools(self, db):
        _, raw = await create_oauth_token(roles=[Role.PROCTOR])
        async with mcp_session() as client:
            for name, args in ACTOR_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                assert not is_error, (name, payload)


class TestGateMatrix:
    async def test_member_without_staff_is_refused_staff_tools(self, db):
        _, raw = await create_oauth_token(roles=[Role.PROCTOR])
        async with mcp_session() as client:
            for name, args in STAFF_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                assert is_error, name
                assert _forbidden(payload), (name, payload)

    async def test_member_without_admin_is_refused_admin_tools(self, db):
        _, raw = await create_oauth_token(roles=[Role.PROCTOR])
        async with mcp_session() as client:
            for name, args in ADMIN_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                assert is_error, name
                assert _forbidden(payload), (name, payload)

    async def test_staff_passes_staff_and_admin_gates(self, db):
        """STAFF satisfies can_view_admin too, matching the REST gates."""
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            for name, args in STAFF_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                assert not is_error, (name, payload)
            for name, args in ADMIN_TOOLS.items():
                is_error, payload = await call_tool(client, raw, name, tenant=TENANT, **args)
                # A missing row is fine here; a refusal is not.
                assert not (is_error and _forbidden(payload)), (name, payload)


class TestFeatureGate:
    async def test_disabled_feature_is_not_found_even_for_staff(self, db):
        """The gate hides, it does not merely refuse.

        Asserting this for a *staff* caller is the point: with the checks in the
        wrong order, staff would sail past the flag and get a real answer for a
        feature their community has turned off.
        """
        await TenantFeatureFlag.filter(flag=FeatureFlag.VOLUNTEERS.value).update(
            available=False, enabled=False,
        )
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_volunteer_shifts', tenant=TENANT,
                start='2026-01-01T00:00:00', end='2026-01-02T00:00:00',
            )
        assert is_error
        assert 'not_found:' in payload, payload
        assert not _forbidden(payload), payload

    async def test_enabled_feature_is_reachable_by_staff(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_volunteer_shifts', tenant=TENANT,
                start='2026-01-01T00:00:00', end='2026-01-02T00:00:00',
            )
        assert not is_error, payload


class TestReadOnlyTokensAreAccepted:
    async def test_every_oauth_token_is_read_only_and_still_works(self, db):
        """Explicit regression test for a deliberate omission.

        Every OAuth token is minted read_only=True because the surface performs
        no writes, so there is no read-only rejection anywhere in mcpserver/.
        Someone "restoring" one for symmetry with the REST API would break every
        single caller — this test is what stops that.
        """
        from models import ApiToken

        user, raw = await create_oauth_token(roles=[Role.STAFF])
        token = await ApiToken.get(user=user)
        assert token.read_only is True
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_tournaments', tenant=TENANT,
            )
        assert not is_error, payload


class TestErrorMapping:
    async def test_missing_row_is_not_found(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_match', match_id=999999, tenant=TENANT,
            )
        assert is_error
        assert 'not_found:' in payload

    async def test_bad_argument_is_invalid_request(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_schedule', date='not-a-date', tenant=TENANT,
            )
        assert is_error
        assert 'invalid_request:' in payload

    async def test_unknown_enum_value_explains_the_valid_set(self, db):
        """An error the model can act on beats one it can only report."""
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'telemetry_top', dimension='nonsense', tenant=TENANT,
            )
        assert is_error
        assert 'invalid_request:' in payload
        assert 'paths' in payload

    async def test_internal_errors_do_not_leak_internals(self, db, monkeypatch):
        """An unexpected failure must reach the model as an opaque message."""
        from application.services import TournamentService

        async def boom(*args, **kwargs):
            raise RuntimeError('secret connection string in here')

        monkeypatch.setattr(TournamentService, 'get_all_tournaments', boom)
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_tournaments', tenant=TENANT,
            )
        assert is_error
        assert 'internal_error:' in payload
        assert 'secret connection string' not in payload
        assert 'Traceback' not in payload


class TestSuperAdmin:
    async def test_super_admin_reaches_a_community_without_a_local_role(self, db):
        """SUPER_ADMIN is the one global role and bypasses the membership floor."""
        _, raw = await create_oauth_token(roles=[Role.SUPER_ADMIN])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_tournaments', tenant=TENANT,
            )
        assert not is_error, payload

    async def test_super_admin_does_not_bypass_a_feature_flag(self, db):
        """A flag is a product decision, not a permission — nobody overrides it."""
        await TenantFeatureFlag.filter(flag=FeatureFlag.BRACKETS.value).update(
            available=False, enabled=False,
        )
        _, raw = await create_oauth_token(roles=[Role.SUPER_ADMIN])
        with tenant_scope(1):
            pass
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_brackets', tournament_id=1, tenant=TENANT,
            )
        assert is_error
        assert 'not_found:' in payload
