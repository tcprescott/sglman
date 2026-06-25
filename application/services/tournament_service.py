"""
Tournament Service - Business Logic Layer

Handles tournament-related operations including creation, updates, validation,
and admin/crew-coordinator membership.
"""

from typing import Optional

from application.repositories import TournamentRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Tournament, User


class TournamentService:
    """Service for tournament-related business operations."""

    def __init__(self) -> None:
        self.repository = TournamentRepository()
        self.audit_service = AuditService()

    async def create_tournament(
        self,
        name: str,
        description: Optional[str] = None,
        seed_generator: Optional[str] = None,
        bracket_url: Optional[str] = None,
        rules_url: Optional[str] = None,
        tournament_format: Optional[str] = None,
        triforce_access_message: Optional[str] = None,
        average_match_duration: Optional[int] = None,
        max_match_duration: Optional[int] = None,
        is_active: bool = True,
        players_per_match: int = 2,
        team_size: int = 1,
        staff_administered: bool = False,
        actor: Optional[User] = None,
    ) -> Tournament:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can create tournaments",
        )

        if not name or not name.strip():
            raise ValueError("Tournament name is required")

        if seed_generator == "None":
            seed_generator = None

        tournament = await self.repository.create(
            name=name.strip(),
            description=description.strip() if description else None,
            seed_generator=seed_generator,
            bracket_url=bracket_url.strip() if bracket_url else None,
            rules_url=rules_url.strip() if rules_url else None,
            tournament_format=tournament_format.strip() if tournament_format else None,
            triforce_access_message=triforce_access_message.strip() if triforce_access_message else None,
            average_match_duration=average_match_duration,
            max_match_duration=max_match_duration,
            is_active=is_active,
            players_per_match=players_per_match,
            team_size=team_size,
            staff_administered=staff_administered,
        )

        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_CREATED,
            {'tournament_id': tournament.id, 'name': tournament.name},
        )

        return tournament

    async def update_tournament(
        self,
        tournament: Tournament,
        name: Optional[str] = None,
        description: Optional[str] = None,
        seed_generator: Optional[str] = None,
        bracket_url: Optional[str] = None,
        rules_url: Optional[str] = None,
        tournament_format: Optional[str] = None,
        triforce_access_message: Optional[str] = None,
        average_match_duration: Optional[int] = None,
        max_match_duration: Optional[int] = None,
        is_active: Optional[bool] = None,
        players_per_match: Optional[int] = None,
        team_size: Optional[int] = None,
        staff_administered: Optional[bool] = None,
        actor: Optional[User] = None,
    ) -> Tournament:
        await AuthService.ensure(
            await AuthService.can_edit_tournament(actor, tournament),
            f"User cannot edit tournament {tournament.id}",
        )

        if name is not None and (not name or not name.strip()):
            raise ValueError("Tournament name cannot be empty")

        if seed_generator == "None":
            seed_generator = None

        update_data = {}
        if name is not None:
            update_data['name'] = name.strip()
        if description is not None:
            update_data['description'] = description.strip() if description else None
        if seed_generator is not None:
            update_data['seed_generator'] = seed_generator
        if bracket_url is not None:
            update_data['bracket_url'] = bracket_url.strip() if bracket_url else None
        if rules_url is not None:
            update_data['rules_url'] = rules_url.strip() if rules_url else None
        if tournament_format is not None:
            update_data['tournament_format'] = tournament_format.strip() if tournament_format else None
        if triforce_access_message is not None:
            update_data['triforce_access_message'] = (
                triforce_access_message.strip() if triforce_access_message else None
            )
        if average_match_duration is not None:
            update_data['average_match_duration'] = average_match_duration
        if max_match_duration is not None:
            update_data['max_match_duration'] = max_match_duration
        if is_active is not None:
            update_data['is_active'] = is_active
        if players_per_match is not None:
            update_data['players_per_match'] = players_per_match
        if team_size is not None:
            update_data['team_size'] = team_size
        if staff_administered is not None:
            update_data['staff_administered'] = staff_administered

        result = await self.repository.update(tournament, **update_data)

        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_UPDATED,
            {'tournament_id': tournament.id, 'changed_fields': list(update_data.keys())},
        )

        return result

    async def delete_tournament(self, tournament: Tournament, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can delete tournaments",
        )
        tournament_id = tournament.id
        await tournament.delete()
        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_DELETED,
            {'tournament_id': tournament_id},
        )

    async def add_admin(self, tournament: Tournament, target: User, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can grant Tournament Admin",
        )
        await tournament.admins.add(target)
        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_ADMIN_GRANTED,
            {'tournament_id': tournament.id, 'target_user_id': target.id},
        )

    async def remove_admin(self, tournament: Tournament, target: User, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can revoke Tournament Admin",
        )
        await tournament.admins.remove(target)
        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_ADMIN_REVOKED,
            {'tournament_id': tournament.id, 'target_user_id': target.id},
        )

    async def add_crew_coordinator(self, tournament: Tournament, target: User, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can grant Crew Coordinator",
        )
        await tournament.crew_coordinators.add(target)
        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_CREW_COORDINATOR_GRANTED,
            {'tournament_id': tournament.id, 'target_user_id': target.id},
        )

    async def remove_crew_coordinator(self, tournament: Tournament, target: User, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can revoke Crew Coordinator",
        )
        await tournament.crew_coordinators.remove(target)
        await self.audit_service.write_log(
            actor,
            AuditActions.TOURNAMENT_CREW_COORDINATOR_REVOKED,
            {'tournament_id': tournament.id, 'target_user_id': target.id},
        )

    async def get_all_tournaments(self, active_only: bool = False) -> list[Tournament]:
        return await self.repository.get_all(active_only=active_only)

    async def get_tournament_by_id(self, tournament_id: int) -> Optional[Tournament]:
        return await self.repository.get_by_id(tournament_id)

    async def get_tournaments_by_ids(self, tournament_ids: list[int]) -> list[Tournament]:
        return await self.repository.get_by_ids(tournament_ids)

    async def get_enrolled_players(self, tournament: Tournament) -> list:
        return await self.repository.get_enrolled_players(tournament)

    async def get_enrolled_players_by_user(self, user: User) -> list:
        return await self.repository.get_enrolled_players_by_user(user)

    async def get_enrolled_players_by_tournament_id(self, tournament_id: int) -> list:
        return await self.repository.get_enrolled_players_by_tournament_id(tournament_id)
