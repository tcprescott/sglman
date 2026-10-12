"""TenantLogo must not leak across tenants.

The image route runs with no community bound and takes the tenant from the URL,
so the read is keyed on tenant *and* hash: another community's id with the right
hash finds nothing. Writes are scoped like any other, so one community removing
its logo leaves the other's alone.
"""

from io import BytesIO

from PIL import Image

from application.services import tenant_logo_service
from application.services.tenant_logo_service import TenantLogoService
from application.services.tenant_theme_service import TenantThemeService
from application.tenant_context import tenant_scope
from models import Role, TenantLogo, User, UserRole


def _png() -> bytes:
    out = BytesIO()
    Image.new('RGBA', (128, 128), (10, 20, 30, 255)).save(out, 'PNG')
    return out.getvalue()


async def test_logo_is_tenant_isolated(two_tenants):
    a, b = two_tenants
    tenant_logo_service._cache.clear()
    staff = await User.create(discord_id=830, username='staff')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=a)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=b)

    with tenant_scope(a.id):
        await TenantLogoService.set_logo(staff, _png())
    sha = (await TenantLogo.get(tenant_id=a.id)).sha256

    assert await TenantLogoService.get_logo_bytes(a.id, sha)
    assert await TenantLogoService.get_logo_bytes(b.id, sha) is None
    assert 'logo' not in await TenantThemeService.get_theme(b.id)

    with tenant_scope(b.id):
        await TenantLogoService.remove_logo(staff)
    assert await TenantLogo.exists(tenant_id=a.id)
    assert 'logo' in await TenantThemeService.get_theme(a.id)
