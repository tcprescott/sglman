"""Every read tool, called against real rows.

The catalogue suite proves a tool is *served* and *gated*; it never runs one.
That gap is exactly where a compact result shape fails: these tools reshape ORM
rows by hand, so a renamed relation or an un-prefetched FK surfaces as an
``internal_error`` at call time and nothing in the schema-level tests notices.

Each test therefore seeds the rows its tool reads and asserts on the payload,
not merely on the absence of an error — a tool that quietly returns ``[]``
because it filtered on the wrong field would otherwise look healthy.
"""

from datetime import datetime, timedelta, timezone

from models import (
    AsyncQualifier,
    AsyncQualifierPool,
    Bracket,
    BracketEntrant,
    BracketEntry,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    Equipment,
    EquipmentLoan,
    EquipmentStatus,
    Feedback,
    FeedbackCategory,
    Match,
    PlayerAvailability,
    Preset,
    RaceRoomProfile,
    RacetimeRoom,
    Role,
    SpeedGamingEpisode,
    SpeedGamingEventLink,
    StreamRoom,
    Tournament,
    User,
    VolunteerAvailabilityStatus,
    Webhook,
    WebhookDelivery,
)
from tests.mcp.conftest import call_tool, create_oauth_token, mcp_session

TENANT = 'default'
NOW = datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc)
WINDOW = {'start': '2026-02-01T00:00:00+00:00', 'end': '2026-04-01T00:00:00+00:00'}


async def _staff():
    return await create_oauth_token(username='mcp-reader', roles=[Role.STAFF])


async def _tournament(name: str = 'Spring Open') -> Tournament:
    return await Tournament.create(name=name, is_active=True)


class TestOrientation:
    async def test_whoami_reports_the_communitys_enabled_features(self, db):
        """The server instructions promise this, so it has to be in the payload.

        A caller that can see which subsystems are on skips the tools that would
        answer `not_found`, instead of learning it one round-trip at a time.
        """
        _, raw = await _staff()
        async with mcp_session() as client:
            is_error, payload = await call_tool(client, raw, 'whoami')
        assert not is_error, payload
        community = payload['tenants'][0]
        assert community['slug'] == TENANT
        assert 'volunteers' in community['features']
        assert 'staff' in community['roles']


class TestEquipment:
    async def test_list_and_get_report_the_current_borrower(self, db):
        user, raw = await _staff()
        asset = await Equipment.create(
            asset_number=7, name='Capture card', status=EquipmentStatus.CHECKED_OUT,
        )
        await EquipmentLoan.create(equipment=asset, borrower=user, checked_out_by=user)

        async with mcp_session() as client:
            is_error, listing = await call_tool(
                client, raw, 'list_equipment', tenant=TENANT,
            )
            assert not is_error, listing
            is_error, detail = await call_tool(
                client, raw, 'get_equipment', tenant=TENANT, equipment_id=asset.id,
            )
        rows = listing['result']
        assert [r['asset_number'] for r in rows] == [7]
        assert rows[0]['borrower'] == user.preferred_name
        assert not is_error, detail
        assert len(detail['loans']) == 1
        assert detail['loans'][0]['checked_in_at'] is None

    async def test_status_filter_narrows_the_inventory(self, db):
        _, raw = await _staff()
        await Equipment.create(asset_number=1, name='Console', status=EquipmentStatus.AVAILABLE)
        await Equipment.create(asset_number=2, name='Retired rig', status=EquipmentStatus.RETIRED)

        async with mcp_session() as client:
            _, payload = await call_tool(
                client, raw, 'list_equipment', tenant=TENANT, status='retired',
            )
        assert [r['name'] for r in payload['result']] == ['Retired rig']

    async def test_an_unknown_status_explains_the_valid_set(self, db):
        """A silent empty list would read as "no equipment", not "bad filter"."""
        _, raw = await _staff()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_equipment', tenant=TENANT, status='borrowed',
            )
        assert is_error
        assert 'invalid_request:' in payload
        assert 'checked_out' in payload


