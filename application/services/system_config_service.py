"""
SystemConfig Service - Business Logic Layer

Typed accessors over the SystemConfiguration key/value table.
"""

import json
from datetime import date, time
from typing import Dict, List, Optional, Tuple

from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from application.utils.timezone import to_local, today_local
from models import Match, Stage, StationFormat, SystemConfiguration, Tournament, User

KEY_EVENT_START_DATE = 'event_start_date'
KEY_EVENT_END_DATE = 'event_end_date'
KEY_MAX_CONCURRENT_PLAYERS = 'max_concurrent_players'
KEY_MAX_CONCURRENT_STAGES = 'max_concurrent_stages'
KEY_VOLUNTEER_REMINDER_LEAD_MINUTES = 'volunteer_reminder_lead_minutes'
KEY_VOLUNTEER_COMP_TIERS = 'volunteer_comp_tiers'
KEY_TOURNAMENT_HOURS = 'tournament_hours_by_date'
KEY_STATION_FORMAT = 'station_format'
# Whether the join page shows non-members today's match times and player names.
# Default off: the membership gate exists precisely to keep a stranger from
# reading a community's schedule, so publishing it again is a staff decision.
KEY_JOIN_PREVIEW = 'join_page_match_preview'


class SystemConfigService:
    """Typed get/set for SystemConfiguration entries used by reports."""

    @staticmethod
    async def get_raw(key: str) -> Optional[str]:
        # SystemConfiguration is per-tenant (unique on (tenant, name)).
        config = await SystemConfiguration.get_or_none(name=key, tenant_id=require_tenant_id())
        return config.value if config else None

    @staticmethod
    async def set_raw(key: str, value: str, actor: User) -> SystemConfiguration:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can modify system configuration",
        )
        tenant_id = require_tenant_id()
        config = await SystemConfiguration.get_or_none(name=key, tenant_id=tenant_id)
        old_value = config.value if config else None
        if config:
            config.value = value
            await config.save()
            result = config
        else:
            result = await SystemConfiguration.create(name=key, value=value, tenant_id=tenant_id)
        await AuditService().write_log(
            actor,
            AuditActions.SYSTEM_CONFIG_UPDATED,
            {'key': key, 'old_value': old_value, 'new_value': value},
        )
        return result

    @staticmethod
    async def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
        raw = await SystemConfigService.get_raw(key)
        if raw is None or raw == '':
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    async def get_bool(key: str, default: bool = False) -> bool:
        """A stored flag, defaulting when the key was never written.

        Anything other than the values ``set_raw`` writes for a switch reads as
        the default rather than as ``True`` — a half-written key must not turn a
        display toggle on by accident.
        """
        raw = await SystemConfigService.get_raw(key)
        if raw is None or raw == '':
            return default
        normalized = raw.strip().lower()
        if normalized in ('true', '1', 'yes', 'on'):
            return True
        if normalized in ('false', '0', 'no', 'off'):
            return False
        return default

    @staticmethod
    async def get_date(key: str, default: Optional[date] = None) -> Optional[date]:
        raw = await SystemConfigService.get_raw(key)
        if not raw:
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return default

    @staticmethod
    async def get_event_window(
        tournament: Optional[Tournament] = None,
    ) -> tuple[date, date]:
        """Return (start_date, end_date) for the event.

        When ``tournament`` sets its own ``event_start_date`` / ``event_end_date``
        those win (each bound independently); any bound the tournament leaves
        unset falls back to the tenant-wide setting. Passing no tournament (the
        default) preserves the tenant-only behavior every tenant-wide caller
        relies on.

        Falls back to the min/max Match.scheduled_at across all matches
        when SystemConfiguration values are missing. If there are no
        scheduled matches either, falls back to today.
        """
        start = tournament.event_start_date if tournament else None
        end = tournament.event_end_date if tournament else None

        if start is None:
            start = await SystemConfigService.get_date(KEY_EVENT_START_DATE)
        if end is None:
            end = await SystemConfigService.get_date(KEY_EVENT_END_DATE)

        if start is None or end is None:
            first = await Match.filter(tenant_id=require_tenant_id()).order_by('scheduled_at').first()
            last = await Match.filter(tenant_id=require_tenant_id()).order_by('-scheduled_at').first()
            derived_start = (
                to_local(first.scheduled_at).date()
                if first and first.scheduled_at else None
            )
            derived_end = (
                to_local(last.scheduled_at).date()
                if last and last.scheduled_at else None
            )
            if start is None:
                start = derived_start or today_local()
            if end is None:
                end = derived_end or start

        if end < start:
            end = start
        return start, end

    @staticmethod
    async def get_max_concurrent_players(default: int = 60) -> int:
        value = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_PLAYERS)
        return value if value is not None and value > 0 else default

    @staticmethod
    async def get_max_concurrent_stages(default: Optional[int] = None) -> int:
        value = await SystemConfigService.get_int(KEY_MAX_CONCURRENT_STAGES)
        if value is not None and value > 0:
            return value
        if default is not None:
            return default
        return await Stage.filter(is_active=True, tenant_id=require_tenant_id()).count()

    @staticmethod
    async def get_volunteer_reminder_lead_minutes(default: int = 60) -> int:
        value = await SystemConfigService.get_int(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES)
        return value if value is not None and value > 0 else default

    @staticmethod
    async def get_volunteer_comp_tiers(
        default: Optional[List[float]] = None,
    ) -> List[float]:
        """Hour thresholds at which a volunteer earns something, ascending.

        SGL comps a badge at 8 hours with more at 12 and 16, which is the
        default when the key was never set. Stored as a comma-separated list of
        hours; a single ``0`` means the community awards nothing by hours.

        A malformed value falls back to the default rather than raising — a
        typo in this box must not take the volunteer roster down.
        """
        fallback = [8.0, 12.0, 16.0] if default is None else sorted(default)
        raw = await SystemConfigService.get_raw(KEY_VOLUNTEER_COMP_TIERS)
        if raw is None or not raw.strip():
            return fallback
        tiers: set[float] = set()
        for token in raw.split(','):
            token = token.strip()
            if not token:
                continue
            try:
                value = float(token)
            except ValueError:
                return fallback
            if value > 0:
                tiers.add(value)
        return sorted(tiers)

    @staticmethod
    def _parse_hours_blob(data: Dict) -> Dict[date, Tuple[time, time]]:
        """Parse a ``{date_iso: {'open', 'close'}}`` blob into typed windows.

        Malformed entries are skipped rather than raising — the same forgiving
        parse the tenant blob has always used, shared now with the per-tournament
        override which stores the identical shape.
        """
        result: Dict[date, Tuple[time, time]] = {}
        if not isinstance(data, dict):
            return result
        for date_str, window in data.items():
            try:
                d = date.fromisoformat(date_str)
                open_t = time.fromisoformat(window['open'])
                close_t = time.fromisoformat(window['close'])
                result[d] = (open_t, close_t)
            except (KeyError, ValueError, TypeError):
                continue
        return result

    @staticmethod
    async def get_tournament_hours(
        tournament: Optional[Tournament] = None,
    ) -> Dict[date, Tuple[time, time]]:
        """Return {date: (open_time, close_time)} for all configured days.

        When ``tournament`` carries its own ``tournament_hours`` blob it fully
        replaces the tenant schedule (a date absent means "unrestricted", the
        same semantics the tenant blob has); otherwise the tenant-wide setting is
        used. Passing no tournament preserves the tenant-only behavior.
        """
        if tournament is not None and tournament.tournament_hours is not None:
            return SystemConfigService._parse_hours_blob(tournament.tournament_hours)
        raw = await SystemConfigService.get_raw(KEY_TOURNAMENT_HOURS)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return SystemConfigService._parse_hours_blob(data)

    @staticmethod
    async def get_tournament_window_for_date(
        d: date, tournament: Optional[Tournament] = None,
    ) -> Optional[Tuple[time, time]]:
        """Return (open_time, close_time) for the given date, or None if not configured."""
        hours = await SystemConfigService.get_tournament_hours(tournament)
        return hours.get(d)

    @staticmethod
    async def get_station_format(default: StationFormat = StationFormat.FREE) -> StationFormat:
        raw = await SystemConfigService.get_raw(KEY_STATION_FORMAT)
        if not raw:
            return default
        try:
            return StationFormat(raw)
        except ValueError:
            return default

    @staticmethod
    def validate_hours_mapping(
        mapping: Dict[date, Tuple[str, str]],
    ) -> Dict[str, Dict[str, str]]:
        """Validate {date: (open_HH_MM, close_HH_MM)} into a storable blob.

        Blank days are dropped; a bad time or a non-increasing window raises a
        user-facing ``ValueError``. Shared by the tenant-wide setter and the
        per-tournament override so both enforce the identical rules.
        """
        data: Dict[str, Dict[str, str]] = {}
        for d, (open_str, close_str) in mapping.items():
            open_str = open_str.strip()
            close_str = close_str.strip()
            if not open_str or not close_str:
                continue
            try:
                open_t = time.fromisoformat(open_str)
                close_t = time.fromisoformat(close_str)
            except ValueError:
                raise ValueError(f"Tournament hours for {d} must be in HH:MM format.") from None
            if close_t <= open_t:
                raise ValueError(f"Close time must be after open time for {d}.")
            data[d.isoformat()] = {'open': open_str, 'close': close_str}
        return data

    @staticmethod
    async def set_tournament_hours(
        mapping: Dict[date, Tuple[str, str]], actor: User,
    ) -> None:
        """Persist per-day tournament hours. mapping is {date: (open_HH_MM, close_HH_MM)}."""
        data = SystemConfigService.validate_hours_mapping(mapping)
        await SystemConfigService.set_raw(KEY_TOURNAMENT_HOURS, json.dumps(data), actor)
