"""
User Service - Business Logic Layer

Coordinates user-related operations and enforces business rules.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set

from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Role, Tournament, TournamentPlayers, User


class UserService:
    """Service for user-related business operations."""

    def __init__(self):
        self.repository = UserRepository()
        self.role_repository = UserRoleRepository()
        self.audit_service = AuditService()

    async def get_user_by_discord_id(self, discord_id: str) -> Optional[User]:
        return await self.repository.get_by_discord_id(discord_id)

    async def get_current_user_from_storage(self, storage_discord_id: Optional[str]) -> Optional[User]:
        if not storage_discord_id:
            return None
        return await self.repository.get_by_discord_id(storage_discord_id)

    async def get_active_tournaments_categorized(self) -> Dict[str, List[Tournament]]:
        tournaments = await Tournament.filter(is_active=True)
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]
        return {
            'staff_tournaments': staff_tournaments,
            'player_tournaments': player_tournaments,
            'all_tournaments': tournaments,
        }

    async def get_user_tournament_registrations(self, user: User) -> List[TournamentPlayers]:
        return await TournamentPlayers.filter(user=user)

    async def update_user_personal_info(
        self,
        user: User,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        dm_notifications: Optional[bool] = None,
    ) -> User:
        """Update the user's own profile fields. Caller is expected to be the
        same user (self-edit); permission check is performed at the page level
        via authentication.
        """
        any_provided = False
        changed: Dict[str, object] = {}
        if display_name is not None:
            any_provided = True
            new_value = display_name.strip() if display_name.strip() else None
            if new_value != user.display_name:
                changed['display_name'] = new_value
            user.display_name = new_value
        if pronouns is not None:
            any_provided = True
            new_value = pronouns.strip() if pronouns.strip() else None
            if new_value != user.pronouns:
                changed['pronouns'] = new_value
            user.pronouns = new_value
        if dm_notifications is not None:
            any_provided = True
            if dm_notifications != user.dm_notifications:
                changed['dm_notifications'] = dm_notifications
            user.dm_notifications = dm_notifications

        if any_provided:
            await user.save()
        if changed:
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_SELF_PROFILE_UPDATED,
                {'target_user_id': user.id, 'changed_fields': changed},
            )
        return user

    async def update_user_tournament_registrations(
        self,
        user: User,
        actor: User,
        selected_tournament_ids: Set[int],
        current_registrations: List[TournamentPlayers],
    ) -> None:
        current_ids = set(tp.tournament_id for tp in current_registrations)
        removed_ids = current_ids - selected_tournament_ids
        added_ids = selected_tournament_ids - current_ids

        for tp in current_registrations:
            if tp.tournament_id in removed_ids:
                await tp.delete()
        for tournament_id in added_ids:
            tournament = await Tournament.get_or_none(id=tournament_id)
            if tournament:
                await TournamentPlayers.create(user=user, tournament=tournament)

        if added_ids or removed_ids:
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
                {
                    'target_user_id': user.id,
                    'added_tournament_ids': sorted(added_ids),
                    'removed_tournament_ids': sorted(removed_ids),
                },
            )

    async def create_user(
        self,
        username: str,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        is_active: bool = True,
        discord_id: Optional[str] = None,
    ) -> User:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can create users",
        )
        if not username or not username.strip():
            raise ValueError("Username is required")
        new_user = await self.repository.create(
            username=username.strip(),
            display_name=display_name.strip() if display_name else None,
            pronouns=pronouns.strip() if pronouns else None,
            is_active=is_active,
            discord_id=discord_id,
        )
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_CREATED,
            {
                'target_user_id': new_user.id,
                'username': new_user.username,
                'is_active': is_active,
                'discord_id': discord_id,
            },
        )
        return new_user

    async def update_user_profile(
        self,
        user: User,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        check_concurrency: bool = False,
        initial_updated_at: Optional[datetime] = None,
    ) -> User:
        """Update display_name / pronouns. Allowed for the user themselves or Staff."""
        if actor.id != user.id and not await AuthService.is_staff(actor):
            raise PermissionError("User cannot edit another user's profile")

        if check_concurrency and initial_updated_at is not None:
            latest_user = await self.repository.get_by_id(user.id)
            if latest_user and latest_user.updated_at != initial_updated_at:
                raise ValueError("This user has been modified by another admin. Please reload and try again.")

        update_data = {}
        if display_name is not None:
            update_data['display_name'] = display_name.strip() if display_name else None
        if pronouns is not None:
            update_data['pronouns'] = pronouns.strip() if pronouns else None

        if update_data:
            await self.repository.update(user, **update_data)
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_PROFILE_UPDATED,
                {'target_user_id': user.id, 'changed_fields': update_data},
            )
        return user

    async def update_user_admin_fields(
        self,
        user: User,
        actor: User,
        is_active: Optional[bool] = None,
        check_concurrency: bool = False,
        initial_updated_at: Optional[datetime] = None,
    ) -> User:
        """Update admin-managed user fields (is_active). Staff-only."""
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can edit admin fields",
        )

        if check_concurrency and initial_updated_at is not None:
            latest_user = await self.repository.get_by_id(user.id)
            if latest_user and latest_user.updated_at != initial_updated_at:
                raise ValueError("This user has been modified by another admin. Please reload and try again.")

        update_data = {}
        if is_active is not None:
            update_data['is_active'] = is_active

        if update_data:
            previous_is_active = user.is_active
            await self.repository.update(user, **update_data)
            if is_active is not None and is_active != previous_is_active:
                await self.audit_service.write_log(
                    actor,
                    AuditActions.USER_ACTIVATION_CHANGED,
                    {'target_user_id': user.id, 'is_active': is_active},
                )
        return user

    async def grant_role(self, target: User, role: Role, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can grant roles",
        )
        await self.role_repository.add(target, role, granted_by=actor)
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_ROLE_GRANTED,
            {'role': role.value, 'target_user_id': target.id},
        )

    async def revoke_role(self, target: User, role: Role, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can revoke roles",
        )
        await self.role_repository.remove(target, role)
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_ROLE_REVOKED,
            {'role': role.value, 'target_user_id': target.id},
        )

    async def manage_tournament_enrollments(
        self,
        user: User,
        actor: User,
        tournament_ids: Set[int],
        is_update: bool = True,
    ) -> None:
        if is_update:
            current_registrations = await self.get_user_tournament_registrations(user)
            await self.update_user_tournament_registrations(
                user, actor, tournament_ids, current_registrations,
            )
        else:
            added: List[int] = []
            for tournament_id in tournament_ids:
                tournament = await Tournament.get_or_none(id=tournament_id)
                if tournament:
                    await TournamentPlayers.create(user=user, tournament=tournament)
                    added.append(tournament_id)
            if added:
                await self.audit_service.write_log(
                    actor,
                    AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
                    {
                        'target_user_id': user.id,
                        'added_tournament_ids': sorted(added),
                        'removed_tournament_ids': [],
                    },
                )
