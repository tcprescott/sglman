"""Log Level Service — super-admin control of runtime logger levels.

Backs the Logging section of ``/platform``: a super-admin turns one module up to
DEBUG while chasing a live problem and back down afterwards, without a redeploy.
Each change is applied to the running process immediately and stored as a
:class:`~models.LogLevelOverride`, which :meth:`apply_persisted` reapplies at
startup so a restart mid-event keeps the setting.

Platform-level, like racetime bots: no tenant context, audit rows land with
``tenant=NULL``.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from application.repositories import LogLevelOverrideRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.utils.log_levels import (
    KNOWN_LOGGERS,
    apply_level,
    effective_level_name,
    level_number,
    normalize_logger_name,
)
from models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoggerLevelRow:
    """One logger as the platform table shows it."""

    name: str
    description: str
    override: Optional[str]
    effective: str
    updated_by: Optional[str]
    updated_at: Optional[datetime]


class LogLevelService:
    """List, set and clear per-logger levels; reapply them at startup."""

    def __init__(self) -> None:
        self.repository = LogLevelOverrideRepository()
        self.audit_service = AuditService()

    async def list_rows(self, actor: Optional[User]) -> List[LoggerLevelRow]:
        """Every known logger plus any overridden one, root first."""
        await AuthService.ensure_super_admin(actor)
        overrides = {o.logger_name: o for o in await self.repository.list_all()}
        rows: List[LoggerLevelRow] = []
        seen: set[str] = set()
        for known in KNOWN_LOGGERS:
            rows.append(self._row(known.name, known.description, overrides.get(known.name)))
            seen.add(known.name)
        for name in sorted(set(overrides) - seen):
            rows.append(self._row(name, 'Custom', overrides[name]))
        return rows

    async def set_level(self, actor: Optional[User], logger_name: str, level: str) -> None:
        await AuthService.ensure_super_admin(actor)
        name = normalize_logger_name(logger_name)
        level = (level or '').strip().upper()
        level_number(level)
        existing = await self.repository.get_by_name(name)
        previous = existing.level if existing else None
        await self.repository.upsert(name, level, actor)
        apply_level(name, level)
        await self.audit_service.write_log(
            actor, AuditActions.LOG_LEVEL_SET,
            {'logger': name or 'root', 'level': level, 'previous': previous},
        )
        logger.warning('Log level for %s set to %s by %s', name or 'root', level, actor.username)

    async def clear(self, actor: Optional[User], logger_name: str) -> None:
        """Drop the override; the logger goes back to inheriting its parent."""
        await AuthService.ensure_super_admin(actor)
        name = normalize_logger_name(logger_name)
        existing = await self.repository.get_by_name(name)
        if existing is None:
            return
        await self.repository.delete(existing)
        apply_level(name, None)
        await self.audit_service.write_log(
            actor, AuditActions.LOG_LEVEL_CLEARED,
            {'logger': name or 'root', 'previous': existing.level},
        )
        logger.warning('Log level override for %s cleared by %s', name or 'root', actor.username)

    async def apply_persisted(self) -> int:
        """Reapply every stored override to the live tree. Startup only.

        A row that no longer parses (a level renamed in code) is skipped and
        logged rather than stopping boot over a diagnostic setting.
        """
        applied = 0
        for override in await self.repository.list_all():
            try:
                apply_level(override.logger_name, override.level)
            except ValueError:
                logger.error(
                    'Ignoring stored log level %r for %s',
                    override.level, override.logger_name or 'root',
                )
                continue
            applied += 1
        if applied:
            logger.warning('Applied %d stored log-level override(s)', applied)
        return applied

    @staticmethod
    def _row(name: str, description: str, override) -> LoggerLevelRow:
        return LoggerLevelRow(
            name=name,
            description=description,
            override=override.level if override else None,
            effective=effective_level_name(name),
            updated_by=(
                override.updated_by.username
                if override is not None and override.updated_by is not None else None
            ),
            updated_at=override.updated_at if override else None,
        )
