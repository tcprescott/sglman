"""
Authorization Service - Business Logic Layer

Stateless policy helpers for role-based access control. All checks accept
a User model (or None). UI code that only has the storage discord_id
should call current_user_from_storage() once at page entry to resolve the
User, then pass it into the helpers.
"""

from typing import Optional

from nicegui import app

from models import Match, Role, Tournament, User, UserRole


class AuthService:
    """Stateless authorization helpers."""

    @staticmethod
    async def get_roles(user: Optional[User]) -> set[Role]:
        if user is None:
            return set()
        rows = await UserRole.filter(user=user).values_list('role', flat=True)
        return {Role(r) for r in rows}

    @staticmethod
    async def has_role(user: Optional[User], role: Role) -> bool:
        if user is None:
            return False
        return await UserRole.filter(user=user, role=role).exists()

    @staticmethod
    async def is_staff(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.STAFF)

    @staticmethod
    async def is_proctor(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.PROCTOR)

    @staticmethod
    async def is_stream_manager(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.STREAM_MANAGER)

    @staticmethod
    async def is_triforce_submitter(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.TRIFORCE_SUBMITTER)

    @staticmethod
    async def can_submit_triforce_text(user: Optional[User], tournament: Tournament) -> bool:
        """Submitting requires the paid Triforce Submitter role (staff override),
        and the tournament must be active with a generator that supports texts."""
        from application.services.seedgen_service import SeedGenerationService

        if not tournament.is_active:
            return False
        if not SeedGenerationService.supports_triforce_texts(tournament.seed_generator):
            return False
        return await AuthService.is_staff(user) or await AuthService.is_triforce_submitter(user)

    @staticmethod
    async def is_tournament_admin(user: Optional[User], tournament_id: int) -> bool:
        if user is None:
            return False
        return await Tournament.filter(id=tournament_id, admins__id=user.id).exists()

    @staticmethod
    async def is_crew_coordinator_of(user: Optional[User], tournament_id: int) -> bool:
        if user is None:
            return False
        return await Tournament.filter(id=tournament_id, crew_coordinators__id=user.id).exists()

    @staticmethod
    async def can_view_admin(user: Optional[User]) -> bool:
        """Any global role or any TA/CC tournament membership."""
        if user is None:
            return False
        if await AuthService.get_roles(user):
            return True
        if await user.admin_tournaments.all().exists():
            return True
        return await user.crew_coordinated_tournaments.all().exists()

    @staticmethod
    async def can_edit_tournament(user: Optional[User], tournament: Tournament) -> bool:
        if await AuthService.is_staff(user):
            return True
        return await AuthService.is_tournament_admin(user, tournament.id)

    @staticmethod
    async def can_crud_match(user: Optional[User], match: Match) -> bool:
        if await AuthService.is_staff(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_transition_match(user: Optional[User], match: Match) -> bool:
        """Seat/start/finish/confirm/roll seeds and assign stations."""
        if await AuthService.is_staff(user) or await AuthService.is_proctor(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_approve_crew(user: Optional[User], match: Match) -> bool:
        if await AuthService.is_staff(user):
            return True
        if await AuthService.is_tournament_admin(user, match.tournament_id):
            return True
        return await AuthService.is_crew_coordinator_of(user, match.tournament_id)

    @staticmethod
    async def can_manage_stream_rooms(user: Optional[User]) -> bool:
        """CRUD on StreamRoom records (the stages themselves)."""
        return await AuthService.is_staff(user) or await AuthService.is_stream_manager(user)

    @staticmethod
    async def is_volunteer_coordinator(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.VOLUNTEER_COORDINATOR)

    @staticmethod
    async def can_manage_volunteers(user: Optional[User]) -> bool:
        """Manage volunteer positions, shifts, and assignments (admin side)."""
        return await AuthService.is_staff(user) or await AuthService.is_volunteer_coordinator(user)

    @staticmethod
    async def is_equipment_manager(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.EQUIPMENT_MANAGER)

    @staticmethod
    async def is_volunteer(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.VOLUNTEER)

    @staticmethod
    async def can_manage_equipment(user: Optional[User]) -> bool:
        """Create/edit/delete lending assets and view private notes/owner."""
        return await AuthService.is_staff(user) or await AuthService.is_equipment_manager(user)

    @staticmethod
    async def can_checkout_equipment(user: Optional[User]) -> bool:
        """Check equipment out (volunteers may only check out to themselves)."""
        if await AuthService.can_manage_equipment(user):
            return True
        return await AuthService.is_volunteer(user)

    @staticmethod
    async def can_checkin_equipment(user: Optional[User]) -> bool:
        """Check equipment back in."""
        return await AuthService.can_manage_equipment(user)

    @staticmethod
    async def can_assign_match_stream(user: Optional[User], match: Match) -> bool:
        """Set a match's stream_room or is_stream_candidate flag.
        Stream Managers can do this globally; TAs can do it for their own tournaments.
        """
        if await AuthService.can_manage_stream_rooms(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_grant_roles(user: Optional[User]) -> bool:
        """Grant/revoke UserRole rows and Tournament.admins / crew_coordinators."""
        return await AuthService.is_staff(user)

    @staticmethod
    async def ensure(allowed: bool, message: str = "Permission denied") -> None:
        if not allowed:
            raise PermissionError(message)


async def current_user_from_storage() -> Optional[User]:
    """Resolve the current request's user from NiceGUI storage to a User model.

    Returns None when the user is not logged in or no longer in the database.
    Call once at page entry and pass the result into AuthService helpers.
    """
    discord_id = app.storage.user.get('discord_id')
    if not discord_id:
        return None
    return await User.get_or_none(discord_id=discord_id)
