"""Who sees which qualifiers on the admin list, and the New Qualifier switch.

A per-qualifier reviewer gets the Qualifiers admin tab, and the "runs are
waiting" DM deep-links them into it, so the list has to hold the qualifiers they
review rather than refusing them outright.
"""

import pytest

from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from models import AsyncQualifier, Role, UserRole
from tests.services._async_qualifier_setup import make_player, make_staff

pytestmark = pytest.mark.anyio


async def test_staff_and_qualifier_admin_see_every_qualifier(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    first = await service.create_qualifier(staff, name='First')
    second = await service.create_qualifier(staff, name='Second')
    qa = await make_player(900801, 'qa')
    await UserRole.create(user=qa, role=Role.QUALIFIER_ADMIN, tenant_id=1)

    for actor in (staff, qa):
        listed = {q.id for q in await service.list_qualifiers(actor)}
        assert listed == {first.id, second.id}


async def test_a_reviewer_sees_only_the_qualifiers_they_review(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    mine = await service.create_qualifier(staff, name='Mine')
    await service.create_qualifier(staff, name='Not mine')
    reviewer = await make_player(900802, 'reviewer')
    await service.add_admin(staff, mine.id, reviewer)

    assert [q.id for q in await service.list_qualifiers(reviewer)] == [mine.id]


async def test_someone_who_reviews_nothing_is_refused(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    await service.create_qualifier(staff, name='Q')
    player = await make_player(900803, 'player')

    with pytest.raises(PermissionError):
        await service.list_qualifiers(player)
    with pytest.raises(PermissionError):
        await service.list_qualifiers(None)


async def test_create_honours_the_active_switch(db):
    service = AsyncQualifierService()
    staff = await make_staff()

    off = await service.create_qualifier(staff, name='Off', is_active=False)
    on = await service.create_qualifier(staff, name='On')

    assert (await AsyncQualifier.get(id=off.id)).is_active is False
    assert (await AsyncQualifier.get(id=on.id)).is_active is True
