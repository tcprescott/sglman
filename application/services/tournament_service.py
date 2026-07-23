"""
Tournament Service - Business Logic Layer

Handles tournament-related operations including creation, updates, validation,
and admin/crew-coordinator membership.
"""

from datetime import date
from typing import Any, Dict, Optional, Tuple

from application.repositories import (
    PresetRepository,
    RaceRoomProfileRepository,
    RacetimeBotRepository,
    TournamentRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.system_config_service import SystemConfigService
from application.services.tournament_config import validate_tournament_config
from application.tenant_context import require_tenant_id
from models import Tournament, User

# Sentinel distinguishing "caller did not supply preset_id" (leave as-is) from an
# explicit None (detach the preset). Update-only; create defaults to no preset.
_UNSET = object()


class TournamentService:
    """Service for tournament-related business operations."""

    def __init__(self) -> None:
        self.repository = TournamentRepository()
        self.preset_repository = PresetRepository()
        self.racetime_bot_repository = RacetimeBotRepository()
        self.race_room_profile_repository = RaceRoomProfileRepository()
        self.audit_service = AuditService()

    async def _resolve_preset_id(self, preset_id: Optional[int]) -> Optional[int]:
        """Validate an incoming preset_id is a real preset in this tenant.

        ``None`` clears the FK. A non-null id must resolve through the
        tenant-scoped repository, so a preset from another tenant is rejected
        rather than silently linked.
        """
        if preset_id is None:
            return None
        preset = await self.preset_repository.get_by_id(preset_id)
        if preset is None:
            raise ValueError("Preset not found")
        return preset.id

    async def _resolve_racetime_bot_id(self, racetime_bot_id: Optional[int]) -> Optional[int]:
        """Validate the bot is one this tenant is *authorized* to use.

        ``None`` clears the FK. A non-null id must appear in the tenant's active
        authorization grants, so a category the tenant was never granted — or
        another tenant's bot — is rejected rather than silently linked.
        """
        if racetime_bot_id is None:
            return None
        authorized = await self.racetime_bot_repository.list_active_for_tenant(require_tenant_id())
        if not any(bot.id == racetime_bot_id for bot in authorized):
            raise ValueError("Racetime bot not available to this tenant")
        return racetime_bot_id

    async def _resolve_race_room_profile_id(self, profile_id: Optional[int]) -> Optional[int]:
        """Validate the room profile belongs to this tenant. ``None`` clears it."""
        if profile_id is None:
            return None
        profile = await self.race_room_profile_repository.get_by_id(profile_id)
        if profile is None:
            raise ValueError("Race room profile not found")
        return profile.id

    @staticmethod
    def _coerce_day(value: Any, label: str) -> Optional[date]:
        """Coerce a date/ISO-string/blank into a ``date`` (or ``None`` to inherit)."""
        if value is None or value == '':
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            raise ValueError(f"{label} must be in YYYY-MM-DD format.")

    def _normalize_event_dates(
        self, event_start_date: Any, event_end_date: Any,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Validate the per-tournament event-window override (each bound optional)."""
        start = self._coerce_day(event_start_date, "Event start date")
        end = self._coerce_day(event_end_date, "Event end date")
        if start is not None and end is not None and end < start:
            raise ValueError("Event end date cannot be before the event start date.")
        return start, end

    @staticmethod
    def _normalize_tournament_hours(
        tournament_hours: Optional[Dict[date, Tuple[str, str]]],
    ) -> Optional[Dict[str, Dict[str, str]]]:
        """Validate a {date: (open, close)} override into a storable blob.

        Returns ``None`` when the mapping is empty/absent so an unset override
        inherits the tenant hours; otherwise the validated
        ``{date_iso: {'open', 'close'}}`` blob. Reuses the tenant validator so
        both surfaces enforce identical HH:MM / close>open rules.
        """
        if not tournament_hours:
            return None
        return SystemConfigService.validate_hours_mapping(tournament_hours) or None

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
        config: Optional[Dict[str, Any]] = None,
        preset_id: Optional[int] = None,
        racetime_bot_id: Optional[int] = None,
        race_room_profile_id: Optional[int] = None,
        racetime_auto_create_rooms: bool = False,
        room_open_minutes_before: int = 30,
        require_racetime_link: bool = False,
        racetime_default_goal: Optional[str] = None,
        event_start_date: Any = None,
        event_end_date: Any = None,
        tournament_hours: Optional[Dict[date, Tuple[str, str]]] = None,
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

        config = validate_tournament_config(config)
        event_start_date, event_end_date = self._normalize_event_dates(
            event_start_date, event_end_date,
        )
        tournament_hours = self._normalize_tournament_hours(tournament_hours)
        preset_id = await self._resolve_preset_id(preset_id)
        racetime_bot_id = await self._resolve_racetime_bot_id(racetime_bot_id)
        race_room_profile_id = await self._resolve_race_room_profile_id(race_room_profile_id)

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
            config=config,
            preset_id=preset_id,
            racetime_bot_id=racetime_bot_id,
            race_room_profile_id=race_room_profile_id,
            racetime_auto_create_rooms=racetime_auto_create_rooms,
            room_open_minutes_before=room_open_minutes_before,
            require_racetime_link=require_racetime_link,
            racetime_default_goal=(racetime_default_goal.strip() if racetime_default_goal else None),
            event_start_date=event_start_date,
            event_end_date=event_end_date,
            tournament_hours=tournament_hours,
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
        config: Optional[Dict[str, Any]] = None,
        preset_id: Any = _UNSET,
        racetime_bot_id: Any = _UNSET,
        race_room_profile_id: Any = _UNSET,
        racetime_auto_create_rooms: Optional[bool] = None,
        room_open_minutes_before: Optional[int] = None,
        require_racetime_link: Optional[bool] = None,
        racetime_default_goal: Any = _UNSET,
        event_start_date: Any = _UNSET,
        event_end_date: Any = _UNSET,
        tournament_hours: Any = _UNSET,
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

        update_data: Dict[str, Any] = {}
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
        if config is not None:
            update_data['config'] = validate_tournament_config(config)
        if preset_id is not _UNSET:
            update_data['preset_id'] = await self._resolve_preset_id(preset_id)
        if racetime_bot_id is not _UNSET:
            update_data['racetime_bot_id'] = await self._resolve_racetime_bot_id(racetime_bot_id)
        if race_room_profile_id is not _UNSET:
            update_data['race_room_profile_id'] = await self._resolve_race_room_profile_id(race_room_profile_id)
        if racetime_auto_create_rooms is not None:
            update_data['racetime_auto_create_rooms'] = racetime_auto_create_rooms
        if room_open_minutes_before is not None:
            update_data['room_open_minutes_before'] = room_open_minutes_before
        if require_racetime_link is not None:
            update_data['require_racetime_link'] = require_racetime_link
        if racetime_default_goal is not _UNSET:
            update_data['racetime_default_goal'] = (
                racetime_default_goal.strip() if racetime_default_goal else None
            )
        if event_start_date is not _UNSET or event_end_date is not _UNSET:
            # Validate the window as a pair, using the current stored value for
            # whichever bound the caller left untouched.
            raw_start = event_start_date if event_start_date is not _UNSET else tournament.event_start_date
            raw_end = event_end_date if event_end_date is not _UNSET else tournament.event_end_date
            norm_start, norm_end = self._normalize_event_dates(raw_start, raw_end)
            if event_start_date is not _UNSET:
                update_data['event_start_date'] = norm_start
            if event_end_date is not _UNSET:
                update_data['event_end_date'] = norm_end
        if tournament_hours is not _UNSET:
            update_data['tournament_hours'] = self._normalize_tournament_hours(tournament_hours)

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
