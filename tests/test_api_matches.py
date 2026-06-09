"""Integration tests for the GET /matches endpoint.

These tests use a fresh in-memory SQLite database (via the function-scoped
``db`` fixture) and exercise the real ORM query path. The full FastAPI app
is not mounted; we attach only the api router to keep the test app
lightweight and avoid the Discord bot startup.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import api
from models import (
    Commentator,
    GeneratedSeeds,
    Match,
    MatchPlayers,
    StreamRoom,
    Tournament,
    Tracker,
    User,
)


@pytest.fixture
def app():
    """Minimal FastAPI app exposing only the matches router."""
    test_app = FastAPI()
    test_app.include_router(api.router, prefix='/api')
    return test_app


@pytest.fixture
async def client(db, app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        yield ac


async def _seed_basic_data() -> dict:
    """Seed two tournaments, two stream rooms, four matches with varied times.

    Returns a dict of created objects for use in assertions.
    """
    t1 = await Tournament.create(name='Cup A')
    t2 = await Tournament.create(name='Cup B')

    room1 = await StreamRoom.create(name='Stage 1')
    room2 = await StreamRoom.create(name='Stage 2')

    # m1: T1 / room1, earliest
    m1 = await Match.create(
        tournament=t1, stream_room=room1,
        scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    # m2: T1 / room2
    m2 = await Match.create(
        tournament=t1, stream_room=room2,
        scheduled_at=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
    )
    # m3: T2 / no room
    m3 = await Match.create(
        tournament=t2,
        scheduled_at=datetime(2025, 1, 3, 12, 0, tzinfo=timezone.utc),
    )
    # m4: T2 / room1, latest
    m4 = await Match.create(
        tournament=t2, stream_room=room1,
        scheduled_at=datetime(2025, 1, 4, 12, 0, tzinfo=timezone.utc),
    )

    return {
        't1': t1, 't2': t2,
        'room1': room1, 'room2': room2,
        'm1': m1, 'm2': m2, 'm3': m3, 'm4': m4,
    }


# ---------------------------------------------------------------------------
# Empty / basic cases
# ---------------------------------------------------------------------------


class TestGetMatchesEmpty:
    async def test_empty_db_returns_empty_list(self, client):
        response = await client.get('/api/matches')
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Result ordering and shape
# ---------------------------------------------------------------------------


class TestResultShape:
    async def test_matches_ordered_by_scheduled_at(self, client):
        data = await _seed_basic_data()
        response = await client.get('/api/matches')
        assert response.status_code == 200
        ids = [m['id'] for m in response.json()]
        assert ids == [data['m1'].id, data['m2'].id, data['m3'].id, data['m4'].id]

    async def test_response_includes_tournament_metadata(self, client):
        data = await _seed_basic_data()
        response = await client.get('/api/matches')
        body = response.json()
        first = body[0]
        assert first['tournament']['id'] == data['t1'].id
        assert first['tournament']['name'] == 'Cup A'

    async def test_response_includes_stream_room_when_set(self, client):
        data = await _seed_basic_data()
        response = await client.get('/api/matches')
        body = response.json()
        # m1 has room1, m3 has no room.
        by_id = {m['id']: m for m in body}
        assert by_id[data['m1'].id]['stream_room']['name'] == 'Stage 1'
        assert by_id[data['m3'].id]['stream_room'] is None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestFilters:
    async def test_filter_by_single_match_id(self, client):
        data = await _seed_basic_data()
        response = await client.get(f'/api/matches?match_id={data["m2"].id}')
        body = response.json()
        assert [m['id'] for m in body] == [data['m2'].id]

    async def test_filter_by_multiple_match_ids(self, client):
        data = await _seed_basic_data()
        response = await client.get(
            f'/api/matches?match_id={data["m1"].id}&match_id={data["m4"].id}'
        )
        body = response.json()
        assert sorted(m['id'] for m in body) == sorted([data['m1'].id, data['m4'].id])

    async def test_filter_by_stream_room_id(self, client):
        data = await _seed_basic_data()
        response = await client.get(f'/api/matches?stream_room_id={data["room1"].id}')
        body = response.json()
        # m1 and m4 are in room1
        assert sorted(m['id'] for m in body) == sorted([data['m1'].id, data['m4'].id])

    async def test_filter_by_multiple_stream_rooms(self, client):
        data = await _seed_basic_data()
        response = await client.get(
            f'/api/matches?stream_room_id={data["room1"].id}'
            f'&stream_room_id={data["room2"].id}'
        )
        body = response.json()
        # m1, m2, m4 — m3 has no room
        assert sorted(m['id'] for m in body) == sorted(
            [data['m1'].id, data['m2'].id, data['m4'].id]
        )

    async def test_filter_by_tournament_id(self, client):
        data = await _seed_basic_data()
        response = await client.get(f'/api/matches?tournament_id={data["t2"].id}')
        body = response.json()
        assert sorted(m['id'] for m in body) == sorted([data['m3'].id, data['m4'].id])

    async def test_filter_by_start_date_inclusive(self, client):
        await _seed_basic_data()
        # 2025-01-02 onward → excludes m1
        response = await client.get('/api/matches?start_date=2025-01-02T00:00:00')
        body = response.json()
        assert len(body) == 3
        for m in body:
            assert m['scheduled_at'] >= '2025-01-02'

    async def test_filter_by_end_date_inclusive(self, client):
        await _seed_basic_data()
        # Up to 2025-01-02 23:59 → m1 and m2 (both before this cutoff).
        # Using a clearly-after cutoff avoids timezone-aware vs naive
        # comparison ambiguity at the boundary.
        response = await client.get('/api/matches?end_date=2025-01-02T23:59:59')
        body = response.json()
        assert len(body) == 2

    async def test_filter_by_date_range(self, client):
        data = await _seed_basic_data()
        response = await client.get(
            '/api/matches?start_date=2025-01-02T00:00:00&end_date=2025-01-03T23:59:59'
        )
        body = response.json()
        assert sorted(m['id'] for m in body) == sorted([data['m2'].id, data['m3'].id])

    async def test_filters_combine_with_and(self, client):
        data = await _seed_basic_data()
        # Tournament 2 AND stream room 1 → only m4.
        response = await client.get(
            f'/api/matches?tournament_id={data["t2"].id}'
            f'&stream_room_id={data["room1"].id}'
        )
        body = response.json()
        assert [m['id'] for m in body] == [data['m4'].id]


# ---------------------------------------------------------------------------
# Limit and the 500 cap
# ---------------------------------------------------------------------------


class TestLimit:
    async def test_default_limit_is_applied(self, client):
        t = await Tournament.create(name='Big')
        for i in range(150):
            await Match.create(
                tournament=t,
                scheduled_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            )
        response = await client.get('/api/matches')
        assert len(response.json()) == 100  # default limit

    async def test_custom_limit_below_cap(self, client):
        t = await Tournament.create(name='Big')
        for i in range(10):
            await Match.create(
                tournament=t,
                scheduled_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            )
        response = await client.get('/api/matches?limit=5')
        assert len(response.json()) == 5

    async def test_limit_above_500_is_rejected(self, client):
        # FastAPI validates ``le=500`` and returns 422 for over-limit values.
        response = await client.get('/api/matches?limit=501')
        assert response.status_code == 422

    async def test_limit_below_1_is_rejected(self, client):
        response = await client.get('/api/matches?limit=0')
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Approved-only filtering for commentators / trackers
#
# The /matches endpoint must expose only approved crew. Filtering happens in
# the route handler (api.get_matches) because Pydantic v2 serializes the
# response via attribute access and never invokes a custom from_orm.
# ---------------------------------------------------------------------------


class TestApprovedOnlyCrew:
    async def test_only_approved_commentators_returned(self, client):
        t = await Tournament.create(name='T')
        match = await Match.create(
            tournament=t,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        approved_user = await User.create(discord_id=1, username='approved')
        unapproved_user = await User.create(discord_id=2, username='unapproved')
        await Commentator.create(match=match, user=approved_user, approved=True)
        await Commentator.create(match=match, user=unapproved_user, approved=False)

        response = await client.get('/api/matches')
        body = response.json()
        commentators = body[0]['commentators']
        assert len(commentators) == 1
        assert commentators[0]['user']['username'] == 'approved'

    async def test_only_approved_trackers_returned(self, client):
        t = await Tournament.create(name='T')
        match = await Match.create(
            tournament=t,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        approved_user = await User.create(discord_id=10, username='approved-tracker')
        unapproved_user = await User.create(discord_id=11, username='unapproved-tracker')
        await Tracker.create(match=match, user=approved_user, approved=True)
        await Tracker.create(match=match, user=unapproved_user, approved=False)

        response = await client.get('/api/matches')
        trackers = response.json()[0]['trackers']
        assert len(trackers) == 1
        assert trackers[0]['user']['username'] == 'approved-tracker'

    async def test_unapproved_commentators_excluded(self, client):
        """Only the approved commentator is returned; the pending one is hidden."""
        t = await Tournament.create(name='T')
        match = await Match.create(
            tournament=t,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        approved_user = await User.create(discord_id=21, username='ok')
        unapproved_user = await User.create(discord_id=22, username='pending')
        await Commentator.create(match=match, user=approved_user, approved=True)
        await Commentator.create(match=match, user=unapproved_user, approved=False)

        response = await client.get('/api/matches')
        commentators = response.json()[0]['commentators']
        assert len(commentators) == 1
        assert commentators[0]['user']['username'] == 'ok'


# ---------------------------------------------------------------------------
# Players and generated seed
# ---------------------------------------------------------------------------


class TestRelatedData:
    async def test_players_are_included(self, client):
        t = await Tournament.create(name='T')
        match = await Match.create(
            tournament=t,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        u1 = await User.create(discord_id=100, username='p1')
        u2 = await User.create(discord_id=101, username='p2')
        await MatchPlayers.create(match=match, user=u1, finish_rank=1)
        await MatchPlayers.create(match=match, user=u2, finish_rank=2)

        response = await client.get('/api/matches')
        players = response.json()[0]['players']
        assert len(players) == 2
        ranks = sorted(p['finish_rank'] for p in players)
        assert ranks == [1, 2]

    async def test_generated_seed_is_included_when_present(self, client):
        t = await Tournament.create(name='T')
        seed = await GeneratedSeeds.create(seed_url='https://example.com/seed/1')
        match = await Match.create(
            tournament=t,
            generated_seed=seed,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        response = await client.get('/api/matches')
        body = response.json()[0]
        assert body['generated_seed']['seed_url'] == 'https://example.com/seed/1'

    async def test_generated_seed_is_none_when_absent(self, client):
        t = await Tournament.create(name='T')
        await Match.create(
            tournament=t,
            scheduled_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        response = await client.get('/api/matches')
        assert response.json()[0]['generated_seed'] is None
