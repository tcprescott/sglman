"""WatchLayoutVote must not leak across tenants: one community's ratings never count in another's."""

from application.services import WatchLayoutService
from application.tenant_context import tenant_scope
from models import Role, User, UserRole


async def test_votes_are_tenant_isolated(two_tenants):
    a, b = two_tenants
    staff = await User.create(discord_id=840, username='staff')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=a)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=b)

    with tenant_scope(a.id):
        await WatchLayoutService().vote('browser', 'tabs', 'up')
    with tenant_scope(b.id):
        assert await WatchLayoutService().votes_for('browser') == {}
        tally = {t.layout: t for t in await WatchLayoutService().tally(staff)}
        assert tally['tabs'].up == 0
    with tenant_scope(a.id):
        tally = {t.layout: t for t in await WatchLayoutService().tally(staff)}
        assert (tally['tabs'].seen, tally['tabs'].up) == (1, 1)
