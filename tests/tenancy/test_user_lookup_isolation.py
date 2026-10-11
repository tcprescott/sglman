"""By-id user routes must not walk the whole platform.

``User`` is global — identity is, deliberately. Belonging to a community is
``TenantMembership``. So a route that takes a ``user_id`` and looks it up bare
reaches every account the platform has, and the caller only has to count
upwards. ``list_users`` was already narrowed for this ("returning the platform's
whole user table was a leak"); these tests hold the by-id routes to the same
line, including the write that clears ``is_active`` — a *global* account
disable, so cross-community reach there locks people out of communities the
actor has nothing to do with.

The refusal is 404, not 403: "no such id" and "not in your community" must read
the same, or the error is a membership oracle.
"""

import pytest

from models import Role, Tenant, TenantMembership, User
from tests.api_helpers import client_for, create_community_member, create_user_token


@pytest.fixture
async def outsider(db):
    """An account that belongs to another community entirely."""
    other = await Tenant.create(name='Elsewhere', slug='elsewhere', is_active=True)
    user = await User.create(discord_id=770001, username='someone-elses-player')
    await TenantMembership.create(user=user, tenant=other)
    return user


class TestReads:
    async def test_staff_cannot_read_a_stranger(self, db, app, outsider):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{outsider.id}')
        assert resp.status_code == 404

    async def test_a_missing_id_and_a_stranger_look_identical(self, db, app, outsider):
        """Otherwise the status code is a membership oracle."""
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            stranger = await c.get(f'/api/users/{outsider.id}')
            missing = await c.get('/api/users/99999')
        assert stranger.status_code == missing.status_code == 404
        assert stranger.json() == missing.json()

    async def test_staff_reads_their_own_community(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        member = await create_community_member(username='ours')
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{member.id}')
        assert resp.status_code == 200
        assert resp.json()['username'] == 'ours'

    async def test_you_can_always_read_yourself(self, db, app):
        user, raw = await create_user_token(username='member')
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{user.id}')
        assert resp.status_code == 200

    async def test_a_token_outliving_its_membership_is_refused(self, db, app):
        """Removal revokes tokens, but one minted before that existed, or by a
        super-admin who has since lost the role, must not keep working."""
        user, raw = await create_user_token(username='loner', member=False)
        assert not await TenantMembership.filter(user=user).exists()
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{user.id}')
        assert resp.status_code == 403

    async def test_super_admin_reads_anyone(self, db, app, outsider):
        _, raw = await create_user_token(username='root', roles=[Role.SUPER_ADMIN])
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{outsider.id}')
        assert resp.status_code == 200

    async def test_availability_of_a_stranger_is_hidden(self, db, app, outsider):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/users/{outsider.id}/availability')
        assert resp.status_code == 404


class TestWrites:
    async def test_staff_cannot_rename_a_stranger(self, db, app, outsider):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.patch(
                f'/api/users/{outsider.id}', json={'display_name': 'Renamed'}
            )
        assert resp.status_code == 404
        await outsider.refresh_from_db()
        assert outsider.display_name != 'Renamed'

    async def test_staff_cannot_deactivate_a_stranger(self, db, app, outsider):
        """The sharp one: is_active is a platform-wide account disable."""
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.patch(
                f'/api/users/{outsider.id}/admin', json={'is_active': False}
            )
        assert resp.status_code == 404
        await outsider.refresh_from_db()
        assert outsider.is_active is True

    async def test_granting_a_role_still_reaches_a_newcomer(self, db, app, outsider):
        """The deliberate exception: a grant is how someone joins.

        ``grant_role`` calls ``ensure_member``, so scoping this one to existing
        members would make the first grant impossible.
        """
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.post(
                f'/api/users/{outsider.id}/roles', json={'role': 'proctor'}
            )
        assert resp.status_code == 200, resp.text
        assert await TenantMembership.filter(user=outsider, tenant_id=1).exists()

    async def test_adding_a_stranger_does_not_unlock_their_account(self, db, app, outsider):
        """Membership is no limit on global fields, since staff can add anyone:
        grant a role, and the 404 above used to become a platform-wide lockout."""
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            await c.post(f'/api/users/{outsider.id}/roles', json={'role': 'volunteer'})
            deactivate = await c.patch(
                f'/api/users/{outsider.id}/admin', json={'is_active': False},
            )
            rename = await c.patch(
                f'/api/users/{outsider.id}', json={'display_name': 'Impostor'},
            )
        assert deactivate.status_code == 403
        assert 'another community' in deactivate.json()['detail']
        assert rename.status_code == 403
        await outsider.refresh_from_db()
        assert outsider.is_active is True
        assert outsider.display_name != 'Impostor'

    async def test_community_staff_cannot_deactivate_a_super_admin(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        admin, _ = await create_user_token(username='platform', roles=[Role.SUPER_ADMIN])
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/users/{admin.id}/admin', json={'is_active': False})
        assert resp.status_code == 403
        assert 'platform admin' in resp.json()['detail']
        await admin.refresh_from_db()
        assert admin.is_active is True

    async def test_staff_still_manage_someone_who_is_only_theirs(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        member = await create_community_member(username='ours-only')
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/users/{member.id}/admin', json={'is_active': False})
        assert resp.status_code == 200, resp.text
        await member.refresh_from_db()
        assert member.is_active is False

    async def test_a_super_admin_may_deactivate_anyone(self, db, app, outsider):
        _, raw = await create_user_token(username='platform', roles=[Role.SUPER_ADMIN])
        await TenantMembership.create(user=outsider, tenant_id=1)
        async with client_for(app, raw) as c:
            resp = await c.patch(f'/api/users/{outsider.id}/admin', json={'is_active': False})
        assert resp.status_code == 200, resp.text
