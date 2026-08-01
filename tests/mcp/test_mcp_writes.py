"""The write surface: who may reach it, and whether it actually writes.

Three layers, and each catches something the others cannot:

* **The connection gate.** A read-only grant — the consent screen's default —
  must be refused at every write tool. This is the load-bearing one: the tools
  are hidden from a read-only listing, and a check that only hid them would look
  identical in every client while a hand-written ``tools/call`` sailed through.
* **The role gate underneath it.** A writing grant is not a promotion. The token
  acts as its user, so a member without the role is refused exactly as they are
  in the web UI.
* **The write itself.** A tool that returns cleanly having changed nothing is
  the failure no gate test can see, so each one is asserted against the row.
"""

from datetime import datetime, timedelta, timezone

from models import Match, MatchPlayers, Role, StreamRoom, Tournament, User
from tests.mcp.conftest import call_tool, create_oauth_token, mcp_session

TENANT = 'default'

# Every write tool with arguments that reach the gate rather than failing
# validation first. The gate runs before the tool body, so these need not name
# rows that exist.
WRITE_CALLS = {
    'create_match': {
        'tournament_id': 1, 'scheduled_date': '2026-05-01',
        'scheduled_time': '18:00', 'player_ids': [1, 2],
    },
    'submit_match_request': {
        'tournament_id': 1, 'scheduled_date': '2026-05-01',
        'scheduled_time': '18:00', 'player_ids': [1],
    },
    'update_match': {'match_id': 1, 'comment': 'x'},
    'delete_match': {'match_id': 1},
    'set_match_stream_candidate': {'match_id': 1, 'flag': True},
    'assign_match_stream_room': {'match_id': 1, 'stream_room_id': 1},
    'assign_match_stations': {'match_id': 1, 'assignments': {}},
    'seat_match': {'match_id': 1},
    'start_match': {'match_id': 1},
    'finish_match': {'match_id': 1},
    'confirm_match': {'match_id': 1},
    'record_match_result': {'match_id': 1, 'winner_id': 1},
    'set_match_review': {'match_id': 1, 'needs_review': True, 'note': 'x'},
    'generate_match_seed': {'match_id': 1},
    'signup_as_crew': {'match_id': 1, 'role': 'commentator'},
    'withdraw_crew_signup': {'match_id': 1, 'role': 'commentator'},
    'acknowledge_match': {'match_id': 1},
    'watch_match': {'match_id': 1},
    'unwatch_match': {'match_id': 1},
}


async def _match(*, players: list[User] | None = None) -> Match:
    tournament = await Tournament.create(name='Spring Open', is_active=True)
    match = await Match.create(
        tournament=tournament,
        scheduled_at=datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc),
    )
    for player in players or []:
        await MatchPlayers.create(match=match, user=player)
    return match


class TestTheConnectionGate:
    async def test_a_read_only_connection_is_refused_every_write(self, db):
        """Hiding the tools is not the gate; this is.

        A client that kept a cached listing, or one driving the JSON-RPC by
        hand, reaches these names whether or not they were advertised.
        """
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            for name, args in WRITE_CALLS.items():
                is_error, payload = await call_tool(
                    client, raw, name, tenant=TENANT, **args
                )
                assert is_error, name
                assert 'forbidden:' in payload, (name, payload)
                assert 'read' in payload.lower(), (name, payload)

    async def test_a_writing_connection_passes_the_connection_gate(self, db):
        """Same caller, same tools, box ticked — the refusal has to change.

        Asserted as "not refused for being read-only" rather than "succeeds",
        because these ids name nothing: a `not_found` here means the call got
        past the gate, which is what is under test.
        """
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        async with mcp_session() as client:
            for name, args in WRITE_CALLS.items():
                is_error, payload = await call_tool(
                    client, raw, name, tenant=TENANT, **args
                )
                if not is_error:
                    continue
                assert 'read-only' not in payload.lower(), (name, payload)

    async def test_the_membership_floor_still_answers_first(self, db):
        """A writing token must not disclose a community the user cannot see.

        If the read-only check ran first, a role-less user would learn from the
        wording that their *connection* was the problem — which is only true of
        a community that exists and that they might otherwise reach.
        """
        _, raw = await create_oauth_token()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'update_match', tenant=TENANT, match_id=1, comment='x',
            )
        assert is_error
        assert 'not_found:' in payload, payload


