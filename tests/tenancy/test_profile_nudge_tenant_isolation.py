"""ProfileNudgeDismissal / profile reminder rules stay inside their community."""

from application.services.profile_nudge_service import ProfileNudgeService
from application.tenant_context import tenant_scope
from models import ProfileNudgeDismissal, Role, UserRole
from tests.factories import make_user


async def test_rules_and_dismissals_do_not_leak_between_tenants(two_tenants):
    a, b = two_tenants
    staff = await make_user(discord_id=840, username='leak_staff')
    member = await make_user(discord_id=841, username='leak_member')
    for t in (a, b):
        await UserRole.create(user=staff, role=Role.STAFF, tenant=t)
    service = ProfileNudgeService()
    rule = [{'check': 'pronouns', 'dismissible': True, 'note': None}]

    with tenant_scope(a.id):
        await service.set_rules(staff, rule)
    with tenant_scope(b.id):
        assert await service.get_rules() == []
        assert await service.pending_for(member) == []
        await service.set_rules(staff, rule)

    with tenant_scope(a.id):
        await service.dismiss(member, 'pronouns')
        assert await service.pending_for(member) == []
    with tenant_scope(b.id):
        assert len(await service.pending_for(member)) == 1
        assert await service.repository.dismissed_checks(member.id) == set()

    assert await ProfileNudgeDismissal.filter(tenant_id=a.id).count() == 1
    assert await ProfileNudgeDismissal.filter(tenant_id=b.id).count() == 0
