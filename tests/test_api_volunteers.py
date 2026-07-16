"""REST API tests for the volunteer scheduling endpoints (api/routers/volunteers.py).

Covers positions, shifts, assignments, coverage, and the self-service
profile / availability / assignments endpoints. Each mutating route is checked
for a success path (with the right role), a 403 for the wrong role or a
read-only token, and 400/404 where the service or router rejects input.
"""

from datetime import datetime, timezone

import pytest

from models import (
    Role,
    User,
    VolunteerAssignment,
    VolunteerPosition,
    VolunteerShift,
)
from tests.api_helpers import build_api_app, client_for, create_user_token

UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def iso(y, mo, d, h=0, mi=0):
    return utc(y, mo, d, h, mi).isoformat()


@pytest.fixture(autouse=True)
def stub_discord_queue(monkeypatch):
    captured = []
    monkeypatch.setattr('application.services.discord_queue.enqueue', captured.append)
    yield captured
    for coro in captured:
        coro.close()


@pytest.fixture
def app():
    return build_api_app()


async def _coordinator_token(username='coord'):
    return await create_user_token(username=username, roles=[Role.VOLUNTEER_COORDINATOR])


# --- Positions ------------------------------------------------------------

class TestPositions:
    async def test_list_positions_all_and_active_only(self, db, app):
        _, raw = await create_user_token(username='reader', read_only=True)
        await VolunteerPosition.create(name='Active Desk', is_active=True)
        await VolunteerPosition.create(name='Retired Desk', is_active=False)
        async with client_for(app, raw) as c:
            all_resp = await c.get('/api/volunteers/positions')
            assert all_resp.status_code == 200
            assert {p['name'] for p in all_resp.json()} == {'Active Desk', 'Retired Desk'}

            active_resp = await c.get('/api/volunteers/positions', params={'active_only': 'true'})
            assert active_resp.status_code == 200
            assert [p['name'] for p in active_resp.json()] == ['Active Desk']

    async def test_create_position_success(self, db, app):
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/positions', json={'name': 'Check-in', 'color': '#abc'})
            assert resp.status_code == 201
            body = resp.json()
            assert body['name'] == 'Check-in'
            assert body['is_active'] is True

    async def test_create_position_forbidden_for_plain_user(self, db, app):
        """Service raises PermissionError -> 403 for a non-coordinator."""
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/positions', json={'name': 'X'})
            assert resp.status_code == 403

    async def test_create_position_read_only_token_forbidden(self, db, app):
        _, raw = await create_user_token(username='coord', roles=[Role.VOLUNTEER_COORDINATOR], read_only=True)
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/positions', json={'name': 'X'})
            assert resp.status_code == 403

    async def test_create_position_duplicate_name_bad_request(self, db, app):
        _, raw = await _coordinator_token()
        await VolunteerPosition.create(name='Dupe')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/positions', json={'name': 'Dupe'})
            assert resp.status_code == 400

    async def test_create_position_invalid_stagger_bad_request(self, db, app):
        """Stagger interval exceeding the shift length is rejected."""
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.post(
                '/api/volunteers/positions',
                json={'name': 'Rolling', 'shift_length_minutes': 30, 'stagger_minutes': 60},
            )
            assert resp.status_code == 400

    async def test_update_position_success(self, db, app):
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Old Name')
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/volunteers/positions/{pos.id}', json={'name': 'New Name'})
            assert resp.status_code == 200
            assert resp.json()['name'] == 'New Name'

    async def test_update_position_no_fields_returns_unchanged(self, db, app):
        """Empty patch body short-circuits and returns the position untouched."""
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Steady')
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/volunteers/positions/{pos.id}', json={})
            assert resp.status_code == 200
            assert resp.json()['name'] == 'Steady'

    async def test_update_position_not_found(self, db, app):
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.patch('/api/volunteers/positions/9999', json={'name': 'Nope'})
            assert resp.status_code == 404

    async def test_update_position_duplicate_name_bad_request(self, db, app):
        _, raw = await _coordinator_token()
        await VolunteerPosition.create(name='Taken')
        pos = await VolunteerPosition.create(name='Mine')
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/volunteers/positions/{pos.id}', json={'name': 'Taken'})
            assert resp.status_code == 400

    async def test_delete_position_success(self, db, app):
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Temp')
        async with client_for(app, raw) as c:
            resp = await c.delete(f'/api/volunteers/positions/{pos.id}')
            assert resp.status_code == 204
        assert await VolunteerPosition.get_or_none(id=pos.id) is None

    async def test_delete_position_not_found(self, db, app):
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.delete('/api/volunteers/positions/9999')
            assert resp.status_code == 404