class TestTheRoleGateUnderneath:
    async def test_writing_is_not_a_promotion(self, db):
        """The token acts as its user; approving writes grants no role."""
        _, raw = await create_oauth_token(roles=[Role.VOLUNTEER], write=True)
        match = await _match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'delete_match', tenant=TENANT, match_id=match.id,
            )
        assert is_error, payload
        assert 'forbidden:' in payload, payload
        assert await Match.filter(id=match.id).exists()


class TestTheWritesLand:
    async def test_create_match_returns_the_new_match(self, db):
        user, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        tournament = await Tournament.create(name='Spring Open', is_active=True)
        player = await User.create(discord_id=771001, username='player-one')
        other = await User.create(discord_id=771002, username='player-two')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'create_match', tenant=TENANT,
                tournament_id=tournament.id,
                scheduled_date='2026-05-01', scheduled_time='18:00',
                player_ids=[player.id, other.id],
            )
        assert not is_error, payload
        assert payload['tournament']['id'] == tournament.id
        assert {p['user']['id'] for p in payload['players']} == {player.id, other.id}
        assert await Match.filter(id=payload['id']).exists()

    async def test_update_match_changes_the_row(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        match = await _match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'update_match', tenant=TENANT,
                match_id=match.id, comment='moved for the restream',
            )
        assert not is_error, payload
        assert payload['comment'] == 'moved for the restream'
        await match.refresh_from_db()
        assert match.comment == 'moved for the restream'

    async def test_assign_stream_room_and_clear_it(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        match = await _match()
        room = await StreamRoom.create(name='Main Stage', is_active=True)
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'assign_match_stream_room', tenant=TENANT,
                match_id=match.id, stream_room_id=room.id,
            )
            assert not is_error, payload
            assert payload['stream_room']['id'] == room.id

            # Omitting the id clears the room rather than leaving it alone —
            # the one argument whose absence means something.
            is_error, payload = await call_tool(
                client, raw, 'assign_match_stream_room', tenant=TENANT,
                match_id=match.id,
            )
        assert not is_error, payload
        assert payload['stream_room'] is None

    async def test_delete_match_removes_it(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        match = await _match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'delete_match', tenant=TENANT, match_id=match.id,
            )
        assert not is_error, payload
        assert payload['ok'] is True
        assert not await Match.filter(id=match.id).exists()

    async def test_a_tournament_in_another_community_cannot_be_scheduled_into(self, db):
        """A bare id must not be able to plant a match across the boundary.

        The permission check short-circuits for staff and the scheduling-hours
        check falls through for a tournament it cannot see, so before the scoped
        resolve in `create_match` this produced a real match — and enrolled its
        players — in the other community's tournament.
        """
        from models import Tenant

        other = await Tenant.create(slug='other-community', name='Other', is_active=True)
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        theirs = await Tournament.create(
            name='Their Open', is_active=True, tenant_id=other.id,
        )
        player = await User.create(discord_id=772001, username='p1')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'create_match', tenant=TENANT,
                tournament_id=theirs.id, scheduled_date='2026-05-01',
                scheduled_time='18:00', player_ids=[player.id],
            )
        assert is_error, payload
        assert 'not_found:' in payload, payload
        assert not await Match.filter(tournament_id=theirs.id).exists()

    async def test_stations_keyed_by_user_id_are_refused(self, db):
        """Applying nothing and reporting success is the worst answer here.

        The keys are participation-row ids and the near-miss is a user id, so a
        wrong key set used to mean a clean `MatchResponse`, an audit row and an
        event for a write that changed nothing.
        """
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        player = await User.create(discord_id=772002, username='p2')
        match = await _match(players=[player])
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'assign_match_stations', tenant=TENANT,
                match_id=match.id, assignments={str(player.id + 5000): 'A'},
            )
        assert is_error, payload
        assert 'invalid_request:' in payload, payload
        assert 'user ids' in payload, payload

    async def test_a_match_in_another_community_is_not_found(self, db):
        """The write path hand-scopes its load; a bare id must not cross over."""
        from models import Tenant

        other = await Tenant.create(slug='other-community', name='Other', is_active=True)
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        tournament = await Tournament.create(
            name='Their Open', is_active=True, tenant_id=other.id,
        )
        match = await Match.create(
            tournament=tournament, tenant_id=other.id,
            scheduled_at=datetime(2026, 5, 1, 18, 0, tzinfo=timezone.utc),
        )
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'seat_match', tenant=TENANT, match_id=match.id,
            )
        assert is_error
        assert 'not_found:' in payload, payload


