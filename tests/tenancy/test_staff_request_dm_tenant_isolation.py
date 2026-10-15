"""Staff request DMs never cross communities.

Request ids are per table, not per tenant, so the same ``(kind, object_id)``
can name a request in two communities. Deciding one must only edit the DMs that
community's staff got.
"""

from application.repositories import StaffRequestDMRepository
from application.tenant_context import tenant_scope
from models import StaffRequestDM, StaffRequestKind
from tests.factories import make_user


async def test_staff_request_dms_do_not_leak_across_tenants(two_tenants):
    a, b = two_tenants
    staff = await make_user(discord_id=760, username='both-staff')
    kind = StaffRequestKind.JOIN_REQUEST
    with tenant_scope(a.id):
        await StaffRequestDMRepository.record(kind, 5, staff.id, 1, 11)
    with tenant_scope(b.id):
        await StaffRequestDMRepository.record(kind, 5, staff.id, 2, 22)
        assert [r.message_id for r in await StaffRequestDMRepository.list_for(kind, 5)] == [22]
        assert await StaffRequestDMRepository.forget(kind, 5) == 1

    with tenant_scope(a.id):
        assert [r.message_id for r in await StaffRequestDMRepository.list_for(kind, 5)] == [11]
    assert await StaffRequestDM.all().count() == 1