# --- Shifts ---------------------------------------------------------------

class TestShifts:
    async def test_list_shifts_in_window(self, db, app):
        _, raw = await create_user_token(username='reader')
        pos = await VolunteerPosition.create(name='Desk')
        await VolunteerShift.create(position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16))
        async with client_for(app, raw) as c:
            resp = await c.get(
                '/api/volunteers/shifts',
                params={'start': iso(2025, 10, 1), 'end': iso(2025, 10, 31)},
            )
            assert resp.status_code == 200
            rows = resp.json()
            assert len(rows) == 1
            assert rows[0]['position_name'] == 'Desk'
            assert rows[0]['filled'] == 0

    async def test_get_shift_success(self, db, app):
        _, raw = await create_user_token(username='reader')
        pos = await VolunteerPosition.create(name='Desk')
        shift = await VolunteerShift.create(
            position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16), label='Morning',
        )
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/volunteers/shifts/{shift.id}')
            assert resp.status_code == 200
            assert resp.json()['label'] == 'Morning'

    async def test_get_shift_not_found(self, db, app):
        _, raw = await create_user_token(username='reader')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/volunteers/shifts/9999')
            assert resp.status_code == 404

    async def test_create_shift_success(self, db, app):
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Desk')
        async with client_for(app, raw) as c:
            resp = await c.post(
                '/api/volunteers/shifts',
                json={
                    'position_id': pos.id,
                    'starts_at': iso(2025, 10, 8, 12),
                    'ends_at': iso(2025, 10, 8, 16),
                    'slots_needed': 2,
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body['position_id'] == pos.id
            assert body['slots_needed'] == 2

    async def test_create_shift_end_before_start_bad_request(self, db, app):
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Desk')
        async with client_for(app, raw) as c:
            resp = await c.post(
                '/api/volunteers/shifts',
                json={
                    'position_id': pos.id,
                    'starts_at': iso(2025, 10, 8, 16),
                    'ends_at': iso(2025, 10, 8, 12),
                },
            )
            assert resp.status_code == 400

    async def test_create_shift_forbidden_for_plain_user(self, db, app):
        _, raw = await create_user_token(username='plain')
        pos = await VolunteerPosition.create(name='Desk')
        async with client_for(app, raw) as c:
            resp = await c.post(
                '/api/volunteers/shifts',
                json={
                    'position_id': pos.id,
                    'starts_at': iso(2025, 10, 8, 12),
                    'ends_at': iso(2025, 10, 8, 16),
                },
            )
            assert resp.status_code == 403

    async def test_delete_shift_success(self, db, app):
        _, raw = await _coordinator_token()
        pos = await VolunteerPosition.create(name='Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16))
        async with client_for(app, raw) as c:
            resp = await c.delete(f'/api/volunteers/shifts/{shift.id}')
            assert resp.status_code == 204
        assert await VolunteerShift.get_or_none(id=shift.id) is None

    async def test_delete_shift_not_found(self, db, app):
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.delete('/api/volunteers/shifts/9999')
            assert resp.status_code == 404


# --- Assignments ----------------------------------------------------------

class TestAssignments:
    async def _shift(self, slots_needed=1):
        pos = await VolunteerPosition.create(name='Desk')
        return await VolunteerShift.create(
            position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16),
            slots_needed=slots_needed,
        )

    async def test_assign_success_no_warnings(self, db, app):
        _, raw = await _coordinator_token()
        target = await User.create(discord_id=555, username='vol', dm_notifications=False)
        shift = await self._shift(slots_needed=2)
        async with client_for(app, raw) as c:
            resp = await c.post(
                f'/api/volunteers/shifts/{shift.id}/assignments', json={'user_id': target.id},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body['assignment']['user_id'] == target.id
            assert body['assignment']['user_name'] == 'vol'
            assert body['warnings'] == []

    async def test_assign_overfilled_returns_warning(self, db, app):
        """A second assignment past slots_needed succeeds but reports a warning."""
        _, raw = await _coordinator_token()
        shift = await self._shift(slots_needed=1)
        first = await User.create(discord_id=1001, username='first', dm_notifications=False)
        second = await User.create(discord_id=1002, username='second', dm_notifications=False)
        await VolunteerAssignment.create(shift=shift, user=first)
        async with client_for(app, raw) as c:
            resp = await c.post(
                f'/api/volunteers/shifts/{shift.id}/assignments', json={'user_id': second.id},
            )
            assert resp.status_code == 200
            assert resp.json()['warnings']

    async def test_assign_duplicate_bad_request(self, db, app):
        _, raw = await _coordinator_token()
        shift = await self._shift()
        target = await User.create(discord_id=2001, username='vol', dm_notifications=False)
        await VolunteerAssignment.create(shift=shift, user=target)
        async with client_for(app, raw) as c:
            resp = await c.post(
                f'/api/volunteers/shifts/{shift.id}/assignments', json={'user_id': target.id},
            )
            assert resp.status_code == 400

    async def test_assign_shift_not_found(self, db, app):
        _, raw = await _coordinator_token()
        target = await User.create(discord_id=3001, username='vol')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/shifts/9999/assignments', json={'user_id': target.id})
            assert resp.status_code == 404

    async def test_assign_user_not_found(self, db, app):
        _, raw = await _coordinator_token()
        shift = await self._shift()
        async with client_for(app, raw) as c:
            resp = await c.post(f'/api/volunteers/shifts/{shift.id}/assignments', json={'user_id': 9999})
            assert resp.status_code == 404

    async def test_assign_forbidden_for_plain_user(self, db, app):
        _, raw = await create_user_token(username='plain')
        shift = await self._shift()
        target = await User.create(discord_id=4001, username='vol')
        async with client_for(app, raw) as c:
            resp = await c.post(
                f'/api/volunteers/shifts/{shift.id}/assignments', json={'user_id': target.id},
            )
            assert resp.status_code == 403

    async def test_unassign_success(self, db, app):
        _, raw = await _coordinator_token()
        shift = await self._shift()
        target = await User.create(discord_id=5001, username='vol')
        assignment = await VolunteerAssignment.create(shift=shift, user=target)
        async with client_for(app, raw) as c:
            resp = await c.delete(f'/api/volunteers/assignments/{assignment.id}')
            assert resp.status_code == 204
        assert await VolunteerAssignment.get_or_none(id=assignment.id) is None

    async def test_unassign_not_found(self, db, app):
        _, raw = await _coordinator_token()
        async with client_for(app, raw) as c:
            resp = await c.delete('/api/volunteers/assignments/9999')
            assert resp.status_code == 404

    async def test_acknowledge_success(self, db, app):
        volunteer, raw = await create_user_token(username='vol')
        pos = await VolunteerPosition.create(name='Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16))
        assignment = await VolunteerAssignment.create(shift=shift, user=volunteer)
        async with client_for(app, raw) as c:
            resp = await c.post(f'/api/volunteers/assignments/{assignment.id}/acknowledge')
            assert resp.status_code == 200
            assert resp.json()['acknowledged_at'] is not None

    async def test_acknowledge_not_found(self, db, app):
        """acknowledge on a missing assignment raises NotFoundError -> 404 (audit §2B.6)."""
        _, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/assignments/9999/acknowledge')
            assert resp.status_code == 404

    async def test_acknowledge_other_users_assignment_bad_request(self, db, app):
        owner = await User.create(discord_id=6001, username='owner')
        _, raw = await create_user_token(username='intruder')
        pos = await VolunteerPosition.create(name='Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16))
        assignment = await VolunteerAssignment.create(shift=shift, user=owner)
        async with client_for(app, raw) as c:
            resp = await c.post(f'/api/volunteers/assignments/{assignment.id}/acknowledge')
            assert resp.status_code == 400


# --- Coverage -------------------------------------------------------------

class TestCoverage:
    async def test_coverage_reports_understaffed(self, db, app):
        _, raw = await create_user_token(username='reader')
        pos = await VolunteerPosition.create(name='Desk')
        shift = await VolunteerShift.create(
            position=pos, starts_at=utc(2025, 10, 8, 12), ends_at=utc(2025, 10, 8, 16),
            slots_needed=2, label='AM',
        )
        one = await User.create(discord_id=7001, username='one')
        await VolunteerAssignment.create(shift=shift, user=one)
        async with client_for(app, raw) as c:
            resp = await c.get(
                '/api/volunteers/coverage',
                params={'start': iso(2025, 10, 1), 'end': iso(2025, 10, 31)},
            )
            assert resp.status_code == 200
            rows = resp.json()
            assert len(rows) == 1
            row = rows[0]
            assert row['filled'] == 1
            assert row['needed'] == 2
            assert row['understaffed'] is True
            assert row['position'] == 'Desk'


# --- Self-service ---------------------------------------------------------

class TestSelfService:
    async def test_get_profile_creates_opted_out_profile(self, db, app):
        actor, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/volunteers/me/profile')
            assert resp.status_code == 200
            body = resp.json()
            assert body['user_id'] == actor.id
            assert body['opted_in'] is False

    async def test_opt_in_then_opt_out(self, db, app):
        _, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            in_resp = await c.post('/api/volunteers/me/opt-in', json={'note': 'ready to help'})
            assert in_resp.status_code == 200
            in_body = in_resp.json()
            assert in_body['opted_in'] is True
            assert in_body['note'] == 'ready to help'

            out_resp = await c.post('/api/volunteers/me/opt-out')
            assert out_resp.status_code == 200
            assert out_resp.json()['opted_in'] is False

    async def test_opt_in_read_only_token_forbidden(self, db, app):
        _, raw = await create_user_token(username='vol', read_only=True)
        async with client_for(app, raw) as c:
            resp = await c.post('/api/volunteers/me/opt-in', json={})
            assert resp.status_code == 403

    async def test_get_availability_empty(self, db, app):
        _, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/volunteers/me/availability')
            assert resp.status_code == 200
            assert resp.json() == []

    async def test_set_availability_success_after_opt_in(self, db, app):
        actor, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            await c.post('/api/volunteers/me/opt-in', json={})
            put = await c.put(
                '/api/volunteers/me/availability',
                json={'windows': [{
                    'starts_at': iso(2025, 10, 8, 10),
                    'ends_at': iso(2025, 10, 8, 14),
                    'status': 'preferred',
                    'note': 'mornings',
                }]},
            )
            assert put.status_code == 200
            rows = put.json()
            assert len(rows) == 1
            assert rows[0]['status'] == 'preferred'
            assert rows[0]['user_id'] == actor.id

            listed = await c.get('/api/volunteers/me/availability')
            assert len(listed.json()) == 1

    async def test_set_availability_without_opt_in_bad_request(self, db, app):
        _, raw = await create_user_token(username='vol')
        async with client_for(app, raw) as c:
            put = await c.put(
                '/api/volunteers/me/availability',
                json={'windows': [{
                    'starts_at': iso(2025, 10, 8, 10),
                    'ends_at': iso(2025, 10, 8, 14),
                }]},
            )
            assert put.status_code == 400

    async def test_set_availability_read_only_token_forbidden(self, db, app):
        _, raw = await create_user_token(username='vol', read_only=True)
        async with client_for(app, raw) as c:
            put = await c.put('/api/volunteers/me/availability', json={'windows': []})
            assert put.status_code == 403

    async def test_my_assignments_upcoming_only_and_all(self, db, app):
        actor, raw = await create_user_token(username='vol')
        pos = await VolunteerPosition.create(name='Desk')
        future_shift = await VolunteerShift.create(
            position=pos, starts_at=utc(2030, 1, 1, 12), ends_at=utc(2030, 1, 1, 16),
        )
        past_shift = await VolunteerShift.create(
            position=pos, starts_at=utc(2020, 1, 1, 12), ends_at=utc(2020, 1, 1, 16),
        )
        await VolunteerAssignment.create(shift=future_shift, user=actor)
        await VolunteerAssignment.create(shift=past_shift, user=actor)
        async with client_for(app, raw) as c:
            upcoming = await c.get('/api/volunteers/me/assignments')
            assert upcoming.status_code == 200
            assert len(upcoming.json()) == 1

            everything = await c.get('/api/volunteers/me/assignments', params={'upcoming_only': 'false'})
            assert everything.status_code == 200
            assert len(everything.json()) == 2
