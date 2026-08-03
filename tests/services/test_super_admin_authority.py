"""Super-admin in-tenant authority, and the Volunteer nav's access gate.

Two guarantees, which pull in opposite directions and so are tested together:

1. A ``SUPER_ADMIN`` has **full authority inside every tenant** — including a
   tenant they hold no roles in — because ``AuthService.is_staff`` treats the
   global role as staff-equivalent and is the override term in every ``can_*``.
2. Authority stops at the **feature flag**. A subsystem the community has not
   turned on stays hidden from the super-admin too, so they can never operate a
   feature the tenant has not enabled.

``can_view_volunteer`` is where both meet: it is the nav's single source of truth
and must agree with the ``@protected_tab_page('/volunteer')`` gate.
"""

import pytest

from application.services.auth_service import AuthService
from application.tenant_context import tenant_scope
from models import FeatureFlag, Role, Tenant, TenantFeatureFlag, Tournament, User, UserRole


@pytest.fixture
async def fresh_tenant(db):
    """A brand-new tenant: no flag rows (all features off), no role grants."""
    return await Tenant.create(name='Fresh', slug='fresh')


@pytest.fixture
async def super_admin(db):
    user = await User.create(discord_id=90001, username='platform-owner')
    await UserRole.create(user=user, role=Role.SUPER_ADMIN, tenant=None)
    return user


@pytest.fixture
async def nobody(db):
    """Signed in, but holds no role anywhere."""
    return await User.create(discord_id=90002, username='nobody')


async def _enable(tenant_id: int, flag: FeatureFlag) -> None:
    await TenantFeatureFlag.create(
        tenant_id=tenant_id, flag=flag.value, available=True, enabled=True,
    )


# --- 1. authority carries into a tenant with no grants ----------------------

async def test_is_staff_true_for_super_admin_in_a_tenant_they_have_no_roles_in(
    super_admin, fresh_tenant,
):
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.is_staff(super_admin) is True


async def test_get_roles_stays_literal_for_super_admin(super_admin, fresh_tenant):
    """Staff-*equivalence* must not fabricate a STAFF grant: role-management UI
    reads ``get_roles``/``has_role`` and would otherwise show a role nobody granted."""
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.get_roles(super_admin) == set()
        assert await AuthService.has_role(super_admin, Role.STAFF) is False


@pytest.mark.parametrize('helper', [
    'can_manage_volunteers',
    'can_manage_stages',
    'can_manage_equipment',
    'can_checkin_equipment',
    'can_manage_presets',
    'can_manage_sync',
    'can_grant_roles',
    'can_view_admin',
])
async def test_gated_helpers_grant_super_admin_in_a_foreign_tenant(
    super_admin, nobody, fresh_tenant, helper,
):
    with tenant_scope(fresh_tenant.id):
        assert await getattr(AuthService, helper)(super_admin) is True
        # Same call, ordinary user: proves the fixture tenant really grants nothing.
        assert await getattr(AuthService, helper)(nobody) is False


async def test_borrowing_is_deliberately_not_role_gated(nobody, fresh_tenant):
    """``can_checkout_equipment`` is absent from the list above on purpose: a
    loaner's QR code is scanned by whoever holds it, so borrowing to yourself is
    open to any signed-in member. Lending *on behalf of* someone else is the
    gated action, and it is ``can_manage_equipment`` that gates it."""
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.can_checkout_equipment(nobody) is True
        assert await AuthService.can_checkout_equipment(None) is False


async def test_super_admin_may_edit_and_crud_another_tenants_tournament(
    super_admin, nobody, fresh_tenant,
):
    with tenant_scope(fresh_tenant.id):
        tournament = await Tournament.create(name='Fresh Cup', tenant_id=fresh_tenant.id)
        assert await AuthService.can_edit_tournament(super_admin, tournament) is True
        assert await AuthService.can_edit_tournament(nobody, tournament) is False


# --- 2. authority does not bypass feature flags -----------------------------

async def test_can_view_volunteer_false_for_super_admin_when_feature_off(
    super_admin, fresh_tenant,
):
    """The regression this suite exists for: the header offered every signed-in
    user a Volunteer link, which 404s where the tenant has the feature off."""
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.can_view_volunteer(super_admin) is False


async def test_can_view_volunteer_true_for_super_admin_once_feature_enabled(
    super_admin, fresh_tenant,
):
    await _enable(fresh_tenant.id, FeatureFlag.VOLUNTEERS)
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.can_view_volunteer(super_admin) is True


@pytest.mark.parametrize('role,expected', [
    (Role.VOLUNTEER, True),
    (Role.PROCTOR, True),
    (Role.STAFF, True),
    (Role.EQUIPMENT_MANAGER, False),
    (None, False),
])
async def test_can_view_volunteer_matches_the_pages_role_gate(
    db, fresh_tenant, role, expected,
):
    """Mirrors ``roles=[VOLUNTEER, PROCTOR, STAFF]`` on the page decorator — an
    unrelated admin role must not surface the link, or it dead-ends on a 403."""
    await _enable(fresh_tenant.id, FeatureFlag.VOLUNTEERS)
    user = await User.create(discord_id=91000, username='u')
    if role is not None:
        await UserRole.create(user=user, role=role, tenant_id=fresh_tenant.id)
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.can_view_volunteer(user) is expected


async def test_can_view_volunteer_false_when_signed_out():
    assert await AuthService.can_view_volunteer(None) is False


async def test_volunteer_role_in_another_tenant_does_not_surface_the_link(
    db, fresh_tenant,
):
    other = await Tenant.create(name='Other', slug='other')
    await _enable(fresh_tenant.id, FeatureFlag.VOLUNTEERS)
    await _enable(other.id, FeatureFlag.VOLUNTEERS)
    user = await User.create(discord_id=91999, username='vol-elsewhere')
    await UserRole.create(user=user, role=Role.VOLUNTEER, tenant_id=other.id)
    with tenant_scope(fresh_tenant.id):
        assert await AuthService.can_view_volunteer(user) is False
    with tenant_scope(other.id):
        assert await AuthService.can_view_volunteer(user) is True
