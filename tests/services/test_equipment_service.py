import pytest

from application.services.equipment_service import EquipmentService
from application.tenant_context import tenant_scope
from models import Equipment, EquipmentLoan, EquipmentStatus, Role, User, UserRole


async def _user(discord_id: int, username: str, *roles: Role) -> User:
    user = await User.create(discord_id=discord_id, username=username)
    for role in roles:
        await UserRole.create(user=user, role=role)
    return user


@pytest.fixture
def service():
    return EquipmentService()


class TestAssetNumbering:
    async def test_assigns_sequential_numbers(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        a = await service.create_asset(manager, name='Console')
        b = await service.create_asset(manager, name='Capture card')
        assert a.asset_number == 1
        assert b.asset_number == 2

    async def test_bulk_create_contiguous_range(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        await service.create_asset(manager, name='Cable')  # number 1
        created = await service.bulk_create_assets(manager, name='HDMI', count=5)
        numbers = sorted(a.asset_number for a in created)
        assert numbers == [2, 3, 4, 5, 6]
        assert await Equipment.all().count() == 6

    async def test_bulk_count_bounds(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        with pytest.raises(ValueError):
            await service.bulk_create_assets(manager, name='X', count=0)
        with pytest.raises(ValueError):
            await service.bulk_create_assets(manager, name='X', count=201)


class TestPermissions:
    async def test_non_manager_cannot_create(self, db, service):
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        with pytest.raises(PermissionError):
            await service.create_asset(volunteer, name='Console')

    async def test_staff_can_manage(self, db, service):
        staff = await _user(3, 'staff', Role.STAFF)
        asset = await service.create_asset(staff, name='Console')
        assert asset.asset_number == 1


class TestCheckoutCheckin:
    async def test_volunteer_checkout_is_self_only(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        other = await _user(3, 'other', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')

        # Volunteer attempts to check out to someone else — forced to self.
        loan = await service.checkout(volunteer, asset.id, borrower_id=other.id)
        assert loan.borrower_id == volunteer.id

        refreshed = await service.get_asset(asset.id)
        assert refreshed.status == EquipmentStatus.CHECKED_OUT

    async def test_manager_can_checkout_on_behalf(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        borrower = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')

        loan = await service.checkout(manager, asset.id, borrower_id=borrower.id)
        assert loan.borrower_id == borrower.id

    async def test_cannot_checkout_when_already_out(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')
        await service.checkout(manager, asset.id, borrower_id=volunteer.id)

        with pytest.raises(ValueError):
            await service.checkout(volunteer, asset.id)

    async def test_volunteer_cannot_checkin(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')
        await service.checkout(volunteer, asset.id)

        with pytest.raises(PermissionError):
            await service.checkin(volunteer, asset.id)

    async def test_checkin_closes_loan_and_frees_asset(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')
        await service.checkout(volunteer, asset.id)

        await service.checkin(manager, asset.id)

        refreshed = await service.get_asset(asset.id)
        assert refreshed.status == EquipmentStatus.AVAILABLE
        loan = await EquipmentLoan.get(equipment=refreshed, borrower=volunteer)
        assert loan.checked_in_at is not None
        assert loan.checked_in_by_id == manager.id
        # Asset is checkout-able again afterward.
        assert await service.current_loan(refreshed) is None


class TestDelete:
    async def test_delete_blocked_while_on_loan(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')
        await service.checkout(volunteer, asset.id)

        with pytest.raises(ValueError):
            await service.delete_asset(manager, asset.id)

    async def test_delete_after_checkin(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        volunteer = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Console')
        await service.checkout(volunteer, asset.id)
        await service.checkin(manager, asset.id)

        await service.delete_asset(manager, asset.id)
        assert await Equipment.all().count() == 0


class TestGetAssetsByIds:
    async def test_returns_selected_ordered_by_number(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        a = await service.create_asset(manager, name='A')  # number 1
        b = await service.create_asset(manager, name='B')  # number 2
        c = await service.create_asset(manager, name='C')  # number 3

        got = await service.get_assets_by_ids([c.id, a.id])
        # Selection honored, and ordered by asset_number regardless of input order.
        assert [x.asset_number for x in got] == [a.asset_number, c.asset_number]
        assert b.id not in {x.id for x in got}

    async def test_empty_and_unknown_ids(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        asset = await service.create_asset(manager, name='A')
        assert await service.get_assets_by_ids([]) == []
        # Unknown ids are silently dropped; known ones still come back.
        got = await service.get_assets_by_ids([asset.id, 999_999])
        assert [x.id for x in got] == [asset.id]

    async def test_does_not_leak_across_tenants(self, service, two_tenants):
        tenant_a, tenant_b = two_tenants
        # Create assets directly per tenant (asset_number is unique per tenant,
        # so both can be #1) — this exercises the repo's tenant scoping, not the
        # per-tenant role gate.
        a_asset = await Equipment.create(tenant_id=tenant_a.id, asset_number=1, name='A-asset')
        b_asset = await Equipment.create(tenant_id=tenant_b.id, asset_number=1, name='B-asset')

        # Asking for both ids from within tenant A returns only tenant A's asset.
        with tenant_scope(tenant_a.id):
            got = await service.get_assets_by_ids([a_asset.id, b_asset.id])
        assert [x.id for x in got] == [a_asset.id]


class TestOwnerLabel:
    async def test_owner_label_house_vs_user(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        owner = await _user(2, 'owner', Role.VOLUNTEER)

        house = await service.create_asset(manager, name='House asset')
        # An un-owned asset falls back to the owning community's name.
        assert house.owner_label('Acme Community') == 'Acme Community'

        owned = await service.create_asset(manager, name='Owned asset', owner_user_id=owner.id)
        fetched = await service.get_asset(owned.id)
        assert fetched.owner_label('Acme Community') == owner.preferred_name


class TestLoanHistoryBound:
    """The history is bounded at the read, not just at the render.

    An asset lent two hundred times used to fetch two hundred rows with three
    prefetched users each, and paint every one, on the phone where scrolling
    costs most.
    """

    @staticmethod
    async def _asset_with_loans(service, count: int):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        borrower = await _user(2, 'vol', Role.VOLUNTEER)
        asset = await service.create_asset(manager, name='Well-travelled cable')
        for _ in range(count):
            await service.checkout(borrower, asset.id)
            await service.checkin(manager, asset.id)
        return asset, manager, borrower

    async def test_limit_is_honoured(self, db, service):
        asset, _, _ = await self._asset_with_loans(service, 12)
        assert len(await service.loan_history(asset, limit=5)) == 5

    async def test_no_limit_returns_everything(self, db, service):
        asset, _, _ = await self._asset_with_loans(service, 12)
        assert len(await service.loan_history(asset)) == 12

    async def test_count_is_the_total_not_the_page(self, db, service):
        asset, _, _ = await self._asset_with_loans(service, 12)
        await service.loan_history(asset, limit=5)
        assert await service.loan_count(asset) == 12

    async def test_the_bounded_page_is_the_most_recent(self, db, service):
        asset, _, _ = await self._asset_with_loans(service, 12)
        every = await service.loan_history(asset)
        page = await service.loan_history(asset, limit=3)
        assert [loan.id for loan in page] == [loan.id for loan in every[:3]]
        # Newest first, so the page's oldest row is no older than the rest.
        assert page[0].checked_out_at >= page[-1].checked_out_at

    async def test_an_asset_with_no_loans_is_clean(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        asset = await service.create_asset(manager, name='Never lent')
        assert await service.loan_history(asset, limit=5) == []
        assert await service.loan_count(asset) == 0

    async def test_a_limit_larger_than_the_history_is_fine(self, db, service):
        asset, _, _ = await self._asset_with_loans(service, 2)
        assert len(await service.loan_history(asset, limit=50)) == 2
