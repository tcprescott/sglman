"""The audit report reads one community's trail and names only its own things."""

from application.services.audit_service import AuditService
from application.tenant_context import tenant_scope
from models import AuditLog, Role, Stage, UserRole
from tests.factories import make_user


async def test_audit_reads_and_names_stay_in_their_community(two_tenants):
    a, b = two_tenants
    staff = await make_user(discord_id=9001, username='staff-a')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=a)
    with tenant_scope(b.id):
        b_stage = await Stage.create(name='B Secret Stage')
    await AuditLog.create(user=staff, tenant_id=b.id, action='match.stage_assigned',
                          details=f'{{"match_id": 1, "stage_id": {b_stage.id}}}')
    await AuditLog.create(user=staff, tenant_id=a.id, action='match.stage_assigned',
                          details=f'{{"match_id": 2, "stage_id": {b_stage.id}}}')
    await AuditLog.create(user=staff, tenant_id=None, action='tenant.created', details='{}')

    with tenant_scope(a.id):
        service = AuditService()
        logs = await service.list_logs(actor=staff)
        assert [log.action for log in logs] == ['match.stage_assigned']
        assert await service.count_logs(actor=staff) == 1
        names = await service.reference_names(actor=staff, details=[{'stage_id': b_stage.id}])
        assert names.stages == {}


async def test_area_and_label_search_filter(two_tenants):
    a, _ = two_tenants
    staff = await make_user(discord_id=9002, username='staff-a2')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=a)
    for action in ('match.stage_assigned', 'profile_nudge.dismissed', 'system_config.updated'):
        await AuditLog.create(user=staff, tenant_id=a.id, action=action, details='{}')

    with tenant_scope(a.id):
        service = AuditService()
        people = await service.list_logs(actor=staff, area='people')
        assert [log.action for log in people] == ['profile_nudge.dismissed']
        by_label = await service.list_logs(actor=staff, search='reminder')
        assert [log.action for log in by_label] == ['profile_nudge.dismissed']
        by_key = await service.list_logs(actor=staff, search='system_config')
        assert [log.action for log in by_key] == ['system_config.updated']
        assert await service.count_logs(actor=staff, area='bogus') == 0