class TestOnlinePlay:
    async def test_presets_list_compactly_and_read_in_full(self, db):
        _, raw = await _staff()
        preset = await Preset.create(
            name='Open Standard', randomizer='alttpr',
            settings={'glitches': 'none'}, description='Weekly settings',
        )
        await Preset.create(name='Other game', randomizer='smz3', settings={})

        async with mcp_session() as client:
            _, listing = await call_tool(
                client, raw, 'list_presets', tenant=TENANT, randomizer='alttpr',
            )
            is_error, detail = await call_tool(
                client, raw, 'get_preset', tenant=TENANT, preset_id=preset.id,
            )
        assert [p['name'] for p in listing['result']] == ['Open Standard']
        # The summary carries no settings; the detail is the only way to get them.
        assert 'settings' not in listing['result'][0]
        assert not is_error, detail
        assert detail['settings'] == {'glitches': 'none'}

    async def test_race_rooms_list_open_and_resolve_by_match(self, db):
        _, raw = await _staff()
        tournament = await _tournament()
        match = await Match.create(tournament=tournament, scheduled_at=NOW)
        await RacetimeRoom.create(
            slug='alttpr/happy-link-1234', category='alttpr',
            room_name='Race', match=match, opened_at=NOW,
        )

        async with mcp_session() as client:
            _, open_rooms = await call_tool(client, raw, 'list_race_rooms', tenant=TENANT)
            is_error, room = await call_tool(
                client, raw, 'get_race_room', tenant=TENANT, match_id=match.id,
            )
        assert [r['slug'] for r in open_rooms['result']] == ['alttpr/happy-link-1234']
        assert not is_error, room
        assert room['match_id'] == match.id
        assert room['status'] == 'open'

    async def test_missing_race_room_is_not_found_not_an_error(self, db):
        _, raw = await _staff()
        tournament = await _tournament()
        match = await Match.create(tournament=tournament, scheduled_at=NOW)
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_race_room', tenant=TENANT, match_id=match.id,
            )
        assert is_error
        assert 'not_found:' in payload

    async def test_race_room_profiles_list(self, db):
        _, raw = await _staff()
        await RaceRoomProfile.create(name='Tournament room', goal='Beat the game')
        async with mcp_session() as client:
            _, payload = await call_tool(
                client, raw, 'list_race_room_profiles', tenant=TENANT,
            )
        assert payload['result'][0]['goal'] == 'Beat the game'

    async def test_speedgaming_links_and_their_episodes(self, db):
        _, raw = await _staff()
        tournament = await _tournament()
        link = await SpeedGamingEventLink.create(
            tournament=tournament, event_slug='alttprleague', last_status='ok',
        )
        await SpeedGamingEpisode.create(
            event_link=link, sg_episode_id='4242', title='Week 1', scheduled_at=NOW,
        )

        async with mcp_session() as client:
            _, links = await call_tool(
                client, raw, 'list_speedgaming_links', tenant=TENANT,
            )
            _, episodes = await call_tool(
                client, raw, 'list_speedgaming_episodes', tenant=TENANT, link_id=link.id,
            )
        assert links['result'][0]['event_slug'] == 'alttprleague'
        assert episodes['result'][0]['sg_episode_id'] == '4242'
        # The upstream payload blob is deliberately not echoed back.
        assert 'payload' not in episodes['result'][0]


class TestBrackets:
    async def _bracket(self):
        tournament = await _tournament('Bracket Cup')
        bracket = await Bracket.create(
            tournament=tournament, name='Main', format=BracketFormat.SINGLE_ELIM,
        )
        entrants = [
            await BracketEntrant.create(tournament=tournament, display_name=name)
            for name in ('Alice', 'Bob')
        ]
        entries = [
            await BracketEntry.create(bracket=bracket, entrant=entrant, seed=seed)
            for seed, entrant in enumerate(entrants, start=1)
        ]
        await BracketMatch.create(
            bracket=bracket, round=1, position=1,
            entry1=entries[0], entry2=entries[1], winner=entries[0],
            entry1_score=2, entry2_score=1, state=BracketMatchState.COMPLETE,
        )
        return tournament, bracket

    async def test_get_bracket_counts_its_field(self, db):
        _, raw = await _staff()
        _, bracket = await self._bracket()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_bracket', tenant=TENANT, bracket_id=bracket.id,
            )
        assert not is_error, payload
        assert payload['format'] == 'single_elim'
        assert payload['entry_count'] == 2

    async def test_bracket_matches_name_their_entrants(self, db):
        """The reshaping worth testing: entry ids resolved to people.

        ``list_matches`` does not prefetch entries, so the names come from two
        separate list reads — a mapping that is easy to get subtly wrong and
        impossible to spot in a schema-level test.
        """
        _, raw = await _staff()
        _, bracket = await self._bracket()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_bracket_matches', tenant=TENANT, bracket_id=bracket.id,
            )
        assert not is_error, payload
        pairing = payload['result'][0]
        assert (pairing['entry1'], pairing['entry2']) == ('Alice', 'Bob')
        assert pairing['winner'] == 'Alice'
        assert (pairing['entry1_score'], pairing['entry2_score']) == (2, 1)

    async def test_entrants_are_listed_per_tournament(self, db):
        _, raw = await _staff()
        tournament, _ = await self._bracket()
        async with mcp_session() as client:
            _, payload = await call_tool(
                client, raw, 'list_bracket_entrants',
                tenant=TENANT, tournament_id=tournament.id,
            )
        assert sorted(e['display_name'] for e in payload['result']) == ['Alice', 'Bob']


