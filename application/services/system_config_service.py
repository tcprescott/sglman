"""
SystemConfig Service - Business Logic Layer

Typed accessors over the SystemConfiguration key/value table.
"""

from datetime import date, datetime
from typing import Optional

from application.services.audit_service import AuditActions, AuditService
from application.utils.timezone import EASTERN_TZ, to_eastern
from models import Match, StreamRoom, SystemConfiguration, User


KEY_EVENT_START_DATE = 'event_start_date'
KEY_EVENT_END_DATE = 'event_end_date'
KEY_MAX_CONCURRENT_PLAYERS = 'max_concurrent_players'
KEY_MAX_CONCURRENT_STAGES = 'max_concurrent_stages'


class SystemConfigService:
    """Typed get/set for SystemConfiguration entries used by reports."""

    @staticmethod
    async def get_raw(key: str) -> Optional[str]:
        config = await SystemConfiguration.get_or_none(name=key)
        return config.value if config else None

    @staticmethod
    async def set_raw(key: str, value: str, actor: User) -> SystemConfiguration:
        config = await SystemConfiguration.get_or_none(name=key)
        old_value = config.value if config else None
        if config:
            config.value = value
            await config.save()
            result = config
        else:
            result = await SystemConfiguration.create(name=key, value=value)
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
            first = await Match.all().order_by('scheduled_at').first()
            last = await Match.all().order_by('-scheduled_at').first()
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
        return await StreamRoom.filter(is_active=True).count()
