"""
Equipment Service - Business Logic Layer

Manages lending assets (create/edit/delete, bulk creation, auto-assigned asset
numbers) and the checkout/check-in workflow with full loan history.
"""

from datetime import datetime, timezone
from typing import List, Optional

from application.errors import require_found
from application.repositories.equipment_repository import EquipmentRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Equipment, EquipmentLoan, EquipmentStatus, User

MAX_BULK_COUNT = 200


class EquipmentService:
    """Service for equipment lending operations."""

    def __init__(self) -> None:
        self.repository = EquipmentRepository()
        self.audit_service = AuditService()

    @staticmethod
    async def _resolve_owner(owner_user_id: Optional[int]) -> Optional[User]:
        """Resolve an owner id to a User; ``None`` means Wizzrobe."""
        if not owner_user_id:
            return None
        owner = await User.get_or_none(id=owner_user_id)
        if owner is None:
            raise ValueError("Selected owner was not found.")
        return owner

    # --- Asset management (Equipment Manager / Staff) ---

    async def create_asset(
        self,
        actor: User,
        name: str,
        description: Optional[str] = None,
        private_notes: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> Equipment:
        await AuthService.ensure(
            await AuthService.can_manage_equipment(actor),
            "You do not have permission to manage equipment.",
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Asset name is required.")

        owner = await self._resolve_owner(owner_user_id)
        asset_number = await self.repository.next_asset_number()
        equipment = await self.repository.create(
            asset_number=asset_number,
            name=name,
            description=(description or '').strip() or None,
            private_notes=(private_notes or '').strip() or None,
            owner_user=owner,
        )

        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_CREATED,
            {'equipment_id': equipment.id, 'asset_number': asset_number},
        )
        return equipment

    async def bulk_create_assets(
        self,
        actor: User,
        name: str,
        count: int,
        description: Optional[str] = None,
        private_notes: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> List[Equipment]:
        await AuthService.ensure(
            await AuthService.can_manage_equipment(actor),
            "You do not have permission to manage equipment.",
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Asset name is required.")
        if not 1 <= count <= MAX_BULK_COUNT:
            raise ValueError(f"Count must be between 1 and {MAX_BULK_COUNT}.")

        owner = await self._resolve_owner(owner_user_id)
        start = await self.repository.next_asset_number()
        description = (description or '').strip() or None
        private_notes = (private_notes or '').strip() or None

        assets = [
            Equipment(
                asset_number=start + offset,
                name=name,
                description=description,
                private_notes=private_notes,
                owner_user=owner,
            )
            for offset in range(count)
        ]
        await self.repository.bulk_create(assets)

        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_CREATED,
            {'count': count, 'asset_number_start': start, 'asset_number_end': start + count - 1},
        )
        return assets

    async def update_asset(
        self,
        actor: User,
        equipment_id: int,
        name: str,
        description: Optional[str],
        private_notes: Optional[str],
        owner_user_id: Optional[int],
        status: Optional[EquipmentStatus] = None,
    ) -> Equipment:
        await AuthService.ensure(
            await AuthService.can_manage_equipment(actor),
            "You do not have permission to manage equipment.",
        )
        equipment = require_found(await self.repository.get_by_id(equipment_id), "Asset")
        name = (name or '').strip()
        if not name:
            raise ValueError("Asset name is required.")

        equipment.name = name
        equipment.description = (description or '').strip() or None
        equipment.private_notes = (private_notes or '').strip() or None
        equipment.owner_user = await self._resolve_owner(owner_user_id)
        fields = ['name', 'description', 'private_notes', 'owner_user_id', 'updated_at']

        if status is not None and status != equipment.status:
            if equipment.status == EquipmentStatus.CHECKED_OUT or status == EquipmentStatus.CHECKED_OUT:
                raise ValueError("Use check out / check in to change a checked-out status.")
            equipment.status = status
            fields.append('status')

        await self.repository.update(equipment, fields)
        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_UPDATED,
            {'equipment_id': equipment.id, 'asset_number': equipment.asset_number},
        )
        return equipment

    async def delete_asset(self, actor: User, equipment_id: int) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_equipment(actor),
            "You do not have permission to manage equipment.",
        )
        equipment = require_found(await self.repository.get_by_id(equipment_id), "Asset")
        if await self.repository.get_open_loan(equipment) is not None:
            raise ValueError("Cannot delete an asset that is currently checked out.")

        asset_number = equipment.asset_number
        await self.repository.delete(equipment)
        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_DELETED,
            {'equipment_id': equipment_id, 'asset_number': asset_number},
        )

    # --- Checkout / check-in ---

    async def checkout(
        self,
        actor: User,
        equipment_id: int,
        borrower_id: Optional[int] = None,
    ) -> EquipmentLoan:
        await AuthService.ensure(
            await AuthService.can_checkout_equipment(actor),
            "You do not have permission to check out equipment.",
        )
        # Volunteers may only check out to themselves; managers/staff may check
        # out on behalf of any user.
        if await AuthService.can_manage_equipment(actor) and borrower_id:
            borrower = await User.get_or_none(id=borrower_id)
            if borrower is None:
                raise ValueError("Selected borrower was not found.")
        else:
            borrower = actor

        equipment = require_found(await self.repository.get_by_id(equipment_id), "Asset")
        if equipment.status == EquipmentStatus.RETIRED:
            raise ValueError("This asset is retired and cannot be checked out.")
        if await self.repository.get_open_loan(equipment) is not None:
            raise ValueError("This asset is already checked out.")

        loan = await self.repository.create_loan(equipment, borrower, actor)
        equipment.status = EquipmentStatus.CHECKED_OUT
        await self.repository.update(equipment, ['status', 'updated_at'])

        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_CHECKED_OUT,
            {'equipment_id': equipment.id, 'asset_number': equipment.asset_number, 'borrower_id': borrower.id},
        )
        return loan

    async def checkin(self, actor: User, equipment_id: int) -> Equipment:
        await AuthService.ensure(
            await AuthService.can_checkin_equipment(actor),
            "You do not have permission to check in equipment.",
        )
        equipment = require_found(await self.repository.get_by_id(equipment_id), "Asset")
        loan = await self.repository.get_open_loan(equipment)
        if loan is None:
            raise ValueError("This asset is not currently checked out.")

        await self.repository.close_loan(loan, actor, datetime.now(timezone.utc))
        equipment.status = EquipmentStatus.AVAILABLE
        await self.repository.update(equipment, ['status', 'updated_at'])

        await self.audit_service.write_log(
            actor,
            AuditActions.EQUIPMENT_CHECKED_IN,
            {'equipment_id': equipment.id, 'asset_number': equipment.asset_number},
        )
        return equipment

    # --- Reads ---

    async def list_assets(self) -> List[Equipment]:
        return await self.repository.list_all()

    async def get_assets_by_ids(self, ids: List[int]) -> List[Equipment]:
        """Fetch the given assets (tenant-scoped) for bulk QR-label printing.

        A pure read ordered by asset number. The tenant-scoped query silently
        drops any id that is unknown or belongs to another community, so a
        crafted id list can never surface another tenant's assets.
        """
        return await self.repository.list_by_ids(ids)

    async def get_asset(self, equipment_id: int) -> Optional[Equipment]:
        return await self.repository.get_by_id(equipment_id)

    async def current_loan(self, equipment: Equipment) -> Optional[EquipmentLoan]:
        return await self.repository.get_open_loan(equipment)

    async def open_loans_by_equipment_id(self) -> dict[int, EquipmentLoan]:
        return await self.repository.open_loans_by_equipment_id()

    async def loan_history(self, equipment: Equipment) -> List[EquipmentLoan]:
        return await self.repository.list_loans_for_equipment(equipment)

    async def my_checkouts(self, user: User) -> List[EquipmentLoan]:
        return await self.repository.list_open_loans_for_user(user)