class TestAsyncQualifiers:
    async def test_qualifier_detail_includes_its_pools(self, db):
        _, raw = await _staff()
        qualifier = await AsyncQualifier.create(name='Season 5 Quals', runs_per_pool=2)
        await AsyncQualifierPool.create(qualifier=qualifier, name='Pool A')

        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_async_qualifier', tenant=TENANT, qualifier_id=qualifier.id,
            )
        assert not is_error, payload
        assert payload['runs_per_pool'] == 2
        assert [p['name'] for p in payload['pools']] == ['Pool A']
        assert payload['pools'][0]['permalink_count'] == 0

    async def test_leaderboard_is_readable_by_a_qualifier_admin(self, db):
        """An empty board is still the right answer; a refusal would not be."""
        _, raw = await _staff()
        qualifier = await AsyncQualifier.create(name='Season 5 Quals')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_async_qualifier_leaderboard',
                tenant=TENANT, qualifier_id=qualifier.id,
            )
        assert not is_error, payload
        assert payload['result'] == []

    async def test_live_races_list_for_a_qualifier(self, db):
        _, raw = await _staff()
        qualifier = await AsyncQualifier.create(name='Season 5 Quals')
        pool = await AsyncQualifierPool.create(qualifier=qualifier, name='Pool A')
        from models import AsyncQualifierLiveRace

        await AsyncQualifierLiveRace.create(pool=pool, match_title='Finals A')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_async_qualifier_live_races',
                tenant=TENANT, qualifier_id=qualifier.id,
            )
        assert not is_error, payload
        assert payload['result'][0]['match_title'] == 'Finals A'
        assert payload['result'][0]['pool'] == 'Pool A'


class TestObservability:
    async def test_webhooks_never_disclose_their_signing_secret(self, db):
        """The one thing this tool must not return."""
        _, raw = await _staff()
        hook = await Webhook.create(
            name='Ops', url='https://example.test/hook',
            secret='super-secret-value', event_types=['match.created'],
        )
        await WebhookDelivery.create(
            webhook=hook, event_type='match.created', payload='{}',
            success=False, response_status=500, attempt_count=3, error='boom',
        )

        async with mcp_session() as client:
            _, hooks = await call_tool(client, raw, 'list_webhooks', tenant=TENANT)
            _, deliveries = await call_tool(
                client, raw, 'list_webhook_deliveries', tenant=TENANT, webhook_id=hook.id,
            )
        assert hooks['result'][0]['event_types'] == ['match.created']
        assert 'super-secret-value' not in str(hooks)
        assert deliveries['result'][0]['response_status'] == 500
        # The serialized request body is bulk, and the audit log already has it.
        assert 'payload' not in deliveries['result'][0]

    async def test_feedback_lists_most_recent_first(self, db):
        user, raw = await _staff()
        await Feedback.create(
            user=user, category=FeedbackCategory.OTHER,
            message='Older note', page_url='/admin',
        )
        await Feedback.create(
            user=user, category=FeedbackCategory.OTHER,
            message='Newer note', page_url='/schedule',
        )
        async with mcp_session() as client:
            _, payload = await call_tool(client, raw, 'list_feedback', tenant=TENANT)
        assert [f['message'] for f in payload['result']] == ['Newer note', 'Older note']
        assert payload['result'][0]['submitted_by'] == user.preferred_name

    async def test_service_health_probes_the_tenants_own_integrations(self, db):
        _, raw = await _staff()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'list_service_health', tenant=TENANT,
            )
        assert not is_error, payload
        for probe in payload['result']:
            assert probe['status']
            assert probe['checked_at']


