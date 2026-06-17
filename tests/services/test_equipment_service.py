import pytest

from application.services.equipment_service import EquipmentService
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


class TestOwnerLabel:
    async def test_owner_label_house_vs_user(self, db, service):
        manager = await _user(1, 'manager', Role.EQUIPMENT_MANAGER)
        owner = await _user(2, 'owner', Role.VOLUNTEER)

        house = await service.create_asset(manager, name='House asset')
        assert house.owner_label == 'SpeedGaming Live'

        owned = await service.create_asset(manager, name='Owned asset', owner_user_id=owner.id)
        fetched = await service.get_asset(owned.id)
        assert fetched.owner_label == owner.preferred_name
