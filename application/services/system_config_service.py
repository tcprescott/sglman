"""
SystemConfig Service - Business Logic Layer

Typed accessors over the SystemConfiguration key/value table.
"""

import json
from datetime import date, datetime, time
from typing import Dict, Optional, Tuple

from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from application.utils.timezone import EASTERN_TZ, to_eastern
from models import Match, StationFormat, StreamRoom, SystemConfiguration, User


KEY_EVENT_START_DATE = 'event_start_date'
KEY_EVENT_END_DATE = 'event_end_date'
KEY_MAX_CONCURRENT_PLAYERS = 'max_concurrent_players'
KEY_MAX_CONCURRENT_STAGES = 'max_concurrent_stages'
KEY_VOLUNTEER_REMINDER_LEAD_MINUTES = 'volunteer_reminder_lead_minutes'
KEY_TOURNAMENT_HOURS = 'tournament_hours_by_date'
KEY_DISCORD_SYNC_GUILD_ID = 'discord_role_sync_guild_id'
KEY_STATION_FORMAT = 'station_format'


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
    async def get_discord_sync_guild_id() -> Optional[int]:
        """Return the Discord guild id used for login-time role sync, or None."""
        return await SystemConfigService.get_int(KEY_DISCORD_SYNC_GUILD_ID)

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
    async def get_event_window() -> tuple[date, date]:
        """Return (start_date, end_date) for the event.

        Falls back to the min/max Match.scheduled_at across all matches
        when SystemConfiguration values are missing. If there are no
        scheduled matches either, falls back to today and today+3 days.
        """
        start = await SystemConfigService.get_date(KEY_EVENT_START_DATE)
        end = await SystemConfigService.get_date(KEY_EVENT_END_DATE)

        if start is None or end is None:
            first = await Match.filter(tenant_id=require_tenant_id()).order_by('scheduled_at').first()
            last = await Match.filter(tenant_id=require_tenant_id()).order_by('-scheduled_at').first()
            derived_start = (
                to_eastern(first.scheduled_at).date()
                if first and first.scheduled_at else None
            )
            derived_end = (
                to_eastern(last.scheduled_at).date()
                if last and last.scheduled_at else None
            )
            if start is None:
                start = derived_start or datetime.now(EASTERN_TZ).date()
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
        return await StreamRoom.filter(is_active=True, tenant_id=require_tenant_id()).count()

    @staticmethod
    async def get_volunteer_reminder_lead_minutes(default: int = 60) -> int:
        value = await SystemConfigService.get_int(KEY_VOLUNTEER_REMINDER_LEAD_MINUTES)
        return value if value is not None and value > 0 else default

    @staticmethod
    async def get_tournament_hours() -> Dict[date, Tuple[time, time]]:
        """Return {date: (open_time, close_time)} for all configured days."""
        raw = await SystemConfigService.get_raw(KEY_TOURNAMENT_HOURS)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        result: Dict[date, Tuple[time, time]] = {}
        for date_str, window in data.items():
            try:
                d = date.fromisoformat(date_str)
                open_t = time.fromisoformat(window['open'])
                close_t = time.fromisoformat(window['close'])
                result[d] = (open_t, close_t)
            except (KeyError, ValueError):
                continue
        return result

    @staticmethod
    async def get_tournament_window_for_date(d: date) -> Optional[Tuple[time, time]]:
        """Return (open_time, close_time) for the given date, or None if not configured."""
        hours = await SystemConfigService.get_tournament_hours()
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
    async def set_tournament_hours(
        mapping: Dict[date, Tuple[str, str]], actor: User,
    ) -> None:
        """Persist per-day tournament hours. mapping is {date: (open_HH_MM, close_HH_MM)}."""
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
                raise ValueError(f"Tournament hours for {d} must be in HH:MM format.")
            if close_t <= open_t:
                raise ValueError(f"Close time must be after open time for {d}.")
            data[d.isoformat()] = {'open': open_str, 'close': close_str}
        await SystemConfigService.set_raw(KEY_TOURNAMENT_HOURS, json.dumps(data), actor)