class TestOrientationReportsTheGrant:
    async def test_whoami_reports_a_read_only_connection(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF])
        async with mcp_session() as client:
            is_error, payload = await call_tool(client, raw, 'whoami')
        assert not is_error, payload
        assert payload['can_write'] is False

    async def test_whoami_reports_a_writing_connection(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        async with mcp_session() as client:
            is_error, payload = await call_tool(client, raw, 'whoami')
        assert not is_error, payload
        assert payload['can_write'] is True


class TestConsentDecidesTheGrant:
    async def test_approving_without_the_box_mints_a_read_only_token(self, db):
        from application.services.mcp_auth_service import READ_SCOPE, WRITE_SCOPE

        _, token = await _approve(allow_write=False)
        assert token.read_only is True
        assert token.scope == READ_SCOPE
        assert WRITE_SCOPE not in (token.scope or '')

    async def test_approving_with_the_box_mints_a_writing_token(self, db):
        from application.services.mcp_auth_service import WRITE_SCOPE

        _, token = await _approve(allow_write=True)
        assert token.read_only is False
        assert WRITE_SCOPE in token.scope

    async def test_a_client_requesting_write_still_gets_read_only(self, db):
        """The client asks; the human decides. Nothing else does.

        Without this, a client that pads its authorize request with
        `scope=wizzrobe:write` would be granted it by default, and the box on
        the consent screen would be decoration.
        """
        _, token = await _approve(allow_write=False, requested_scopes=[
            'wizzrobe:read', 'wizzrobe:write',
        ])
        assert token.read_only is True

    async def test_a_refresh_cannot_widen_a_read_only_grant(self, db):
        """Rotation re-keys the row, so the grant is fixed at consent."""
        from application.services import McpAuthService

        _, token = await _approve(allow_write=False)
        await McpAuthService().exchange_refresh(token)
        await token.refresh_from_db()
        assert token.read_only is True


async def _approve(*, allow_write: bool, requested_scopes: list[str] | None = None):
    """Drive one grant through consent and return ``(user, token)``."""
    import secrets

    from application.services import McpAuthService
    from application.services.mcp_auth_service import PendingAuthorization
    from models import ApiToken, McpOAuthClient

    service = McpAuthService()
    client = await McpOAuthClient.create(
        client_id=f'consent-{secrets.token_hex(4)}',
        client_name='Consent Test Client',
        redirect_uris=['http://localhost/callback'],
        grant_types=['authorization_code', 'refresh_token'],
        response_types=['code'],
    )
    user = await User.create(
        discord_id=secrets.randbelow(10 ** 12) + 1, username=f'c-{secrets.token_hex(3)}',
    )
    txn = service.begin_authorization(PendingAuthorization(
        client_id=client.client_id,
        redirect_uri='http://localhost/callback',
        redirect_uri_provided_explicitly=True,
        code_challenge='challenge',
        scopes=requested_scopes or ['wizzrobe:read'],
        state=None,
        resource=None,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    raw_code, _, _ = await service.approve(txn, user, allow_write=allow_write)
    code = await service.load_code(client.client_id, raw_code)
    await service.exchange_code(code)
    return user, await ApiToken.get(user=user)
