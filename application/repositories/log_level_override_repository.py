"""Log Level Override Repository — data access for runtime logger levels.

``LogLevelOverride`` is **global** (no tenant column): one process, one logging
tree, managed on ``/platform``. Nothing here is tenant-scoped.
"""

from typing import List, Optional

from models import LogLevelOverride, User


class LogLevelOverrideRepository:
    """Unscoped CRUD for :class:`~models.LogLevelOverride`."""

    @staticmethod
    async def list_all() -> List[LogLevelOverride]:
        return await LogLevelOverride.all().prefetch_related('updated_by').order_by('logger_name')

    @staticmethod
    async def get_by_name(logger_name: str) -> Optional[LogLevelOverride]:
        return await LogLevelOverride.get_or_none(logger_name=logger_name)

    @staticmethod
    async def upsert(logger_name: str, level: str, updated_by: Optional[User]) -> LogLevelOverride:
        override, _ = await LogLevelOverride.update_or_create(
            logger_name=logger_name,
            defaults={'level': level, 'updated_by': updated_by},
        )
        return override

    @staticmethod
    async def delete(override: LogLevelOverride) -> None:
        await override.delete()
