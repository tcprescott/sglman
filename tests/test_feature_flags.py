"""Feature-flag system tests: registry, two-tier semantics, and isolation.

The ``db`` fixture pre-seeds the default tenant (id 1) with every flag fully on
(see conftest), so these tests exercise the OFF/partial states under freshly
created tenants that start with no flag rows — a missing row is the
disabled-by-default posture.
"""

import pytest

from application.feature_flags import FEATURE_FLAG_REGISTRY, established_flags
from application.repositories.feature_flag_repository import TenantFeatureFlagRepository
from application.services.feature_flag_service import FeatureFlagService
from application.tenant_context import reset_tenant_id, set_tenant_id, tenant_scope
from models import AuditLog, FeatureFlag, Role, Tenant, TenantFeatureFlag, User, UserRole


@pytest.fixture
async def tenants(db):
    """(tenant_a, tenant_b). A is the pre-seeded default (all flags on); B is fresh (no rows)."""
    a = await Tenant.get(id=1)
    b = await Tenant.create(name='Tenant B', slug='tenant-b')
    return a, b


async def _staff(discord_id: int, tenant_id: int) -> User:
    user = await User.create(discord_id=discord_id, username=f'u{discord_id}')
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=tenant_id)
    return user


async def _super_admin(discord_id: int) -> User:
    user = await User.create(discord_id=discord_id, username=f'sa{discord_id}')
    await UserRole.create(user=user, role=Role.SUPER_ADMIN, tenant=None)
    return user


async def _flag(tenant_id: int, flag: FeatureFlag, *, available: bool, enabled: bool) -> None:
    await TenantFeatureFlag.create(
        tenant_id=tenant_id, flag=flag.value, available=available, enabled=enabled,
    )


# --- registry ---------------------------------------------------------------

def test_registry_covers_every_flag():
    assert len(FEATURE_FLAG_REGISTRY) == 7
    assert set(FEATURE_FLAG_REGISTRY) == set(FeatureFlag)


def test_established_flags_are_the_in_use_features():
    assert set(established_flags()) == {
        FeatureFlag.CHALLONGE, FeatureFlag.EQUIPMENT,
        FeatureFlag.VOLUNTEERS, FeatureFlag.TRIFORCE_TEXTS,
    }
    # New/unreleased features ship dark (not established).
    assert FeatureFlag.ASYNC_QUALIFIERS not in established_flags()
    assert FeatureFlag.RACETIME_ROOMS not in established_flags()


# --- effective state: available AND enabled ---------------------------------

async def test_missing_row_is_off(tenants):
    a, b = tenants
    svc = FeatureFlagService()
    with tenant_scope(b.id):
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is False
        assert await svc.enabled_flags() == set()


async def test_available_but_not_enabled_is_off(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=False)
        assert await FeatureFlagService().is_enabled(FeatureFlag.EQUIPMENT) is False


async def test_available_and_enabled_is_on(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=True)
        svc = FeatureFlagService()
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is True
        assert FeatureFlag.EQUIPMENT in await svc.enabled_flags()


async def test_enabled_without_available_is_off(tenants):
    """Defensive: a stray enabled=True/available=False row still reads off."""
    a, b = tenants
    with tenant_scope(b.id):
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=False, enabled=True)
        assert await FeatureFlagService().is_enabled(FeatureFlag.EQUIPMENT) is False


async def test_off_tenant_reads_disabled(db):
    """No tenant in scope (the platform surface) → off, never a raise."""
    token = set_tenant_id(None)
    try:
        assert await FeatureFlagService().is_enabled(FeatureFlag.EQUIPMENT) is False
        assert await FeatureFlagService().enabled_flags() == set()
    finally:
        reset_tenant_id(token)


# --- ensure_enabled (service guard) -----------------------------------------

async def test_ensure_enabled_raises_when_off(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        with pytest.raises(ValueError):
            await FeatureFlagService().ensure_enabled(FeatureFlag.EQUIPMENT)


async def test_ensure_enabled_passes_when_on(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=True)
        await FeatureFlagService().ensure_enabled(FeatureFlag.EQUIPMENT)  # no raise


# --- tenant tier: STAFF toggles enabled within availability -----------------

async def test_set_tenant_enabled_requires_availability(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        staff = await _staff(5001, b.id)
        with pytest.raises(ValueError):
            await FeatureFlagService().set_tenant_enabled(staff, FeatureFlag.EQUIPMENT, True)


async def test_set_tenant_enabled_toggles_when_available(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        staff = await _staff(5002, b.id)
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=False)
        svc = FeatureFlagService()
        await svc.set_tenant_enabled(staff, FeatureFlag.EQUIPMENT, True)
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is True
        await svc.set_tenant_enabled(staff, FeatureFlag.EQUIPMENT, False)
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is False


async def test_set_tenant_enabled_requires_staff(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        nonstaff = await User.create(discord_id=5003, username='ns')
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=False)
        with pytest.raises(PermissionError):
            await FeatureFlagService().set_tenant_enabled(nonstaff, FeatureFlag.EQUIPMENT, True)


async def test_set_tenant_enabled_writes_audit(tenants):
    a, b = tenants
    with tenant_scope(b.id):
        staff = await _staff(5006, b.id)
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=False)
        await FeatureFlagService().set_tenant_enabled(staff, FeatureFlag.EQUIPMENT, True)
        rows = await AuditLog.filter(tenant_id=b.id, action='feature_flag.enabled')
        assert len(rows) == 1


# --- platform tier: super-admin grants availability -------------------------

async def test_set_availability_requires_super_admin(tenants):
    a, b = tenants
    staff = await _staff(5004, b.id)  # tenant staff is NOT a super-admin
    with pytest.raises(PermissionError):
        await FeatureFlagService().set_availability(staff, b.id, FeatureFlag.EQUIPMENT, True)


async def test_super_admin_grants_availability_without_enabling(tenants):
    a, b = tenants
    sa = await _super_admin(5005)
    await FeatureFlagService().set_availability(sa, b.id, FeatureFlag.ASYNC_QUALIFIERS, True)
    row = await TenantFeatureFlagRepository.get_for_tenant(b.id, 'async_qualifiers')
    assert row is not None and row.available is True and row.enabled is False
    # Available but not yet enabled → still off for users.
    with tenant_scope(b.id):
        assert await FeatureFlagService().is_enabled(FeatureFlag.ASYNC_QUALIFIERS) is False


async def test_revoking_availability_preserves_enabled_choice(tenants):
    a, b = tenants
    sa = await _super_admin(5007)
    await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=True)
    await FeatureFlagService().set_availability(sa, b.id, FeatureFlag.EQUIPMENT, False)
    row = await TenantFeatureFlagRepository.get_for_tenant(b.id, 'equipment')
    # enabled untouched, but effective is off because available is now False.
    assert row.enabled is True and row.available is False
    with tenant_scope(b.id):
        assert await FeatureFlagService().is_enabled(FeatureFlag.EQUIPMENT) is False


# --- isolation --------------------------------------------------------------

async def test_flags_do_not_leak_across_tenants(db):
    b = await Tenant.create(name='B', slug='tb')
    c = await Tenant.create(name='C', slug='tc')
    with tenant_scope(b.id):
        await _flag(b.id, FeatureFlag.EQUIPMENT, available=True, enabled=True)
    svc = FeatureFlagService()
    with tenant_scope(b.id):
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is True
    with tenant_scope(c.id):
        # C never had a row — B's flag must not bleed across.
        assert await svc.is_enabled(FeatureFlag.EQUIPMENT) is False
        assert await svc.enabled_flags() == set()
