"""The enrolment write must stamp the tenant itself.

``TournamentPlayers.tenant`` is a **non-null** FK, and two writes in
``UserService`` used to omit it. On Postgres that is an ``IntegrityError`` —
verified against the dev database before the fix — so the per-user edit dialog's
enrolment path did not work at all.

Three safety nets each missed it, and the third is why this file is unusual:

1. ``tests/conftest.py``'s ``db`` fixture wraps every tenant-scoped model's
   ``.create`` to stamp the ambient tenant when a caller omits it, so no
   DB-backed test could ever fail on an unstamped write. The wrapper is the
   right call for ~700 legacy call sites — but it means a test that wants to
   prove the *production* path stamps has to step around it, which is what
   ``unstamped_creates`` below does.
2. The unit tests mocked ``TournamentPlayers.create`` and asserted set maths
   against ``await_count``; the kwargs were never inspected.
3. ``check_tenant_scoping.py`` only read repository modules. It now reads
   service modules too (writes only).
"""

import pytest
from tortoise.exceptions import IntegrityError
from tortoise.models import Model as TortoiseModel

from application.services.user_service import UserService
from application.tenant_context import tenant_scope
from models import Tenant, Tournament, TournamentPlayers, User


@pytest.fixture
def unstamped_creates(db, monkeypatch):
    """Undo the ``db`` fixture's auto-stamp for ``TournamentPlayers``.

    Restores Tortoise's own ``Model.create``, so a caller that forgets
    ``tenant_id`` gets the production behaviour: a non-null violation. Without
    this, every test in the suite passes whether the write stamps or not.

    Depends on ``db`` so it is always applied *after* the wrapper it undoes.
    """
    monkeypatch.setattr(
        TournamentPlayers, 'create',
        TortoiseModel.__dict__['create'].__get__(None, TournamentPlayers),
    )
    assert getattr(TournamentPlayers.create, '__name__', '') != '_stamped_create', (
        'the db fixture wrapper is still in place — this fixture would do nothing'
    )


async def test_the_harness_really_does_auto_stamp(db):
    """Pin the reason the other tests in the suite cannot catch this.

    If the fixture ever stops stamping, this fails and the note above becomes
    wrong — which is worth knowing, because it would make ~700 call sites start
    failing too.
    """
    tournament = await Tournament.create(name='T')
    user = await User.create(discord_id=5100, username='u')
    row = await TournamentPlayers.create(tournament=tournament, user=user)
    assert row.tenant_id == 1


async def test_enrolment_stamps_the_tenant_without_the_fixtures_help(unstamped_creates):
    """The regression test: this fails against the pre-fix service.

    ``update_user_tournament_registrations`` used to call
    ``TournamentPlayers.create`` directly with no tenant, which raises here
    exactly as it does on Postgres.
    """
    tournament = await Tournament.create(name='T', tenant_id=1)
    user = await User.create(discord_id=5101, username='enrollee')
    actor = await User.create(discord_id=5102, username='boss')

    await UserService().update_user_tournament_registrations(
        user, actor, {tournament.id}, [],
    )
    row = await TournamentPlayers.get(tournament=tournament, user=user)
    assert row.tenant_id == 1


async def test_manage_enrollments_stamps_the_tenant_too(unstamped_creates):
    tournament = await Tournament.create(name='T', tenant_id=1)
    user = await User.create(discord_id=5103, username='enrollee2')
    actor = await User.create(discord_id=5104, username='boss2')

    await UserService().manage_tournament_enrollments(
        user, actor, {tournament.id}, is_update=False,
    )
    row = await TournamentPlayers.get(tournament=tournament, user=user)
    assert row.tenant_id == 1


async def test_an_unstamped_write_really_does_fail(unstamped_creates):
    """The fixture is only meaningful if the unstamped write actually raises.

    Verified against Postgres before the fix ("null value in column tenant_id …
    violates not-null constraint"); this pins the same behaviour in the suite so
    the two tests above cannot pass for the wrong reason.
    """
    tournament = await Tournament.create(name='T', tenant_id=1)
    user = await User.create(discord_id=5105, username='u2')
    with pytest.raises(IntegrityError):
        await TournamentPlayers.create(tournament=tournament, user=user)


async def test_enrolment_rows_do_not_leak_across_tenants(two_tenants, db):
    tenant_a, tenant_b = two_tenants
    user = await User.create(discord_id=5106, username='shared')
    actor = await User.create(discord_id=5107, username='boss3')

    with tenant_scope(tenant_a.id):
        tournament_a = await Tournament.create(name='A')
        await UserService().update_user_tournament_registrations(
            user, actor, {tournament_a.id}, [],
        )

    assert await TournamentPlayers.filter(tenant_id=tenant_a.id).count() == 1
    assert await TournamentPlayers.filter(tenant_id=tenant_b.id).count() == 0

    with tenant_scope(tenant_b.id):
        assert await UserService().get_user_tournament_registrations(user) == []


async def test_enrolment_refuses_a_tournament_in_another_tenant(db):
    """The tenant filter on the load, not just the stamp on the write."""
    other = await Tenant.create(name='Other', slug='other')
    with tenant_scope(other.id):
        elsewhere = await Tournament.create(name='Elsewhere')
    user = await User.create(discord_id=5108, username='u3')
    actor = await User.create(discord_id=5109, username='boss4')

    await UserService().update_user_tournament_registrations(
        user, actor, {elsewhere.id}, [],
    )
    assert await TournamentPlayers.filter(user=user).count() == 0