class TestAnalytics:
    async def _scheduled_match(self):
        tournament = await _tournament('Analytics Cup')
        room = await StreamRoom.create(name='Main Channel', is_active=True)
        await Match.create(
            tournament=tournament, stream_room=room, scheduled_at=NOW,
        )
        return tournament

    async def test_capacity_forecast_summarizes_instead_of_dumping_intervals(self, db):
        """A forecast is a shape, not a series: peaks, not every interval.

        The service builds a per-interval payload for a chart; handing that to a
        model buries the answer, so the tool must not simply pass it through.
        """
        _, raw = await _staff()
        await self._scheduled_match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'capacity_forecast', tenant=TENANT, **WINDOW,
            )
        assert not is_error, payload
        forecast = payload['result']
        assert 'intervals' not in forecast
        assert 'match_ids_per_interval' not in forecast
        assert forecast['interval_minutes'] > 0
        assert len(forecast['busiest']) <= 5

    async def test_stream_room_utilization_reports_per_room_totals(self, db):
        """Its raw payload carries ORM Match rows, which cannot be serialized."""
        _, raw = await _staff()
        await self._scheduled_match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'stream_room_utilization', tenant=TENANT, **WINDOW,
            )
        assert not is_error, payload
        room = payload['result']['rooms'][0]
        assert room['stream_room_name'] == 'Main Channel'
        assert room['match_count'] == 1
        assert 'matches' not in room

    async def test_tournament_health_scores_the_window(self, db):
        _, raw = await _staff()
        await self._scheduled_match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'tournament_health', tenant=TENANT, **WINDOW,
            )
        assert not is_error, payload
        assert payload['result'][0]['tournament_name'] == 'Analytics Cup'

    async def test_trend_tools_return_a_bucketed_series(self, db):
        _, raw = await _staff()
        await self._scheduled_match()
        async with mcp_session() as client:
            for name in ('crew_participation_trends', 'activity_trends'):
                is_error, payload = await call_tool(
                    client, raw, name, tenant=TENANT, bucket='week', **WINDOW,
                )
                assert not is_error, (name, payload)
                series = payload['result']
                assert series['bucket'] == 'week'
                assert series['bucket_labels']

    async def test_volunteer_hour_trends_is_bucketed_too(self, db):
        _, raw = await _staff()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'volunteer_hour_trends', tenant=TENANT, **WINDOW,
            )
        assert not is_error, payload
        assert payload['result']['totals']['scheduled_hours'] == 0

    async def test_matches_active_at_finds_a_match_in_progress(self, db):
        _, raw = await _staff()
        await self._scheduled_match()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'matches_active_at', tenant=TENANT,
                instant=(NOW + timedelta(minutes=30)).isoformat(),
            )
        assert not is_error, payload
        assert payload['result'][0]['stream_room'] == 'Main Channel'


class TestPlayerAvailability:
    async def test_a_player_reads_their_own_windows(self, db):
        user, raw = await create_oauth_token(username='player', roles=[Role.PROCTOR])
        await PlayerAvailability.create(
            user=user, starts_at=NOW, ends_at=NOW + timedelta(hours=4),
            status=VolunteerAvailabilityStatus.PREFERRED, note='After work',
        )
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_player_availability', tenant=TENANT, **WINDOW,
            )
        assert not is_error, payload
        assert payload['result'][0]['user_id'] == user.id
        assert payload['result'][0]['windows'][0]['status'] == 'preferred'

    async def test_reading_someone_else_requires_staff(self, db):
        _, raw = await create_oauth_token(username='nosy', roles=[Role.PROCTOR])
        other = await User.create(discord_id=987654321, username='other')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_player_availability',
                tenant=TENANT, user_ids=[other.id], **WINDOW,
            )
        assert is_error
        assert 'forbidden:' in payload

    async def test_staff_may_read_a_squad_and_silence_is_visible(self, db):
        """A player who declared nothing comes back empty, not missing.

        Dropping them would make "has not answered" indistinguishable from "was
        not asked about", which is the question a scheduler is actually asking.
        """
        _, raw = await _staff()
        quiet = await User.create(discord_id=112233, username='quiet')
        answered = await User.create(discord_id=445566, username='answered')
        await PlayerAvailability.create(
            user=answered, starts_at=NOW, ends_at=NOW + timedelta(hours=2),
            status=VolunteerAvailabilityStatus.AVAILABLE,
        )
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_player_availability',
                tenant=TENANT, user_ids=[quiet.id, answered.id], **WINDOW,
            )
        assert not is_error, payload
        by_id = {row['user_id']: row for row in payload['result']}
        assert by_id[quiet.id]['windows'] == []
        assert len(by_id[answered.id]['windows']) == 1

    async def test_the_squad_size_is_capped(self, db):
        _, raw = await _staff()
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'get_player_availability',
                tenant=TENANT, user_ids=list(range(1, 60)), **WINDOW,
            )
        assert is_error
        assert 'invalid_request:' in payload
