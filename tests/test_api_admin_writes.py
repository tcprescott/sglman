"""Tests for Phase 4 user/role & tournament admin write endpoints.

Focus: tokens inherit their user's permissions/scope (Staff gates, and a
Tournament Admin token can edit only its own tournament)."""


from models import Role, Tournament, User
from tests.api_helpers import client_for, create_user_token


class TestUserAndRoleWrites:
    async def test_staff_creates_user(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.post('/api/users', json={'username': 'newbie', 'discord_id': 5050})
            assert resp.status_code == 201
            assert resp.json()['username'] == 'newbie'

    async def test_non_staff_cannot_create_user(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/users', json={'username': 'x', 'discord_id': 6060})
            assert resp.status_code == 403

    async def test_self_update_changes_display_name(self, db, app):
        _, raw = await create_user_token(username='me')
        async with client_for(app, raw) as c:
            resp = await c.patch('/api/users/me', json={'display_name': 'Cool Name'})
            assert resp.status_code == 200
            assert resp.json()['display_name'] == 'Cool Name'

    async def test_grant_and_revoke_role(self, db, app):
        _, staff_raw = await create_user_token(username='boss', roles=[Role.STAFF])
        target = await User.create(discord_id=321, username='target')
        async with client_for(app, staff_raw) as c:
            granted = await c.post(f'/api/users/{target.id}/roles', json={'role': 'proctor'})
            assert granted.status_code == 200
            detail = await c.get(f'/api/users/{target.id}')
            assert 'proctor' in detail.json()['roles']

            revoked = await c.delete(f'/api/users/{target.id}/roles/proctor')
            assert revoked.status_code == 204

    async def test_non_staff_cannot_grant_role(self, db, app):
        _, raw = await create_user_token(username='plain')
        target = await User.create(discord_id=999, username='target')
        async with client_for(app, raw) as c:
            resp = await c.post(f'/api/users/{target.id}/roles', json={'role': 'staff'})
            assert resp.status_code == 403


class TestTournamentWrites:
    async def test_staff_crud_tournament(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            created = await c.post('/api/tournaments', json={'name': 'New Cup'})
            assert created.status_code == 201
            tid = created.json()['id']

            updated = await c.patch(f'/api/tournaments/{tid}', json={'name': 'Renamed Cup'})
            assert updated.status_code == 200
            assert updated.json()['name'] == 'Renamed Cup'

            assert (await c.delete(f'/api/tournaments/{tid}')).status_code == 204

    async def test_non_staff_cannot_create_tournament(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            assert (await c.post('/api/tournaments', json={'name': 'X'})).status_code == 403

    async def test_tournament_admin_token_scope(self, db, app):
        """A token inherits its user's Tournament Admin scope: the TA can edit
        their tournament; an unrelated user cannot."""
        _, staff_raw = await create_user_token(username='boss', roles=[Role.STAFF])
        ta_user, ta_raw = await create_user_token(username='ta')
        _, outsider_raw = await create_user_token(username='outsider')
        t = await Tournament.create(name='Cup')

        async with client_for(app, staff_raw) as staff, \
                client_for(app, ta_raw) as ta, \
                client_for(app, outsider_raw) as outsider:
            # Staff grants TA membership.
            added = await staff.post(f'/api/tournaments/{t.id}/admins', json={'user_id': ta_user.id})
            assert added.status_code == 200

            # TA can edit their tournament...
            edited = await ta.patch(f'/api/tournaments/{t.id}', json={'name': 'TA Edit'})
            assert edited.status_code == 200

            # ...but an unrelated user cannot.
            blocked = await outsider.patch(f'/api/tournaments/{t.id}', json={'name': 'Nope'})
            assert blocked.status_code == 403
